"""Template format fixer — Tier 2 LLM-assisted repair of drifted
filled paragraphs.

Sibling to `template_format_validator`. The validator detects drift;
the fixer attempts to repair it via a Sonnet call constrained to
formatting changes only.

Pipeline:
  1. Validator finds `DriftedParagraph` entries in the filled docx.
  2. For each, fixer calls Sonnet 4.6 with template_text +
     filled_text + resolved_values + the canonical expected text.
     Sonnet returns `{corrected_text: "..."}`.
  3. CONTENT-EQUALITY GUARDRAIL (deterministic): normalize both
     filled_text and corrected_text by lower-casing + stripping all
     whitespace + stripping punctuation. They must be identical —
     i.e. the LLM only changed HOW characters are laid out, never
     WHAT was said. Otherwise reject the LLM output, leave the
     filled bytes unchanged, log WARNING.
  4. APPLY (deterministic): rebuild the drifted paragraph's
     `<w:r>` children from corrected_text — split on `\\n` /
     `\\t`, insert `<w:br/>` / `<w:tab/>` between segments, wrap
     text in `<w:t>` runs. Loses run-level formatting (bold /
     italic) inside the rebuilt paragraph but for CoS / contact
     blocks that's fine (uniformly formatted text). Mixed-format
     paragraphs aren't expected here because the validator only
     flags paragraphs where the SAME substitution decision needs
     to be applied to the entire region.
  5. RE-VALIDATE: run `validate_fill_format` again on the fixed
     bytes. Still-drifted paragraphs are logged but the fixed bytes
     ship to R2 anyway (best-effort — fixer never makes things
     worse than Tier 1).

Soft-fail throughout: LLM errors, invalid JSON, content-equality
failure, apply errors are all swallowed with WARNING. The fixer
never blocks the fill pipeline.

Cost attribution: `template_format_fix_v2` for dashboard isolation.

Behind `TEMPLATE_FORMAT_AUTOFIX_V2=1` env flag (same as validator,
Option A — one knob).
"""

from __future__ import annotations

import logging
import re
import string
from io import BytesIO
from typing import Any

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from langchain_anthropic import ChatAnthropic
from pydantic import BaseModel, Field

from src.core.common.constants import CLAUDE_MODEL_STANDARD
from src.core.common.cost_tracking import (
    CostTrackingCallback,
    build_cost_context_for_agent,
)

from .template_format_validator import (
    DriftedParagraph,
    _paragraph_text_with_breaks,
    _render_expected_fill,
)

logger = logging.getLogger(__name__)


_COST_KIND = "template_format_fix_v2"
_TAGS = ["core", "agent", "template_format_fix_v2"]
_MAX_TOKENS = 2000
_PUNCT_TABLE = str.maketrans("", "", string.punctuation)


class _CorrectedParagraph(BaseModel):
    """LLM structured-output schema."""
    corrected_text: str = Field(
        description=(
            "The filled paragraph text with formatting corrected. Use "
            "\\n for line breaks and \\t for tabs. Never change words, "
            "names, numbers, emails, or any content — only fix layout."
        ),
    )


async def autofix_fill_drift(
    filled_bytes: bytes,
    template_bytes: bytes,
    resolved_values: dict[str, str],
    drifted_paragraphs: list[DriftedParagraph],
) -> bytes:
    """Attempt to repair each drifted paragraph by calling Sonnet 4.6
    for a formatting-only correction, content-equality-checking the
    response, and rebuilding the paragraph XML deterministically.

    Returns the fixed bytes on success — OR the original `filled_bytes`
    unchanged if ANY step soft-fails for ANY drifted paragraph (the
    fixer is best-effort; surviving drift is still better than no
    drift detection + corrupted output).
    """
    if not drifted_paragraphs:
        return filled_bytes

    try:
        filled_doc = Document(BytesIO(filled_bytes))
        template_doc = Document(BytesIO(template_bytes))
    except Exception as err:  # noqa: BLE001
        logger.warning("TemplateFormatFixer: doc parse failed (%s); skipping fix", err)
        return filled_bytes

    from .docx_template import DocxTemplateService
    template_paras = list(DocxTemplateService._iter_all_paragraphs(template_doc))
    filled_paras = list(DocxTemplateService._iter_all_paragraphs(filled_doc))

    if len(template_paras) != len(filled_paras):
        logger.warning(
            "TemplateFormatFixer: paragraph count mismatch (template=%d, filled=%d); "
            "skipping fix",
            len(template_paras), len(filled_paras),
        )
        return filled_bytes

    placeholder_to_value = {f"[[{n}]]": v for n, v in resolved_values.items()}
    fixed_any = False

    for drift in drifted_paragraphs:
        idx = drift.template_paragraph_index
        if idx < 0 or idx >= len(filled_paras):
            continue
        tmpl_para = template_paras[idx]
        filled_para = filled_paras[idx]
        tmpl_text = _paragraph_text_with_breaks(tmpl_para)
        filled_text = _paragraph_text_with_breaks(filled_para)

        relevant_values = {
            ph[2:-2]: v
            for ph, v in placeholder_to_value.items()
            if ph in tmpl_text
        }

        try:
            corrected = await _call_sonnet_for_fix(
                template_text=tmpl_text,
                filled_text=filled_text,
                resolved_values=relevant_values,
            )
        except Exception as err:  # noqa: BLE001
            logger.warning(
                "TemplateFormatFixer: Sonnet call failed for paragraph %d (%s); "
                "skipping this fix",
                idx, err,
            )
            continue

        if corrected is None or corrected == filled_text:
            continue

        expected_text = _render_expected_fill(
            tmpl_para, tmpl_text, placeholder_to_value,
        )
        if not _content_equivalent(expected_text, corrected):
            logger.warning(
                "TemplateFormatFixer: rejecting LLM correction for paragraph %d — "
                "content equality guardrail failed (expected_norm=%r corrected_norm=%r)",
                idx,
                _normalize_for_equality(expected_text)[:80],
                _normalize_for_equality(corrected)[:80],
            )
            continue

        try:
            _apply_corrected_text(filled_para._element, corrected)
            fixed_any = True
        except Exception as err:  # noqa: BLE001
            logger.warning(
                "TemplateFormatFixer: apply failed for paragraph %d (%s); "
                "leaving original",
                idx, err,
            )

    if not fixed_any:
        return filled_bytes

    output = BytesIO()
    filled_doc.save(output)
    output.seek(0)
    return output.read()


async def _call_sonnet_for_fix(
    *,
    template_text: str,
    filled_text: str,
    resolved_values: dict[str, str],
) -> str | None:
    """Single Sonnet roundtrip. Returns the corrected text, or None on
    any LLM-side failure (caller swallows + skips this drift).

    Structured output via `with_structured_output(_CorrectedParagraph)`
    forces the model to return clean JSON — no regex parsing needed.
    """
    prompt = _build_fix_prompt(
        template_text=template_text,
        filled_text=filled_text,
        resolved_values=resolved_values,
    )

    llm = ChatAnthropic(
        model=CLAUDE_MODEL_STANDARD,
        max_tokens=_MAX_TOKENS,
    )
    cost_ctx = build_cost_context_for_agent(
        kind=_COST_KIND,
        agent_name="TemplateFormatFixerV2",
        extra_metadata={"placeholders": list(resolved_values.keys())},
    )
    callbacks: list[Any] = [CostTrackingCallback(cost_context=cost_ctx)]
    try:
        from src.core.studio_v2.observability import langfuse_callback
        lf_handler = langfuse_callback()
        if lf_handler is not None:
            callbacks.append(lf_handler)
    except Exception:  # noqa: BLE001
        pass

    chain = llm.with_structured_output(_CorrectedParagraph).with_config({
        "run_name": "TemplateFormatFixerV2",
        "tags": _TAGS,
        "callbacks": callbacks,
    })
    response = await chain.ainvoke(prompt)
    if response is None:
        return None
    if isinstance(response, _CorrectedParagraph):
        return _decode_escape_sequences(response.corrected_text)
    if isinstance(response, dict) and "corrected_text" in response:
        return _decode_escape_sequences(response["corrected_text"])
    return None


def _decode_escape_sequences(text: str) -> str:
    """Defensive normalization: Claude sometimes echoes our prompt's
    literal `\\n` / `\\t` examples verbatim (backslash + letter, two
    chars) instead of using real newline / tab characters. Convert
    those two-char escape sequences to their single-char form so the
    content-equality guardrail's whitespace normalization treats them
    correctly.

    Idempotent — if the model returned real `\\n` already, this is a
    no-op.
    """
    return text.replace("\\n", "\n").replace("\\t", "\t").replace("\\r", "\r")


def _build_fix_prompt(
    *,
    template_text: str,
    filled_text: str,
    resolved_values: dict[str, str],
) -> str:
    values_block = "\n".join(
        f"  [[{name}]] = {value!r}" for name, value in resolved_values.items()
    ) or "  (none)"
    return f"""You are a deterministic formatting-correction tool for
legal documents. You are NEVER allowed to invent, rephrase, or
remove content. Your only job is to fix LAYOUT: line breaks, tabs,
spaces, and leading/trailing whitespace.

A template paragraph contains [[placeholders]] that were substituted
with resolved values to produce a filled paragraph. The substitution
engine may have lost a line break or merged content incorrectly.
Compare the template's structure to the filled output, and return
the corrected filled paragraph text.

<template_paragraph>
{template_text}
</template_paragraph>

<placeholder_resolved_values>
{values_block}
</placeholder_resolved_values>

<actual_filled_paragraph>
{filled_text}
</actual_filled_paragraph>

Rules:
1. The corrected text MUST contain the same characters as the filled
   paragraph, in the same order — only line breaks, tab characters,
   and surrounding whitespace may differ.
2. NEVER add or remove names, numbers, emails, dates, words, or
   punctuation. ONLY change formatting.
3. If the filled paragraph already looks correct, return it
   UNCHANGED.
4. Multi-line resolved values whose placeholder occupies the entire
   template paragraph should render with REAL line breaks between
   lines (use actual newline characters, NOT the literal text "\\n").
   NEVER join multi-line values with the word "and".
5. Tab characters between fields must be preserved as actual tab
   characters (NOT the literal text "\\t").
6. CRITICAL: emit ACTUAL line break and tab characters in the JSON
   string value. Do NOT emit the literal backslash-letter sequence
   text — the output will be parsed as a real string, not as a
   Python literal.

Return JSON with one field: `corrected_text` (the fixed paragraph).
"""


def _content_equivalent(original: str, corrected: str) -> bool:
    """Deterministic guardrail. Both strings must reduce to the same
    canonical form after stripping ALL whitespace, ALL punctuation,
    and lower-casing. Catches LLM hallucinations that rewrite content
    under the guise of formatting fixes.
    """
    return _normalize_for_equality(original) == _normalize_for_equality(corrected)


def _normalize_for_equality(text: str) -> str:
    text = text.lower()
    text = text.translate(_PUNCT_TABLE)
    text = re.sub(r"\s+", "", text)
    return text


def _apply_corrected_text(paragraph_element, corrected_text: str) -> None:
    """Rebuild `paragraph_element`'s `<w:r>` children to render
    `corrected_text` exactly. Splits on `\\n` (becomes `<w:br/>`) and
    `\\t` (becomes `<w:tab/>`).

    Removes all existing `<w:r>` children and inserts a single fresh
    `<w:r>` with the corrected content. Run-level formatting inside
    the paragraph is lost — acceptable for the contact-block / caption
    case the validator typically flags (uniformly formatted text).

    Preserves the paragraph's `<w:pPr>` (paragraph properties) so
    style / alignment / indentation stay intact.
    """
    pPr = paragraph_element.find(qn("w:pPr"))
    for child in list(paragraph_element):
        if child.tag != qn("w:pPr"):
            paragraph_element.remove(child)

    new_run = OxmlElement("w:r")
    _append_content_to_run(new_run, corrected_text)
    if pPr is not None:
        pPr.addnext(new_run)
    else:
        paragraph_element.append(new_run)


def _append_content_to_run(run_element, text: str) -> None:
    """Walk `text`, emitting `<w:t>` / `<w:br/>` / `<w:tab/>` children
    into `run_element` to faithfully reproduce the layout."""
    buffer = ""

    def _flush():
        nonlocal buffer
        if not buffer:
            return
        t = OxmlElement("w:t")
        t.text = buffer
        if buffer.startswith(" ") or buffer.endswith(" ") or "  " in buffer:
            t.set(qn("xml:space"), "preserve")
        run_element.append(t)
        buffer = ""

    for ch in text:
        if ch == "\n":
            _flush()
            br = OxmlElement("w:br")
            br.set(qn("w:type"), "line")
            run_element.append(br)
        elif ch == "\t":
            _flush()
            tab = OxmlElement("w:tab")
            run_element.append(tab)
        else:
            buffer += ch
    _flush()
