"""Template grammar fixer — Tier 2 LLM-assisted repair of agreement
mismatches between hardcoded template language and the resolved
values' actual cardinality.

Sibling to `template_format_fixer`. The format fixer repairs LAYOUT
drift (lost line breaks, tabs, paragraph boundaries). The grammar
fixer repairs AGREEMENT drift — plural noun / pronoun / verb /
determiner forms that contradict a single-debtor case (or vice
versa for joint cases).

SURGICAL DESIGN — the LLM never produces paragraph text. Instead it
identifies single-word swaps (`original_word`, `replacement_word`,
`paragraph_index`) and we apply them in-place inside each `<w:t>`
element. This is impossible to abuse for case normalization or
layout rewrites because:

  - The schema literally has no field for whole-paragraph text.
  - Each substitution is validated against a closed allowlist of
    agreement-word pairs (`_AGREEMENT_PAIRS`) AND the case style of
    `replacement_word` must match `original_word`.
  - We only mutate `<w:t>.text` character content; `<w:rPr>`
    siblings (bold / underline / italic / font / color) are
    untouched, so heading / caption formatting survives.
  - The word-token regex treats apostrophes as part of words, so
    replacing "Debtors" doesn't accidentally hit "Debtors'" inside
    the same paragraph (each possessive form is its own swap).

Pipeline:
  1. `validate_fill_grammar` (Tier 1, deterministic) flags suspect
     paragraphs whose plural tokens contradict the resolved values'
     cardinality signals.
  2. This module ships the suspect paragraphs + cardinality signals
     + resolved values to Sonnet 4.6 in one document-level call.
     The LLM emits a flat list of `_WordSubstitution` entries.
  3. ALLOWLIST CHECK (deterministic): each substitution must be a
     known agreement pair AND case-style-preserving. Failures get
     dropped with a WARNING.
  4. APPLY (deterministic): walk `<w:t>` elements in the target
     paragraph, replace every word-token match of `original_word`
     with `replacement_word`. Run formatting preserved by
     construction.
  5. Soft-fail throughout — LLM errors, invalid JSON, missing words
     all swallowed with WARNING. Fixer never makes things worse
     than skipping the fix.

Cost attribution: `template_grammar_fix_v2` for dashboard isolation
(separate from `template_format_fix_v2`).

Behind `TEMPLATE_GRAMMAR_AUTOFIX_V2=1` env flag — independent of the
format fixer's flag so each can be rolled separately.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from io import BytesIO
from typing import Any

from docx import Document
from docx.oxml.ns import qn
from langchain_anthropic import ChatAnthropic
from pydantic import BaseModel, Field

from src.core.common.constants import CLAUDE_MODEL_STANDARD
from src.core.common.cost_tracking import (
    CostTrackingCallback,
    build_cost_context_for_agent,
)

from .template_grammar_validator import (
    GrammarSuspectParagraph,
)

logger = logging.getLogger(__name__)


_COST_KIND = "template_grammar_fix_v2"
_TAGS = ["core", "agent", "template_grammar_fix_v2"]
_MAX_TOKENS = 4000

# Word-token regex. Treats apostrophes (straight + curly) as part of
# the word so possessives like "Debtors'" / "Debtor's" / "DEBTOR'S"
# are single tokens. Underscores are intentionally EXCLUDED — caption
# slots ("________ Debtor.") use leading underscores as visual layout
# (a fill line); those belong to the non-word group and must be
# preserved byte-for-byte by the apply step.
_WORD_TOKEN_RE = re.compile(r"[A-Za-z‘’']+|[^A-Za-z‘’']+")

# Allowed agreement-word swaps. Lowercased + apostrophe-normalized.
# The fixer's in-place apply rejects any word-token substitution
# whose pair isn't in this set — prevents the LLM from "helpfully"
# normalizing case ("EX-PARTE MOTION" → "Ex-Parte Motion"), rewriting
# verbs, or restructuring headings under the guise of grammar fixes.
# Add new pairs here as new agreement patterns surface in practice.
_AGREEMENT_PAIRS: frozenset[frozenset[str]] = frozenset({
    # Bankruptcy / litigation party nouns — plural ↔ singular
    frozenset(("debtors", "debtor")),
    frozenset(("debtors'", "debtor's")),
    frozenset(("creditors", "creditor")),
    frozenset(("creditors'", "creditor's")),
    frozenset(("trustees", "trustee")),
    frozenset(("trustees'", "trustee's")),
    frozenset(("movants", "movant")),
    frozenset(("movants'", "movant's")),
    frozenset(("petitioners", "petitioner")),
    frozenset(("petitioners'", "petitioner's")),
    frozenset(("respondents", "respondent")),
    frozenset(("respondents'", "respondent's")),
    frozenset(("plaintiffs", "plaintiff")),
    frozenset(("plaintiffs'", "plaintiff's")),
    frozenset(("defendants", "defendant")),
    frozenset(("defendants'", "defendant's")),
    frozenset(("claimants", "claimant")),
    frozenset(("claimants'", "claimant's")),
    frozenset(("applicants", "applicant")),
    frozenset(("applicants'", "applicant's")),
    # Pronouns are DELIBERATELY ABSENT from this allowlist. Modern
    # legalese (and most state bar style manuals) default to singular
    # they: "the Debtor, by and through their counsel" stays as
    # "their" regardless of the resolved debtor's gender. Forcing
    # "their" → "her" or "his" risks silently misgendering from a
    # name guess (Andrea / Pat / Jordan are ambiguous; even
    # unambiguous-sounding names can mismatch the actual person).
    # The validator still flags pronoun tokens so the LLM has a
    # chance to consider them and emit replace_original=False;
    # this allowlist ensures any LLM-emitted pronoun swap gets
    # rejected at apply time. Bypass: future per-firm config could
    # opt in to gendered swaps; v1 is hard-coded singular-they.
    # Verbs — plural ↔ singular
    frozenset(("are", "is")),
    frozenset(("were", "was")),
    frozenset(("have", "has")),
    frozenset(("do", "does")),
    # Determiners — plural ↔ singular
    frozenset(("these", "this")),
    frozenset(("those", "that")),
})

_APOSTROPHE_NORMALIZE = str.maketrans("‘’", "''")

# Phrases that, when present in the LLM's `reason` field for a
# substitution, indicate the LLM reasoned itself out of the swap
# but emitted it anyway. We treat the reason field as a COMMITMENT
# ledger, not an "explain yourself" field — any hedge means the swap
# is rejected. Backstop for the prompt instruction "omit, don't
# explain". Lowercased + substring-matched.
#
# Real example (2026-05-28 worker log):
#   _WordSubstitution(original_word="have", replacement_word="has",
#       reason="... but wait, the subject here is NOT the debtor; "
#              "'have' agrees with 'differences' (plural noun), so "
#              "this is grammatically correct and should NOT be "
#              "changed")
#
# The LLM identified the correct grammar but emitted the swap
# anyway. This list catches that class.
_HEDGING_REASON_PHRASES: tuple[str, ...] = (
    "but wait",
    "but actually",
    "actually, ",
    "however,",
    "on second thought",
    "should not be changed",
    "shouldn't be changed",
    "should not change",
    "do not change",
    "don't change",
    "do not swap",
    "don't swap",
    "is grammatically correct",
    "is correct",
    "is already correct",
    "no swap needed",
    "no change needed",
    "no fix needed",
    "i was wrong",
    "i was mistaken",
    "i should not",
    "i shouldn't",
    "this might be wrong",
    "this may be wrong",
    "not the debtor",
    "not the subject",
    "not actually",
    "wrong swap",
    "incorrect swap",
)

# Maximum number of characters of the post-fix paragraph to include in
# the forensic record. Long enough for a paralegal to recognize the
# heading / caption / sentence; short enough to stay readable in the
# Resolution Log UI.
_PARAGRAPH_PREVIEW_MAX = 160


@dataclass(frozen=True)
class GrammarRepairRecord:
    """Forensic record of a single agreement-swap actually applied to
    the filled docx. The finalizer converts this to the wire-facing
    `GrammarRepairV2` Pydantic model.

    This dataclass lives in `common/` (no studio_v2 dependency) so the
    fixer module can return it without inverting the package layering.
    """
    paragraph_index: int
    original_word: str
    replacement_word: str
    occurrences: int
    paragraph_preview: str
    reason: str


class _WordSubstitution(BaseModel):
    paragraph_index: int = Field(
        description=(
            "Which suspect paragraph this substitution applies to. "
            "Must match one of the paragraph_index values the user "
            "supplied in <suspect_paragraphs>."
        ),
    )
    original_word: str = Field(
        description=(
            "The EXACT word as it appears in the paragraph text — "
            "case-preserved, apostrophes included. E.g. 'Debtors', "
            "'DEBTORS\\'', 'have', 'these'. Must appear literally in "
            "the paragraph."
        ),
    )
    replacement_word: str = Field(
        description=(
            "The singular/plural counterpart in the SAME CASE STYLE "
            "as original_word. E.g. 'Debtors'→'Debtor', "
            "'DEBTORS\\''→'DEBTOR\\'S', 'have'→'has', 'these'→'this'. "
            "For pronouns (which are NEVER swapped), populate this "
            "with the same string as original_word and set "
            "replace_original=False. Otherwise it represents the "
            "'what would the swap be' answer for logging / debugging."
        ),
    )
    replace_original: bool = Field(
        default=True,
        description=(
            "THE CONTRACT. True = apply this swap to the docx. "
            "False = skip; you considered this flagged word and "
            "decided the original is correct (e.g. the verb's "
            "subject is a plural noun OTHER than the cardinality-"
            "sensitive party, so the original verb agreement is "
            "right). Only substitutions with replace_original=True "
            "modify the docx. The fixer will NOT look at reason to "
            "override this — set it correctly. Default True matches "
            "the prior behavior when this field was absent; the "
            "prompt instructs you to set it EXPLICITLY for every "
            "flagged word, but the default keeps legacy callers safe."
        ),
    )
    reason: str = Field(
        default="",
        description=(
            "One short AFFIRMATIVE clause matching the decision in "
            "replace_original. When True: 'single debtor; subject is "
            "debtor'. When False: 'subject is differences (plural); "
            "keep have'. Never hedge after committing — if you find "
            "yourself writing 'but wait', flip replace_original and "
            "rewrite the reason."
        ),
    )


class _GrammarCorrections(BaseModel):
    substitutions: list[_WordSubstitution] = Field(
        default_factory=list,
        description=(
            "Flat list of word-level substitutions across all suspect "
            "paragraphs. The applier groups by paragraph_index. "
            "Return an empty list if no real agreement fixes are "
            "needed."
        ),
    )


async def autofix_grammar_drift(
    *,
    filled_bytes: bytes,
    resolved_values: dict[str, str],
    suspect_paragraphs: list[GrammarSuspectParagraph],
    cardinality_signals: dict[str, str],
) -> tuple[bytes, list[GrammarRepairRecord]]:
    """Attempt to repair agreement drift in the filled docx via a
    single Sonnet 4.6 call.

    Returns `(fixed_bytes, applied_repairs)`:
      - `fixed_bytes` is the post-fix docx bytes on success, or the
        original `filled_bytes` unchanged when nothing applied.
      - `applied_repairs` is the list of agreement swaps that
        ACTUALLY landed inside `<w:t>` elements (allowlist passed,
        word found, paragraph mutated). Empty when no swaps applied
        — even if the LLM emitted suggestions that were all rejected
        or untargetable.

    Soft-fails throughout — LLM errors, parse errors, missing words
    are all swallowed with a WARNING; the caller gets `(filled_bytes,
    [])` and continues.
    """
    if not suspect_paragraphs:
        return filled_bytes, []

    try:
        doc = Document(BytesIO(filled_bytes))
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "TemplateGrammarFixer: doc parse failed (%s); skipping", exc,
        )
        return filled_bytes, []

    from .docx_template import DocxTemplateService
    paragraphs = list(DocxTemplateService._iter_all_paragraphs(doc))

    try:
        substitutions = await _call_sonnet_for_grammar(
            suspect_paragraphs=suspect_paragraphs,
            cardinality_signals=cardinality_signals,
            resolved_values=resolved_values,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "TemplateGrammarFixer: Sonnet call failed (%s); skipping fix", exc,
        )
        return filled_bytes, []

    if not substitutions:
        logger.info(
            "TemplateGrammarFixer: LLM returned no substitutions across "
            "%d suspect paragraph(s); nothing to apply",
            len(suspect_paragraphs),
        )
        return filled_bytes, []

    by_paragraph: dict[int, list[_WordSubstitution]] = {}
    for sub in substitutions:
        by_paragraph.setdefault(sub.paragraph_index, []).append(sub)

    suspect_by_index = {s.template_paragraph_index: s for s in suspect_paragraphs}
    applied: list[GrammarRepairRecord] = []

    for idx, paragraph_subs in by_paragraph.items():
        if idx not in suspect_by_index:
            logger.warning(
                "TemplateGrammarFixer: LLM returned index %d not in suspect set; "
                "ignoring", idx,
            )
            continue
        if idx < 0 or idx >= len(paragraphs):
            continue

        paragraph_element = paragraphs[idx]._element
        t_elems = list(paragraph_element.iter(qn("w:t")))

        for sub in paragraph_subs:
            # PRIMARY CONTRACT — the LLM explicitly decided whether to
            # swap this flagged word. False means "I considered this
            # and concluded the original is correct" (typical case:
            # subject-verb agreement where the verb's subject is a
            # plural noun other than the cardinality-sensitive party).
            # Skip silently — this isn't an error, it's the LLM doing
            # its job and telling us not to touch it.
            if not sub.replace_original:
                logger.info(
                    "TemplateGrammarFixer: paragraph %d — LLM kept %r "
                    "as-is (would-be swap: %r) — %s",
                    idx, sub.original_word, sub.replacement_word,
                    sub.reason or "no reason given",
                )
                continue
            # Belt-and-suspenders: even when replace_original=True,
            # reject if the reason contains hedging language. Catches
            # the case where the LLM sets the bool wrong but the
            # natural-language reason reveals the right decision.
            if _reason_hedges_against_swap(sub.reason):
                logger.warning(
                    "TemplateGrammarFixer: rejecting swap %r → %r in "
                    "paragraph %d — reason contains hedging language "
                    "(LLM reasoned the swap shouldn't apply but emitted "
                    "it anyway). reason=%r",
                    sub.original_word, sub.replacement_word, idx,
                    sub.reason,
                )
                continue
            # LLM occasionally bundles trailing/leading punctuation
            # into the "word" (e.g. "Debtors." instead of "Debtors").
            # Strip matching punctuation from both sides so the
            # allowlist + apply see the bare word tokens. Mismatched
            # punctuation is still rejected — we never want to silently
            # eat a period or comma the LLM added or dropped.
            stripped = _strip_matching_outer_punctuation(
                sub.original_word, sub.replacement_word,
            )
            if stripped is None:
                logger.warning(
                    "TemplateGrammarFixer: rejecting swap %r → %r in "
                    "paragraph %d (punctuation around the word differs "
                    "between original and replacement)",
                    sub.original_word, sub.replacement_word, idx,
                )
                continue
            original, replacement = stripped
            if not _is_allowed_agreement_swap(original, replacement):
                logger.warning(
                    "TemplateGrammarFixer: rejecting non-allowlist swap "
                    "%r → %r in paragraph %d (not in agreement allowlist "
                    "or case style mismatch)",
                    original, replacement, idx,
                )
                continue
            count = _replace_word_token_in_t_elements(
                t_elems, original, replacement,
            )
            if count == 0:
                logger.warning(
                    "TemplateGrammarFixer: paragraph %d — word %r not found "
                    "in any <w:t> element after typography normalization; "
                    "skipping (likely splits across runs or absent)",
                    idx, original,
                )
                continue
            preview = paragraphs[idx].text
            if len(preview) > _PARAGRAPH_PREVIEW_MAX:
                preview = preview[: _PARAGRAPH_PREVIEW_MAX - 1] + "…"
            applied.append(GrammarRepairRecord(
                paragraph_index=idx,
                original_word=original,
                replacement_word=replacement,
                occurrences=count,
                paragraph_preview=preview,
                reason=sub.reason or "",
            ))
            logger.info(
                "TemplateGrammarFixer: paragraph %d — %r → %r (%d "
                "occurrence%s) — %s",
                idx, original, replacement, count,
                "" if count == 1 else "s",
                sub.reason or "no reason given",
            )

    if not applied:
        return filled_bytes, []

    output = BytesIO()
    doc.save(output)
    output.seek(0)
    return output.read(), applied


async def _call_sonnet_for_grammar(
    *,
    suspect_paragraphs: list[GrammarSuspectParagraph],
    cardinality_signals: dict[str, str],
    resolved_values: dict[str, str],
) -> list[_WordSubstitution]:
    """Single Sonnet roundtrip. Returns a flat list of word-level
    substitutions across all suspect paragraphs (may be empty when
    the LLM judges every suspect paragraph is actually fine)."""
    prompt = _build_grammar_prompt(
        suspect_paragraphs=suspect_paragraphs,
        cardinality_signals=cardinality_signals,
        resolved_values=resolved_values,
    )

    llm = ChatAnthropic(
        model=CLAUDE_MODEL_STANDARD,
        max_tokens=_MAX_TOKENS,
    )
    cost_ctx = build_cost_context_for_agent(
        kind=_COST_KIND,
        agent_name="TemplateGrammarFixerV2",
        extra_metadata={
            "suspect_count": len(suspect_paragraphs),
            "cardinality_signals": cardinality_signals,
        },
    )
    callbacks: list[Any] = [CostTrackingCallback(cost_context=cost_ctx)]
    try:
        from src.core.studio_v2.observability import langfuse_callback
        lf_handler = langfuse_callback()
        if lf_handler is not None:
            callbacks.append(lf_handler)
    except Exception:  # noqa: BLE001
        pass

    chain = llm.with_structured_output(_GrammarCorrections).with_config({
        "run_name": "TemplateGrammarFixerV2",
        "tags": _TAGS,
        "callbacks": callbacks,
    })
    response = await chain.ainvoke(prompt)
    if response is None:
        return []
    if isinstance(response, _GrammarCorrections):
        return response.substitutions
    if isinstance(response, dict) and "substitutions" in response:
        return [
            _WordSubstitution(**s)
            for s in response.get("substitutions", [])
            if isinstance(s, dict)
        ]
    return []


def _build_grammar_prompt(
    *,
    suspect_paragraphs: list[GrammarSuspectParagraph],
    cardinality_signals: dict[str, str],
    resolved_values: dict[str, str],
) -> str:
    cardinality_block = "\n".join(
        f"  {var}: {sig}" for var, sig in sorted(cardinality_signals.items())
    ) or "  (none)"
    values_block = "\n".join(
        f"  [[{name}]] = {value!r}"
        for name, value in sorted(resolved_values.items())
        if value and value.strip()
    ) or "  (none)"
    suspects_block = "\n\n".join(
        f"--- paragraph_index={s.template_paragraph_index} ---\n"
        f"triggered_tokens: {', '.join(s.triggered_tokens)}\n"
        f"text:\n{s.paragraph_text}"
        for s in suspect_paragraphs
    )

    return f"""You are a surgical grammar-correction tool for legal
documents. You identify ONE WORD AT A TIME that needs an agreement
swap (singular ↔ plural) and emit the original word + its
replacement. You are not allowed to produce paragraph text. You
are not allowed to suggest case changes or whitespace changes.
You only emit word-pair substitutions.

A legal document was rendered by substituting resolved values into
a template. Some paragraphs contain plural-sensitive tokens (e.g.
"Debtors", "their", "have", "these") that may contradict the
resolved values — e.g. the template says "The Debtors, [[debtor_name]],
by and through their counsel" but only ONE debtor was resolved.

<cardinality_signals>
{cardinality_block}
</cardinality_signals>

(Signal values: "single" = one party resolved; "joint" = multiple;
"unknown" = no resolved value, treat as ambiguous.)

<resolved_values>
{values_block}
</resolved_values>

<suspect_paragraphs>
{suspects_block}
</suspect_paragraphs>

Your output is a flat list of `_WordSubstitution` entries. For EVERY
flagged plural-sensitive word in the suspect paragraphs, emit one
entry with your decision (whether to swap or keep). Do NOT silently
drop flagged words — emit a `_WordSubstitution` with
`replace_original=False` to record "I considered this and decided
the original is correct."

Each entry has:
  - paragraph_index: which suspect paragraph this applies to
    (must match one of the indices above)
  - original_word: the EXACT word as it appears in the paragraph
    text, case-preserved, apostrophes included
  - replacement_word: the singular/plural counterpart, in the
    SAME CASE STYLE as original_word — populated EVEN WHEN
    replace_original is False (the "what would the swap be" answer)
  - replace_original: TRUE if the swap should be applied to the
    docx; FALSE if you considered the word and decided the original
    is correct. THIS IS THE CONTRACT — the fixer will not look at
    reason to override this. Set it correctly.
  - reason: short AFFIRMATIVE clause matching your decision.
    Examples:
      True:  "single debtor; subject is debtor"
      True:  "single debtor; possessive form"
      False: "subject is 'differences' (plural); keep have"
      False: "singular they is legalese-standard; keep their"

SUBJECT-VERB AGREEMENT — REQUIRED CHECK BEFORE EMITTING ANY VERB
SWAP WITH replace_original=True:

Verbs agree with their grammatical SUBJECT, not with the party
whose cardinality changed. Before setting replace_original=True
on any verb swap (are/is, were/was, have/has, do/does), identify
what noun the verb is actually agreeing with in this sentence.

Patterns that look like they need a swap but DO NOT (emit with
replace_original=False):

- "Irreconcilable differences have arisen between the Debtor and..."
  → 'have' agrees with 'differences' (plural noun), NOT with
  'Debtor'. replace_original=False. reason: "subject is
  'differences' (plural); keep have".

- "The Debtor, the Creditors, and the Trustee are present"
  → 'are' agrees with the compound subject (multiple parties), NOT
  with 'Debtor' alone. replace_original=False. reason: "compound
  subject (multiple parties); keep are".

- "The claims have been filed by the Debtor"
  → 'have' agrees with 'claims' (plural noun), NOT with 'Debtor'.
  replace_original=False. reason: "subject is 'claims' (plural);
  keep have".

- "These exhibits are attached"
  → 'are' agrees with 'exhibits' (plural noun), NOT with the
  cardinality-sensitive party. replace_original=False. reason:
  "subject is 'exhibits' (plural); keep are".

Pronouns get NO subject-verb check because they're never swapped
(see PRONOUNS category below). Just emit replace_original=False
on any pronoun the validator flagged with a reason like
"singular they is legalese-standard; keep <pronoun>".

Allowed substitution categories (you may emit ONLY these — anything
else is rejected at apply time):

NOUNS (party names) — plural ↔ singular, including possessives:
  Debtors ↔ Debtor             Debtors' ↔ Debtor's
  Creditors ↔ Creditor         Creditors' ↔ Creditor's
  Trustees ↔ Trustee           Trustees' ↔ Trustee's
  Movants ↔ Movant             Movants' ↔ Movant's
  Petitioners ↔ Petitioner     Petitioners' ↔ Petitioner's
  Respondents ↔ Respondent     Respondents' ↔ Respondent's
  Plaintiffs ↔ Plaintiff       Plaintiffs' ↔ Plaintiff's
  Defendants ↔ Defendant       Defendants' ↔ Defendant's
  Claimants ↔ Claimant         Claimants' ↔ Claimant's
  Applicants ↔ Applicant       Applicants' ↔ Applicant's

PRONOUNS — NEVER SWAPPED. Legalese defaults to singular they
(`the Debtor, by and through their counsel`) regardless of the
resolved party's gender. The fixer will REJECT any pronoun swap
you emit. If the validator flagged a paragraph because of a
pronoun (their / they / them / themselves / theirs), emit an
entry with replace_original=False and the reason "singular they
is legalese-standard; keep <pronoun>". Do NOT attempt
their → his / her / its, they → he / she / it, them → him / her
/ it, themselves → himself / herself / itself, or any other
pronoun swap.

VERBS — plural ↔ singular:
  are ↔ is        were ↔ was
  have ↔ has      do ↔ does

DETERMINERS — plural ↔ singular:
  these ↔ this    those ↔ that

CASE STYLE PRESERVATION (critical):
  The replacement_word must have the SAME case style as
  original_word.
    "Debtors" (Title) → "Debtor" (Title), NOT "debtor"
    "DEBTORS" (UPPER) → "DEBTOR" (UPPER), NOT "Debtor"
    "DEBTORS'" (UPPER + apostrophe) → "DEBTOR'S" (UPPER + apostrophe)
    "debtors" (lower) → "debtor" (lower)
  Case style violations are REJECTED at apply time. The fixer will
  not change case on any word it doesn't substitute, so emitting
  a case-mismatched pair just drops the fix.

WHAT TO AVOID (these get rejected and your fix gets dropped):
  - Substituting any word NOT in the categories above (verbs like
    "filed" / "moves" / "hereby", adjectives, adverbs, prepositions).
  - Substituting a name, date, number, email, dollar amount,
    case number, docket number, or any factual content.
  - Substituting a heading/title word for case normalization
    (e.g. "MOTION" → "Motion"). NEVER touch case unless it's part
    of a real agreement swap.
  - Emitting a substitution where original_word doesn't literally
    appear in that paragraph's text.

WHAT TO OMIT entirely (do not include any entry):
  - Words that aren't in an agreement category (verbs like 'filed',
    adjectives, adverbs, prepositions, names, dates, numbers).

WHAT TO INCLUDE with replace_original=False (record your decision):
  - Plural-sensitive words you considered but determined are
    correct as-is (subject-verb agreement examples above; pronoun
    antecedents pointing at non-party plural nouns; joint-debtor
    cases where the plural matches).

If EVERY flagged word in every suspect paragraph turns out to be
correct as-is, return entries with replace_original=False for each
— do NOT return an empty list when there were flagged words to
consider.

Return JSON matching the `_GrammarCorrections` schema.
"""


def _replace_word_token_in_t_elements(
    t_elems, old_word: str, new_word: str,
) -> int:
    """Replace every word-token occurrence of `old_word` with
    `new_word` across all `<w:t>` elements.

    Three matching passes, from cheapest to most aggressive:

      1. Exact match: tokenize each `<w:t>.text`, replace matching
         tokens. Handles the common case where the whole word lives
         in one `<w:t>`.
      2. Apostrophe-variant match: the LLM emits "Debtors'" with a
         straight apostrophe (U+0027), but Word may have autoformatted
         the docx to use the curly U+2019. We normalize apostrophes
         on both sides for the comparison and rewrite the matched
         token in place (preserving the docx's original apostrophe
         style if possible).
      3. Cross-`<w:t>` match: when the word spans multiple `<w:t>`
         elements (mid-word formatting splits the run), we
         concatenate the run texts, locate the word boundary, and
         redistribute the replacement across the original element
         slots — preserving every other character. Apostrophe
         normalization applies here too.

    "Word-token" boundaries match `_WORD_TOKEN_RE` so replacing
    "Debtors" never accidentally matches inside "Debtors'".

    Run-level formatting (`<w:rPr>` siblings) is untouched — we only
    mutate `<w:t>.text` character content. Bold / underline / italic
    / font / color all survive.

    Returns the total number of token replacements made across all
    passes. 0 means the word wasn't found anywhere — caller logs +
    skips.
    """
    total = 0

    # Pass 1 — exact match per <w:t>.
    for elem in t_elems:
        if not elem.text or old_word not in elem.text:
            continue
        tokens = _WORD_TOKEN_RE.findall(elem.text)
        if old_word not in tokens:
            continue
        count = tokens.count(old_word)
        elem.text = "".join(
            new_word if t == old_word else t
            for t in tokens
        )
        total += count
    if total > 0:
        return total

    # Pass 2 — apostrophe-variant match per <w:t>.
    old_normalized = _normalize_apostrophes(old_word)
    for elem in t_elems:
        if not elem.text:
            continue
        elem_normalized = _normalize_apostrophes(elem.text)
        if old_normalized not in elem_normalized:
            continue
        norm_tokens = _WORD_TOKEN_RE.findall(elem_normalized)
        if old_normalized not in norm_tokens:
            continue
        raw_tokens = _WORD_TOKEN_RE.findall(elem.text)
        new_pieces: list[str] = []
        count = 0
        for raw, norm in zip(raw_tokens, norm_tokens):
            if norm == old_normalized:
                new_pieces.append(new_word)
                count += 1
            else:
                new_pieces.append(raw)
        if count > 0:
            elem.text = "".join(new_pieces)
            total += count
    if total > 0:
        return total

    # Pass 3 — cross-`<w:t>` match. Concatenate, find, redistribute.
    return _replace_word_across_t_elements(t_elems, old_word, new_word)


def _replace_word_across_t_elements(
    t_elems, old_word: str, new_word: str,
) -> int:
    """Locate `old_word` (apostrophe-normalized) spanning multiple
    `<w:t>` elements, and replace it by redistributing the new word
    across the same element slots.

    Used when mid-word formatting splits a word across runs (e.g.
    `<w:t>The Debt</w:t><w:t>ors</w:t>`). We rebuild only the
    affected slice of each `<w:t>` so untouched prefix / suffix
    characters keep their original run.

    Returns the number of replacements made (0 if the word isn't
    found even with cross-run matching).
    """
    if not t_elems:
        return 0
    pieces = [(elem, elem.text or "") for elem in t_elems]
    full_text = "".join(p[1] for p in pieces)
    full_normalized = _normalize_apostrophes(full_text)
    old_normalized = _normalize_apostrophes(old_word)

    total = 0
    search_from = 0
    while True:
        hit = full_normalized.find(old_normalized, search_from)
        if hit < 0:
            break
        end = hit + len(old_normalized)
        # Word-boundary check: the chars on either side of the hit
        # must not be word chars (per `_WORD_TOKEN_RE`'s definition,
        # i.e. letters or apostrophes). Otherwise we'd hit substrings
        # like "Debtors" inside "redebtors".
        if hit > 0 and _is_wordlike_char(full_normalized[hit - 1]):
            search_from = hit + 1
            continue
        if end < len(full_normalized) and _is_wordlike_char(full_normalized[end]):
            search_from = hit + 1
            continue

        # Find which (elem, offset_within_elem) covers each char in
        # [hit, end). We rewrite only the affected portion of each
        # affected element so unaffected prefix / suffix chars stay
        # in their original runs (and keep their formatting).
        cursor = 0
        changed_any = False
        for i, (elem, text) in enumerate(pieces):
            elem_start = cursor
            elem_end = cursor + len(text)
            if elem_end <= hit or elem_start >= end:
                cursor = elem_end
                continue
            # Overlap with [hit, end).
            local_hit = max(hit, elem_start) - elem_start
            local_end = min(end, elem_end) - elem_start
            if i == 0 or elem_start <= hit < elem_end:
                # First overlapping element absorbs the full new_word.
                if elem_start <= hit < elem_end:
                    new_chunk = (
                        text[:local_hit] + new_word + text[local_end:]
                    )
                else:
                    new_chunk = text[:local_hit] + text[local_end:]
            else:
                # Subsequent overlapping elements drop the covered
                # portion (new_word already placed in the first one).
                new_chunk = text[:local_hit] + text[local_end:]
            if new_chunk != text:
                pieces[i] = (elem, new_chunk)
                changed_any = True
            cursor = elem_end

        if changed_any:
            total += 1
            # Re-build full strings for subsequent search iterations.
            full_text = "".join(p[1] for p in pieces)
            full_normalized = _normalize_apostrophes(full_text)
            # Advance past the replacement.
            search_from = hit + len(new_word)
        else:
            search_from = hit + 1

    if total > 0:
        for elem, text in pieces:
            elem.text = text
    return total


def _is_wordlike_char(ch: str) -> bool:
    return ch.isalpha() or ch in "'‘’"


def _normalize_apostrophes(text: str) -> str:
    return text.translate(_APOSTROPHE_NORMALIZE)


def _strip_matching_outer_punctuation(
    original: str, replacement: str,
) -> tuple[str, str] | None:
    """If `original` and `replacement` carry the SAME leading and
    trailing punctuation, return them with that punctuation stripped.

    Common LLM error: emits `("Debtors.", "Debtor.")` instead of
    `("Debtors", "Debtor")` — same period on both sides, semantically
    just an agreement swap with the period as context. Strip + retry.

    Returns `None` when leading/trailing punctuation differs (means
    the LLM is trying to mutate punctuation as part of the fix —
    rejected to avoid silently eating a comma or period).
    """
    orig_lead, orig_core, orig_trail = _split_outer_punctuation(original)
    rep_lead, rep_core, rep_trail = _split_outer_punctuation(replacement)
    if orig_lead != rep_lead or orig_trail != rep_trail:
        return None
    if not orig_core or not rep_core:
        return None
    return orig_core, rep_core


def _reason_hedges_against_swap(reason: str) -> bool:
    """Whether the LLM's `reason` field contains a phrase indicating
    the LLM reasoned itself out of the swap but emitted it anyway.

    The prompt instructs the LLM that the `reason` field is a
    commitment — affirmative justifications only ("single debtor;
    subject is debtor"). Substitutions where the LLM emits the swap
    AND simultaneously writes "but wait, this is grammatically
    correct" are rejected here as a deterministic backstop.
    """
    if not reason:
        return False
    lower = reason.lower()
    return any(phrase in lower for phrase in _HEDGING_REASON_PHRASES)


def _split_outer_punctuation(word: str) -> tuple[str, str, str]:
    """Returns `(leading_punct, core, trailing_punct)`. `core` keeps
    inner apostrophes (Debtor's stays whole) but drops surrounding
    non-letter/apostrophe characters."""
    start = 0
    while start < len(word) and not _is_wordlike_char(word[start]):
        start += 1
    end = len(word)
    while end > start and not _is_wordlike_char(word[end - 1]):
        end -= 1
    return word[:start], word[start:end], word[end:]


def _is_allowed_agreement_swap(old: str, new: str) -> bool:
    """Whether the (old, new) word substitution is in the explicit
    agreement allowlist AND preserves the original's case style.

    Apostrophe-normalized + lowercased pair must appear in
    `_AGREEMENT_PAIRS`. Case style of `old` (`upper` / `lower` /
    `title` / `mixed`) must match `new` so an ALL CAPS heading swap
    ("DEBTORS'" → "DEBTOR'S") stays ALL CAPS rather than being
    "helpfully" title-cased.
    """
    pair = frozenset((_agreement_key(old), _agreement_key(new)))
    if pair not in _AGREEMENT_PAIRS:
        return False
    return _case_style(old) == _case_style(new)


def _agreement_key(word: str) -> str:
    """Lowercase + normalize curly apostrophes to straight `'` so
    pair lookups treat `Debtors'` / `DEBTORS’` / `debtors'` as the
    same key shape."""
    return word.lower().translate(_APOSTROPHE_NORMALIZE)


def _case_style(word: str) -> str:
    """Classify a word's case style by its alphabetic characters.

    Returns one of "upper" / "lower" / "title" / "mixed" / "none".
    Non-letters (digits, apostrophes, hyphens) are ignored for the
    classification but stay in the word otherwise.
    """
    letters = [c for c in word if c.isalpha()]
    if not letters:
        return "none"
    if all(c.isupper() for c in letters):
        return "upper"
    if all(c.islower() for c in letters):
        return "lower"
    if letters[0].isupper() and all(c.islower() for c in letters[1:]):
        return "title"
    return "mixed"
