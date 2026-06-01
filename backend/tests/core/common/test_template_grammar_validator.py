"""Tests for the Tier 1 deterministic grammar validator.

The validator walks the filled docx, infers cardinality signals from
the resolved values, and flags paragraphs with plural-sensitive
tokens when at least one party resolved as single. Pure-Python; no
LLM calls in these tests.
"""

from io import BytesIO

import pytest
from docx import Document

from src.core.common.documents.template_grammar_validator import (
    GrammarSuspectParagraph,
    _infer_cardinality_signals,
    _looks_like_multi_name,
    _scan_plural_tokens,
    validate_fill_grammar,
)


def _build_docx(paragraphs: list[str]) -> bytes:
    doc = Document()
    for text in paragraphs:
        doc.add_paragraph(text)
    buf = BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf.read()


# === _scan_plural_tokens ===


@pytest.mark.unit
def test_scan_plural_tokens_picks_up_obvious_plurals():
    text = "The Debtors, by and through their counsel, have filed"
    found = _scan_plural_tokens(text)
    assert "debtors" in found
    assert "their" in found
    assert "have" in found


@pytest.mark.unit
def test_scan_plural_tokens_distinguishes_their_from_there():
    """Word boundaries matter — 'there' is not 'their'."""
    text = "There is no objection."
    found = _scan_plural_tokens(text)
    assert "their" not in found
    assert "there" not in found  # 'there' isn't in our plural set anyway


@pytest.mark.unit
def test_scan_plural_tokens_case_insensitive():
    text = "DEBTORS Their HAVE"
    found = _scan_plural_tokens(text)
    assert {"debtors", "their", "have"}.issubset(found)


@pytest.mark.unit
def test_scan_plural_tokens_empty_on_clean_text():
    text = "The Debtor, by and through his counsel, has filed"
    found = _scan_plural_tokens(text)
    assert found == set()


# === _looks_like_multi_name ===


@pytest.mark.unit
def test_looks_like_multi_name_two_capitalized_with_and():
    assert _looks_like_multi_name("Robert Creswell and Lori Creswell")


@pytest.mark.unit
def test_looks_like_multi_name_two_capitalized_with_ampersand():
    assert _looks_like_multi_name("Robert Creswell & Lori Creswell")


@pytest.mark.unit
def test_looks_like_multi_name_solo_name_with_and_in_text_skips():
    """'Andrew' is one capitalized token; 'and' isn't a joiner here."""
    assert not _looks_like_multi_name("Andrew Carnegie")


@pytest.mark.unit
def test_looks_like_multi_name_single_name_skips():
    assert not _looks_like_multi_name("Judith S. Schwartz")


# === _infer_cardinality_signals ===


@pytest.mark.unit
def test_infer_cardinality_single_debtor_no_newline():
    signals = _infer_cardinality_signals({"debtor_name": "Judith S. Schwartz"})
    assert signals == {"debtor_name": "single"}


@pytest.mark.unit
def test_infer_cardinality_joint_debtor_via_newline():
    """v2 Rule 15: joint debtors get `\\n`-joined into one value."""
    signals = _infer_cardinality_signals(
        {"debtor_name": "Robert Creswell\nLori Creswell"},
    )
    assert signals == {"debtor_name": "joint"}


@pytest.mark.unit
def test_infer_cardinality_joint_debtor_via_and_joiner():
    signals = _infer_cardinality_signals(
        {"debtor_name": "Robert Creswell and Lori Creswell"},
    )
    assert signals == {"debtor_name": "joint"}


@pytest.mark.unit
def test_infer_cardinality_empty_value_is_unknown():
    signals = _infer_cardinality_signals({"debtor_name": ""})
    assert signals == {"debtor_name": "unknown"}


@pytest.mark.unit
def test_infer_cardinality_ignores_non_cardinality_vars():
    """`case_number` isn't a cardinality-sensitive variable."""
    signals = _infer_cardinality_signals({
        "case_number": "26-10700",
        "petition_filing_date": "April 30, 2026",
    })
    assert signals == {}


@pytest.mark.unit
def test_infer_cardinality_multiple_parties_independent():
    signals = _infer_cardinality_signals({
        "debtor_name": "Judith S. Schwartz",
        "trustee_name": "Robin R. Weiner",
        "case_number": "26-10700",  # ignored
    })
    assert signals == {
        "debtor_name": "single",
        "trustee_name": "single",
    }


# === validate_fill_grammar ===


@pytest.mark.unit
def test_validate_flags_paragraph_with_plurals_when_single_debtor():
    """JUDITH SCHWARTZ + 'Debtors.' label — classic single-vs-plural
    mismatch."""
    filled = _build_docx([
        "JUDITH S SCHWARTZ",
        "Debtors.",
        "The Debtors, Judith S. Schwartz, by and through their counsel",
    ])
    result = validate_fill_grammar(
        filled_bytes=filled,
        resolved_values={"debtor_name": "Judith S. Schwartz"},
    )
    assert not result.ok
    flagged = {s.template_paragraph_index for s in result.suspect_paragraphs}
    assert 1 in flagged  # "Debtors." label
    assert 2 in flagged  # "The Debtors ... their" body line
    assert 0 not in flagged  # header has no plural tokens


@pytest.mark.unit
def test_validate_skips_when_debtor_is_joint():
    """Joint debtor → 'Debtors' is correct → no flagging, no LLM call."""
    filled = _build_docx([
        "The Debtors, Robert Creswell and Lori Creswell, have filed",
    ])
    result = validate_fill_grammar(
        filled_bytes=filled,
        resolved_values={"debtor_name": "Robert Creswell\nLori Creswell"},
    )
    assert result.ok
    assert result.suspect_paragraphs == []


@pytest.mark.unit
def test_validate_skips_when_no_cardinality_signals():
    """No cardinality-sensitive variables in resolved set → skip
    (template's plural language is presumed intentional)."""
    filled = _build_docx(["The Debtors have filed their motion"])
    result = validate_fill_grammar(
        filled_bytes=filled,
        resolved_values={"case_number": "26-10700"},
    )
    assert result.ok
    assert "No cardinality-sensitive" in result.summary


@pytest.mark.unit
def test_validate_skips_paragraphs_without_plural_tokens():
    """Single debtor + ONE paragraph with no plurals → no suspects."""
    filled = _build_docx([
        "Judith S. Schwartz, Debtor.",
        "Dated this 28th day of May, 2026.",
    ])
    result = validate_fill_grammar(
        filled_bytes=filled,
        resolved_values={"debtor_name": "Judith S. Schwartz"},
    )
    assert result.ok


@pytest.mark.unit
def test_validate_returns_cardinality_signals_for_fixer():
    """The fixer needs the per-variable signals to build the prompt."""
    filled = _build_docx(["The Debtors have filed"])
    result = validate_fill_grammar(
        filled_bytes=filled,
        resolved_values={"debtor_name": "Judith S. Schwartz"},
    )
    assert result.cardinality_signals == {"debtor_name": "single"}


@pytest.mark.unit
def test_validate_includes_triggered_tokens_in_suspect():
    filled = _build_docx(["The Debtors, by their counsel, have filed"])
    result = validate_fill_grammar(
        filled_bytes=filled,
        resolved_values={"debtor_name": "Judith S. Schwartz"},
    )
    assert not result.ok
    suspect = result.suspect_paragraphs[0]
    assert "debtors" in suspect.triggered_tokens
    assert "their" in suspect.triggered_tokens
    assert "have" in suspect.triggered_tokens


@pytest.mark.unit
def test_validate_skips_blank_paragraphs():
    filled = _build_docx([
        "JUDITH S SCHWARTZ",
        "",  # blank — no scan
        "The Debtors have filed",
    ])
    result = validate_fill_grammar(
        filled_bytes=filled,
        resolved_values={"debtor_name": "Judith S. Schwartz"},
    )
    assert not result.ok
    flagged = {s.template_paragraph_index for s in result.suspect_paragraphs}
    assert 1 not in flagged  # blank skipped


@pytest.mark.unit
def test_validate_returns_grammar_suspect_paragraph_dataclass():
    """Defensive type check — fixer consumes this shape directly."""
    filled = _build_docx(["The Debtors have filed"])
    result = validate_fill_grammar(
        filled_bytes=filled,
        resolved_values={"debtor_name": "Judith S. Schwartz"},
    )
    assert isinstance(result.suspect_paragraphs[0], GrammarSuspectParagraph)


@pytest.mark.unit
def test_validate_parse_failure_returns_ok_true():
    """Corrupt docx bytes → soft-fail; ok=True so finalizer doesn't
    invoke the fixer over garbage."""
    result = validate_fill_grammar(
        filled_bytes=b"this is not a docx",
        resolved_values={"debtor_name": "Judith S. Schwartz"},
    )
    assert result.ok
    assert "Parse failure" in result.summary
