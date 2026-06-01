"""System-prompt builder: ensures case identity is rendered + tool-use rules surface."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.core.agents.llm.chat.prompts import build_system_prompt


@pytest.mark.unit
def test_prompt_renders_case_number_and_name():
    case = SimpleNamespace(
        case_number="26-10700",
        case_name="In re Doe",
        chapter=13,
        court_district="FLSB",
    )
    prompt = build_system_prompt(case)
    assert "26-10700" in prompt
    assert "In re Doe" in prompt
    assert "Chapter 13" in prompt
    assert "FLSB" in prompt
    # Tool-use ordering rules surface.
    assert "case_vector_search" in prompt
    assert "petition_vision_lookup" in prompt


@pytest.mark.unit
def test_prompt_handles_missing_chapter_and_district():
    case = SimpleNamespace(
        case_number="26-10700",
        case_name="In re Doe",
        chapter=None,
        court_district=None,
    )
    prompt = build_system_prompt(case)
    assert "Chapter" not in prompt
    # Empty values shouldn't leak as 'None'.
    assert "None" not in prompt


@pytest.mark.unit
def test_prompt_steers_email_questions_to_gmail_search_by_default():
    """Email questions — especially \"most recent ___\" — should default
    to `gmail_search` (Gmail API directly, freshness-sortable). The
    case-scoped `case_emails_search` is restrictive (subject must contain
    the case number) and misses ordinary correspondence. The prompt must
    make this default explicit so the agent doesn't reach for
    case_emails_search first."""
    case = SimpleNamespace(
        case_number="26-10700", case_name="In re Doe", chapter=13, court_district="FLSB",
    )
    prompt = build_system_prompt(case)
    assert "gmail_search" in prompt
    # Either "most recent" or "freshness" hints are in the prompt body.
    assert "most recent" in prompt or "freshness" in prompt.lower()


@pytest.mark.unit
def test_prompt_includes_web_search_fallback_rule():
    """When the case file doesn't carry the answer AND the question is
    about publicly-available info (circuit number, statute, etc.), the
    agent must automatically call `web_search` instead of telling
    counsel \"not available.\""""
    case = SimpleNamespace(
        case_number="26-10700", case_name="In re Doe", chapter=13, court_district="FLSB",
    )
    prompt = build_system_prompt(case)
    assert "web_search" in prompt
    # The concrete worked example (circuit number) is in the prompt so
    # the agent has a pattern to match.
    assert "circuit number" in prompt
    # Explicit "before telling" phrasing locks the fallback behavior in.
    assert "before telling" in prompt.lower()


@pytest.mark.unit
def test_prompt_instructs_third_person_debtor_voice():
    """The agent must refer to the debtor in the third person.

    Counsel / the paralegal is the one chatting; the debtor is the user's
    client. Slipping into second-person ("your schedules…") sounds like
    the chat is addressed to the debtor, which is wrong on register and
    confusing. The prompt has to make this explicit.
    """
    case = SimpleNamespace(
        case_number="26-10700",
        case_name="In re Doe",
        chapter=13,
        court_district="FLSB",
    )
    prompt = build_system_prompt(case).lower()
    assert "third person" in prompt
    # Worked examples of the right voice are in the prompt body.
    assert "the debtor" in prompt
    assert "the client" in prompt
    # And the explicit rule against second-person debtor references.
    assert "never" in prompt
    assert "counsel" in prompt
