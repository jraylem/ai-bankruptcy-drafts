"""Template grammar validator — Tier 1 deterministic scan for obvious
agreement-mismatch risk in a filled docx.

Sibling to `template_format_validator`. The format validator catches
layout drift (lost line breaks, tabs, paragraph boundaries) from the
substitution engine. The grammar validator catches agreement drift
between hardcoded template language ("Debtors", "their", "have",
"these") and the resolved values' actual cardinality (single vs.
joint debtor; single vs. multiple creditors; etc.).

Examples this is meant to flag:
  - Caption "JUDITH S SCHWARTZ" + label "Debtors." — single debtor
    but plural label.
  - Body "The Debtors, Judith S. Schwartz, by and through their
    undersigned counsel" — single debtor name with plural noun +
    plural possessive.
  - "This filing was made by the Debtors, who hereby request..." —
    same shape inside narrative prose.

Two-stage design (mirrors the format pipeline):

    Tier 1 (this module, deterministic):
      - Walk the filled doc; record paragraphs that contain
        plural-sensitive tokens ("Debtors", "their", "they",
        "have", "are", "these", etc.).
      - Inspect the resolved values map to infer plurality signals
        (multi-line debtor_name => joint; single-line => solo).
      - When plurality signals contradict plural-token presence,
        flag the paragraphs as `GrammarSuspectParagraph`s.
      - Otherwise return ok=True — saves LLM cost when nothing
        looks broken.

    Tier 2 (template_grammar_fixer):
      - Sonnet 4.6 reviews the suspect paragraphs with the
        resolved values as context; returns per-paragraph
        corrections constrained by a content-preservation
        guardrail (names / numbers / dates / emails / amounts
        from the original must survive in the corrected text).

Conservative by design: the validator is BIASED toward flagging
ambiguous cases (the LLM can decide they're actually fine and
return them unchanged). The cost of one extra Sonnet call is far
lower than the cost of shipping a draft that reads "The Debtors,
Judith Schwartz, by and through their counsel" to the court.

Used behind `TEMPLATE_GRAMMAR_AUTOFIX_V2=1` env flag. The validator
itself is cheap and pure-Python; the gate is on whether the Tier 2
LLM fixer runs.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from docx import Document
from docx.oxml.ns import qn

from .docx_template import DocxTemplateService

logger = logging.getLogger(__name__)


# Plural-sensitive tokens — when any of these appear in a paragraph
# AND the underlying entity is singular, we likely have an agreement
# error. Lowercased; matched word-boundary case-insensitive.
_PLURAL_NOUNS = frozenset({
    "debtors",
    "creditors",
    "trustees",
    "movants",
    "petitioners",
    "respondents",
    "plaintiffs",
    "defendants",
    "claimants",
    "applicants",
})

_PLURAL_PRONOUNS = frozenset({
    "they",
    "them",
    "their",
    "theirs",
    "themselves",
})

_PLURAL_VERBS = frozenset({
    "are",
    "were",
    "have",
    "do",
})

_PLURAL_DETERMINERS = frozenset({
    "these",
    "those",
})

_ALL_PLURAL_TOKENS = (
    _PLURAL_NOUNS | _PLURAL_PRONOUNS | _PLURAL_VERBS | _PLURAL_DETERMINERS
)

# Multi-name joiner words — when a resolved value contains these AND
# multiple capitalized name-shaped tokens, treat it as joint. `&`
# doesn't sit between word boundaries (it's a non-word character) so
# match it as a literal alternative outside the `\b...\b` group.
_JOINT_JOINER_RE = re.compile(r"\band\b|&", re.IGNORECASE)

# Variables whose cardinality drives plural-agreement decisions. Other
# resolved values (case numbers, dates, dollar amounts) don't carry
# plurality signals; we ignore them for cardinality inference.
_CARDINALITY_VARS = frozenset({
    "debtor_name",
    "debtor_names",
    "debtors",
    "joint_debtor_name",
    "movant_name",
    "movant_names",
    "creditor_name",
    "creditors",
    "trustee_name",
    "trustees",
    "petitioner_name",
    "petitioner_names",
    "plaintiff_name",
    "plaintiffs",
    "defendant_name",
    "defendants",
})


@dataclass(frozen=True)
class GrammarSuspectParagraph:
    """One paragraph flagged as a likely agreement-mismatch candidate.

    `template_paragraph_index` is the position in
    `DocxTemplateService._iter_all_paragraphs(doc)` walk order — same
    convention the format validator uses, so the fixer can address
    paragraphs by stable index.
    """
    template_paragraph_index: int
    paragraph_text: str
    triggered_tokens: tuple[str, ...]
    suspect_reason: str


@dataclass(frozen=True)
class GrammarValidationResult:
    ok: bool
    suspect_paragraphs: list[GrammarSuspectParagraph]
    cardinality_signals: dict[str, str]  # variable -> "single" | "joint" | "unknown"
    summary: str


def validate_fill_grammar(
    filled_bytes: bytes,
    resolved_values: dict[str, str],
) -> GrammarValidationResult:
    """Deterministic scan over the filled docx for agreement-mismatch
    risk.

    Args:
        filled_bytes: The rendered .docx after `fill_template` /
            `_fill_template_v2`. Validator reads paragraphs in
            `_iter_all_paragraphs` order so suspect indices line up
            with what the fixer + finalizer use.
        resolved_values: `template_variable -> resolved value` map.
            Plurality signals are inferred from values whose key
            matches `_CARDINALITY_VARS` — single-line / no-joiner
            values are "single"; multi-line OR joiner-bearing values
            are "joint".

    Returns:
        `ok=True` when no suspect paragraphs detected (skip the LLM
        fixer). `ok=False` with one `GrammarSuspectParagraph` per
        flagged paragraph and a per-variable `cardinality_signals`
        map the fixer can pass to the LLM as context.
    """
    try:
        doc = Document(_BytesIO(filled_bytes))
    except Exception as exc:  # noqa: BLE001
        logger.warning("TemplateGrammarValidator: doc parse failed (%s); skipping", exc)
        return GrammarValidationResult(
            ok=True,
            suspect_paragraphs=[],
            cardinality_signals={},
            summary=f"Parse failure: {exc}",
        )

    cardinality_signals = _infer_cardinality_signals(resolved_values)
    if _all_cardinality_unknown(cardinality_signals):
        # No plurality-sensitive variables resolved at all — assume the
        # template's hardcoded plural language is intentional and skip.
        return GrammarValidationResult(
            ok=True,
            suspect_paragraphs=[],
            cardinality_signals=cardinality_signals,
            summary="No cardinality-sensitive variables in resolved set; skipping",
        )

    has_single_party = any(
        sig == "single" for sig in cardinality_signals.values()
    )
    if not has_single_party:
        # Every party is joint / unknown — plural tokens are fine.
        return GrammarValidationResult(
            ok=True,
            suspect_paragraphs=[],
            cardinality_signals=cardinality_signals,
            summary="All cardinality-sensitive parties are joint; plural tokens expected",
        )

    suspect: list[GrammarSuspectParagraph] = []
    for idx, paragraph in enumerate(DocxTemplateService._iter_all_paragraphs(doc)):
        text = _paragraph_text(paragraph)
        if not text.strip():
            continue
        triggered = _scan_plural_tokens(text)
        if not triggered:
            continue
        suspect.append(GrammarSuspectParagraph(
            template_paragraph_index=idx,
            paragraph_text=text,
            triggered_tokens=tuple(sorted(triggered)),
            suspect_reason=(
                "Plural-sensitive tokens detected while at least one "
                "cardinality-sensitive party resolved as single."
            ),
        ))

    if not suspect:
        return GrammarValidationResult(
            ok=True,
            suspect_paragraphs=[],
            cardinality_signals=cardinality_signals,
            summary="No plural tokens found in any paragraph",
        )
    return GrammarValidationResult(
        ok=False,
        suspect_paragraphs=suspect,
        cardinality_signals=cardinality_signals,
        summary=(
            f"Grammar suspects detected: {len(suspect)} paragraph(s) "
            "with plural tokens while one or more parties are single."
        ),
    )


def _paragraph_text(paragraph) -> str:
    """Read paragraph text with `<w:br/>` as `\\n` and `<w:tab/>` as
    `\\t` so grammar scanning sees the visual layout the same way the
    fixer's apply step does."""
    parts: list[str] = []
    for elem in paragraph._element.iter(qn("w:t"), qn("w:br"), qn("w:tab")):
        if elem.tag == qn("w:t"):
            parts.append(elem.text or "")
        elif elem.tag == qn("w:br"):
            parts.append("\n")
        else:
            parts.append("\t")
    return "".join(parts)


def _scan_plural_tokens(text: str) -> set[str]:
    """Return the lowercased plural tokens found in `text`. Matched
    via word boundaries so "Their" and "There" are distinguishable
    (we want the former, not the latter)."""
    found: set[str] = set()
    for word in re.findall(r"[A-Za-z']+", text):
        lower = word.lower()
        if lower in _ALL_PLURAL_TOKENS:
            found.add(lower)
    return found


def _infer_cardinality_signals(resolved_values: dict[str, str]) -> dict[str, str]:
    """For each cardinality-sensitive variable in the resolved map,
    classify the value as "single" / "joint" / "unknown".

      - "joint": value contains a real newline (the v2 joint-debtor
        convention from Rule 15) OR contains the word "and" / "&"
        between two capitalized name-shaped tokens.
      - "single": value is non-empty AND has no joint signals.
      - "unknown": value is empty / blank.
    """
    signals: dict[str, str] = {}
    for var, raw in resolved_values.items():
        if var.lower() not in _CARDINALITY_VARS:
            continue
        value = (raw or "").strip()
        if not value:
            signals[var] = "unknown"
            continue
        if "\n" in value:
            signals[var] = "joint"
            continue
        if _looks_like_multi_name(value):
            signals[var] = "joint"
            continue
        signals[var] = "single"
    return signals


def _looks_like_multi_name(value: str) -> bool:
    """A single-line value is "joint" when it contains an `and` / `&`
    joiner AND at least two capitalized name-shaped tokens flanking
    it. Catches "Robert Creswell and Lori Creswell" without firing on
    single names that happen to include "and" (rare for people names).
    """
    if not _JOINT_JOINER_RE.search(value):
        return False
    capitalized = re.findall(r"\b[A-Z][a-zA-Z'.-]{1,}\b", value)
    return len(capitalized) >= 3  # at least one name each side of `and`


def _all_cardinality_unknown(signals: dict[str, str]) -> bool:
    if not signals:
        return True
    return all(sig == "unknown" for sig in signals.values())


# Defer the import so test modules can monkeypatch python-docx without
# pulling its full transitive surface at import time.
from io import BytesIO as _BytesIO  # noqa: E402
