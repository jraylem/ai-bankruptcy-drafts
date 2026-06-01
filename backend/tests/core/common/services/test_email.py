"""Tests for the Gmail / CourtDrive query builders in services/email.py."""

import pytest

from src.core.common.services.email import _build_gmail_query


@pytest.mark.unit
def test_build_gmail_query_uses_word_and_subject_match():
    """subject_query renders as `subject:(...)` (word-AND match), not the
    legacy `subject:"..."` phrase form. Word-AND is stemming-aware and
    tolerates token-boundary glue like 'ClaimCh-13' that breaks phrase
    search."""
    query = _build_gmail_query(
        subject_query="Proof of Claim",
        body_query=None,
        case_number=None,
    )
    assert query == "subject:(Proof of Claim)"


@pytest.mark.unit
def test_build_gmail_query_combines_subject_body_and_case_number():
    """Subject is unquoted (word-AND); body and case-number variants stay
    phrase-quoted because their semantics rely on adjacent-token match."""
    query = _build_gmail_query(
        subject_query="Proof of Claim",
        body_query="trustee",
        case_number="26-10700",
    )
    assert query.startswith("subject:(Proof of Claim) ")
    assert '"trustee"' in query
    assert '"26-10700"' in query
    assert '"26-bk-10700"' in query


@pytest.mark.unit
def test_build_gmail_query_returns_empty_when_all_fields_blank():
    assert _build_gmail_query(None, None, None) == ""


@pytest.mark.unit
def test_build_gmail_query_wraps_case_number_in_subject_when_requested():
    """`case_emails_search` passes `case_number_in_subject=True` so the
    case number must appear in the subject line — body matches across
    forwarded threads that mention an unrelated case number used to
    pollute the chat-tool's results."""
    query = _build_gmail_query(
        subject_query=None,
        body_query=None,
        case_number="26-10700",
        case_number_in_subject=True,
    )
    # The OR-clause is wrapped in `subject:` so neither variant matches
    # body-only mentions.
    assert query.startswith("subject:(")
    assert '"26-10700"' in query
    assert '"26-bk-10700"' in query


@pytest.mark.unit
def test_build_gmail_query_default_keeps_case_number_anywhere():
    """Default behavior unchanged for non-chat callers — case number
    matches anywhere in the message body or subject."""
    query = _build_gmail_query(
        subject_query=None,
        body_query=None,
        case_number="26-10700",
    )
    assert not query.startswith("subject:(")
    assert '"26-10700"' in query
    assert '"26-bk-10700"' in query
