"""Tests for case-scope enforcement on gmail_search.

Verifies that the wrapper's case-number variant generation + scope
clause building behave correctly. The actual LangChain GmailSearch
call is integration-tested separately — these tests cover the
deterministic helpers that mutate the query before it hits Gmail.
"""

from __future__ import annotations

import pytest

from src.core.studio_v2.tools.gmail_search import (
    apply_case_scope_to_query,
    build_case_scope_clause,
    case_number_variants,
)


@pytest.mark.unit
@pytest.mark.parametrize(
    "case_number,expected",
    [
        # Canonical bk format: year-NUM-judge
        ("26-15038-PDR", ["26-15038-PDR", "26-15038"]),
        # No judge initials suffix
        ("26-15038", ["26-15038"]),
        # District prefix (Florida Middle: 8:)
        ("8:26-bk-15038-PDR", ["8:26-bk-15038-PDR", "8:26-bk-15038", "26-15038-PDR", "26-15038"]),
        # District prefix, no judge
        ("8:26-bk-15038", ["8:26-bk-15038", "26-15038"]),
        # Civil case prefix
        ("1:24-cv-04200-RDB", ["1:24-cv-04200-RDB", "1:24-cv-04200", "24-04200-RDB", "24-04200"]),
        # Stripped whitespace
        ("  26-15038-PDR  ", ["26-15038-PDR", "26-15038"]),
        # None / empty
        (None, []),
        ("", []),
        ("   ", []),
    ],
)
def test_case_number_variants(case_number, expected):
    """Variants are generated longest-first so display order is sane."""
    assert case_number_variants(case_number) == expected


@pytest.mark.unit
def test_build_case_scope_clause_single_variant():
    """A case_number with no strippable parts produces a single quoted token."""
    assert build_case_scope_clause("26-15038") == '"26-15038"'


@pytest.mark.unit
def test_build_case_scope_clause_multiple_variants():
    """Multiple variants are joined as a parenthesized OR-group."""
    clause = build_case_scope_clause("26-15038-PDR")
    assert clause == '("26-15038-PDR" OR "26-15038")'


@pytest.mark.unit
def test_build_case_scope_clause_empty():
    """No case_number → empty clause (caller skips scoping)."""
    assert build_case_scope_clause(None) == ""
    assert build_case_scope_clause("") == ""


@pytest.mark.unit
def test_apply_case_scope_appends_clause():
    """Original Gmail operators stay intact; clause is AND-ed at the end."""
    out = apply_case_scope_to_query(
        'from:notices@cmecf.uscourts.gov subject:"proof of claim"',
        "26-15038-PDR",
    )
    assert out == (
        'from:notices@cmecf.uscourts.gov subject:"proof of claim" '
        '("26-15038-PDR" OR "26-15038")'
    )


@pytest.mark.unit
def test_apply_case_scope_skips_when_variant_already_present():
    """If LLM already included a variant, don't double-scope."""
    out = apply_case_scope_to_query("subject:claim 26-15038", "26-15038-PDR")
    assert out == "subject:claim 26-15038"


@pytest.mark.unit
def test_apply_case_scope_skips_when_no_case_number():
    """No case_number → query passes through unchanged."""
    out = apply_case_scope_to_query("subject:claim", None)
    assert out == "subject:claim"


@pytest.mark.unit
def test_apply_case_scope_empty_user_query():
    """An empty user query becomes just the clause."""
    out = apply_case_scope_to_query("", "26-15038-PDR")
    assert out == '("26-15038-PDR" OR "26-15038")'
