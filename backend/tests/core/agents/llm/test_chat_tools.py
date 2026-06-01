"""Behavioral tests for the three initial chat-agent tools."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.core.agents.llm.chat.tools.base import ToolContext
from src.core.agents.llm.chat.tools.case_emails_search import CaseEmailsSearchTool
from src.core.agents.llm.chat.tools.gmail_search import GmailSearchTool
from src.core.agents.llm.chat.tools.case_vector_search import CaseVectorSearchTool
from src.core.agents.llm.chat.tools.petition_vision import PetitionVisionLookupTool


def _make_ctx(*, petition_pdf_url: str | None = "https://x/r2/case.pdf") -> ToolContext:
    case = SimpleNamespace(
        id="26_10700",
        case_name="In re Doe",
        case_number="26-10700",
        chapter=13,
        court_district="FLSB",
        petition_pdf_url=petition_pdf_url,
        case_file_collection="case_file_26_10700",
        gmail_collection="gmail_emails_26_10700",
        courtdrive_collection="courtdrive_emails_26_10700",
    )
    return ToolContext(user_id="user-1", case=case)


# ─── case_vector_search ───────────────────────────────────────────────


@pytest.mark.unit
async def test_case_vector_search_returns_results_with_relevance(monkeypatch):
    fake_search = AsyncMock(return_value=SimpleNamespace(
        total=2,
        results=[
            SimpleNamespace(content="Schedule F shows 12 unsecured creditors.", relevance_score=0.91),
            SimpleNamespace(content="Plan term: 60 months.", relevance_score=0.74),
        ],
    ))
    monkeypatch.setattr(
        "src.core.agents.llm.chat.tools.case_vector_search.ToolBox.query_case_specific",
        fake_search,
    )

    out = await CaseVectorSearchTool.invoke(_make_ctx(), query="unsecured creditors", k=3)

    fake_search.assert_awaited_once_with(
        collection_name="case_file_26_10700", query="unsecured creditors", k=3,
    )
    assert out["total"] == 2
    assert len(out["results"]) == 2
    assert out["results"][0]["relevance_score"] == 0.91


@pytest.mark.unit
async def test_case_vector_search_returns_error_envelope_on_exception(monkeypatch):
    async def boom(*_a, **_kw):
        raise RuntimeError("pgvector unreachable")

    monkeypatch.setattr(
        "src.core.agents.llm.chat.tools.case_vector_search.ToolBox.query_case_specific",
        boom,
    )

    out = await CaseVectorSearchTool.invoke(_make_ctx(), query="anything")
    assert out["total"] == 0
    assert out["results"] == []
    assert "error" in out


# ─── case_emails_search ───────────────────────────────────────────────


@pytest.mark.unit
async def test_case_emails_search_threads_case_number_and_always_uses_gmail(monkeypatch):
    """case_emails_search is gmail-only now (court_drive option retired).
    The case number is auto-applied AND restricted to the subject line
    so forwarded-body case-number mentions don't pollute results."""
    captured = {}

    async def fake_query(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            total=1,
            emails=[
                SimpleNamespace(
                    id="m1",
                    subject="Trustee notice",
                    sender="trustee@example.gov",
                    date="Mon, 1 May 2026",
                    body="Body" * 800,
                )
            ],
        )

    monkeypatch.setattr(
        "src.core.agents.llm.chat.tools.case_emails_search.ToolBox.query_email",
        fake_query,
    )

    out = await CaseEmailsSearchTool.invoke(
        _make_ctx(),
        subject_query="trustee",
        body_query=None,
        max_results=4,
    )
    # Backend always called with Gmail — court_drive option no longer exposed.
    assert captured["email_type"].value == "gmail"
    assert captured["case_number"] == "26-10700"
    # Case-number scoping must be SUBJECT-ONLY for the case-scoped tool.
    # Body-anywhere matching pulled in forwarded threads that mentioned
    # an unrelated case number and polluted results.
    assert captured["case_number_in_subject"] is True
    assert out["total"] == 1
    assert out["emails"][0]["subject"] == "Trustee notice"
    # Body is truncated for prompt-size hygiene.
    assert len(out["emails"][0]["body"]) <= 2000


@pytest.mark.unit
async def test_case_emails_search_handles_failure(monkeypatch):
    async def boom(**_kw):
        raise RuntimeError("gmail api 500")

    monkeypatch.setattr(
        "src.core.agents.llm.chat.tools.case_emails_search.ToolBox.query_email",
        boom,
    )
    out = await CaseEmailsSearchTool.invoke(_make_ctx(), body_query="trustee")
    assert out["total"] == 0
    assert "error" in out


@pytest.mark.unit
def test_case_emails_search_input_schema_drops_email_type():
    """email_type field was retired — the schema must not advertise it
    to the LLM anymore. Otherwise the agent will keep trying to pass
    \"court_drive\" and trip Pydantic validation."""
    spec = CaseEmailsSearchTool.to_langchain_tool()
    properties = spec["input_schema"].get("properties", {})
    assert "email_type" not in properties


@pytest.mark.unit
def test_case_emails_search_description_steers_agent_to_body_query():
    """Regression guard: the tool description and field-descriptions must
    point the agent at `body_query` as the default. The old wording made
    `subject_query` look like the safe default and the agent rarely
    populated `body_query` at all, so body-only mentions were missed."""
    spec = CaseEmailsSearchTool.to_langchain_tool()
    assert "body_query" in spec["description"]
    assert "USAGE" in spec["description"]
    props = spec["input_schema"]["properties"]
    assert "PRIMARY" in props["body_query"]["description"]
    assert "rare" in props["subject_query"]["description"].lower()


# ─── gmail_search ────────────────────────────────────────────────────


@pytest.mark.unit
async def test_gmail_search_passes_no_case_number_to_query(monkeypatch):
    """Hallmark of gmail_search: case_number is explicitly None so Gmail
    isn't scoped to the chat's current case."""
    captured = {}

    async def fake_query(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            total=2,
            emails=[
                SimpleNamespace(
                    id="m1",
                    subject="Hi",
                    sender="opp@example.com",
                    date="Mon, 1 May 2026",
                    body="body",
                ),
                SimpleNamespace(
                    id="m2",
                    subject="Hello",
                    sender="opp@example.com",
                    date="Mon, 1 May 2026",
                    body="body2",
                ),
            ],
        )

    monkeypatch.setattr(
        "src.core.agents.llm.chat.tools.gmail_search.ToolBox.query_email",
        fake_query,
    )
    out = await GmailSearchTool.invoke(
        _make_ctx(), subject_query="opposing counsel", max_results=5,
    )
    assert captured["case_number"] is None
    assert captured["email_type"].value == "gmail"
    assert out["total"] == 2
    assert out["emails"][0]["subject"] == "Hi"


@pytest.mark.unit
async def test_gmail_search_rejects_empty_query():
    """Both subject_query and body_query empty → tool returns an error
    envelope without burning a Gmail API call."""
    out = await GmailSearchTool.invoke(_make_ctx())
    assert out["total"] == 0
    assert out["emails"] == []
    assert "at least one" in out["error"].lower()


@pytest.mark.unit
async def test_gmail_search_handles_failure(monkeypatch):
    async def boom(**_kw):
        raise RuntimeError("gmail api 500")

    monkeypatch.setattr(
        "src.core.agents.llm.chat.tools.gmail_search.ToolBox.query_email",
        boom,
    )
    out = await GmailSearchTool.invoke(_make_ctx(), body_query="trustee")
    assert out["total"] == 0
    assert "error" in out


@pytest.mark.unit
def test_gmail_search_description_steers_agent_to_body_query():
    """Same regression guard as `case_emails_search` — `gmail_search`
    must steer the agent at `body_query` as the default."""
    spec = GmailSearchTool.to_langchain_tool()
    assert "body_query" in spec["description"]
    assert "USAGE" in spec["description"]
    props = spec["input_schema"]["properties"]
    assert "PRIMARY" in props["body_query"]["description"]
    assert "rare" in props["subject_query"]["description"].lower()


# ─── petition_vision_lookup ──────────────────────────────────────────


@pytest.mark.unit
async def test_petition_vision_no_pdf_url_returns_error_without_calling_llm():
    out = await PetitionVisionLookupTool.invoke(
        _make_ctx(petition_pdf_url=None), question="anything",
    )
    assert out["answer"] is None
    assert "no petition_pdf_url" in out["error"].lower()


@pytest.mark.unit
async def test_petition_vision_fetch_failure_returns_error(monkeypatch):
    monkeypatch.setattr(
        "src.core.agents.llm.chat.tools.petition_vision.fetch_petition_pdf_bytes",
        AsyncMock(return_value=None),
    )
    out = await PetitionVisionLookupTool.invoke(_make_ctx(), question="anything")
    assert out["answer"] is None
    assert "could not download" in out["error"].lower()


@pytest.mark.unit
async def test_petition_vision_invokes_vision_llm_with_pdf_block(monkeypatch):
    monkeypatch.setattr(
        "src.core.agents.llm.chat.tools.petition_vision.fetch_petition_pdf_bytes",
        AsyncMock(return_value=b"%PDF-1.7 fake"),
    )

    captured = {}

    class _FakeLLM:
        def __init__(self, **kwargs):
            captured["init"] = kwargs

        def with_config(self, _config):
            return self

        async def ainvoke(self, messages):
            captured["messages"] = messages
            return SimpleNamespace(content=[
                {"type": "text", "text": "Box is checked for Chapter 7 on page 1."},
            ])

    monkeypatch.setattr(
        "src.core.agents.llm.chat.tools.petition_vision.ChatAnthropic",
        _FakeLLM,
    )

    out = await PetitionVisionLookupTool.invoke(
        _make_ctx(), question="Is the Chapter 7 box checked on page 1?",
    )

    assert "Box is checked" in (out["answer"] or "")
    # Confirm the document content block is present and base64 is non-empty.
    human_msg = captured["messages"][0]
    blocks = human_msg.content
    assert blocks[0]["type"] == "document"
    assert blocks[0]["source"]["media_type"] == "application/pdf"
    assert blocks[0]["source"]["data"]  # non-empty base64
    assert blocks[1]["type"] == "text"
    assert "Is the Chapter 7 box checked" in blocks[1]["text"]


@pytest.mark.unit
async def test_petition_vision_handles_string_content_response(monkeypatch):
    monkeypatch.setattr(
        "src.core.agents.llm.chat.tools.petition_vision.fetch_petition_pdf_bytes",
        AsyncMock(return_value=b"x"),
    )

    class _FakeLLM:
        def __init__(self, **kwargs):
            pass

        def with_config(self, _config):
            return self

        async def ainvoke(self, _messages):
            return SimpleNamespace(content="plain-string answer")

    monkeypatch.setattr(
        "src.core.agents.llm.chat.tools.petition_vision.ChatAnthropic",
        _FakeLLM,
    )

    out = await PetitionVisionLookupTool.invoke(_make_ctx(), question="anything")
    assert out["answer"] == "plain-string answer"


@pytest.mark.unit
async def test_petition_vision_handles_llm_exception(monkeypatch):
    monkeypatch.setattr(
        "src.core.agents.llm.chat.tools.petition_vision.fetch_petition_pdf_bytes",
        AsyncMock(return_value=b"x"),
    )

    class _BoomLLM:
        def __init__(self, **kwargs):
            pass

        def with_config(self, _config):
            return self

        async def ainvoke(self, _messages):
            raise RuntimeError("anthropic 500")

    monkeypatch.setattr(
        "src.core.agents.llm.chat.tools.petition_vision.ChatAnthropic",
        _BoomLLM,
    )

    out = await PetitionVisionLookupTool.invoke(_make_ctx(), question="x")
    assert out["answer"] is None
    assert "anthropic 500" in out["error"]


# ─── list_drafted_motions ─────────────────────────────────────────────


def _make_log(
    *,
    id: str = "log-1",
    user_id: str = "alice",
    template_name: str = "Motion to Extend Stay",
    status: str = "COMPLETED",
    draft_template_id: str = "t1",
    task_id: str | None = "task-1",
    r2_object_key: str | None = "r2/path.docx",
    error: str | None = None,
    created_at=None,
    updated_at=None,
):
    return SimpleNamespace(
        id=id,
        user_id=user_id,
        template_name=template_name,
        status=status,
        draft_template_id=draft_template_id,
        task_id=task_id,
        r2_object_key=r2_object_key,
        error=error,
        created_at=created_at,
        updated_at=updated_at,
    )


@pytest.mark.unit
async def test_list_drafted_motions_returns_summary_across_users(monkeypatch):
    from src.core.agents.llm.chat.tools.list_drafted_motions import (
        ListDraftedMotionsTool,
    )

    fake = AsyncMock(return_value=[
        _make_log(id="log-a", user_id="alice", template_name="Motion to Extend Stay"),
        _make_log(id="log-b", user_id="bob",   template_name="Motion to Modify Plan", r2_object_key=None),
    ])
    monkeypatch.setattr(
        "src.core.agents.llm.chat.tools.list_drafted_motions."
        "CaseGenerationLogRepository.list_for_case_all_users",
        fake,
    )

    out = await ListDraftedMotionsTool.invoke(_make_ctx())

    fake.assert_awaited_once_with(case_id="26_10700", limit=50)
    assert out["total"] == 2
    by_id = {l["log_id"]: l for l in out["logs"]}
    # Cross-user data surfaces both rows.
    assert by_id["log-a"]["user_id"] == "alice"
    assert by_id["log-b"]["user_id"] == "bob"
    # has_document derived from r2_object_key.
    assert by_id["log-a"]["has_document"] is True
    assert by_id["log-b"]["has_document"] is False


@pytest.mark.unit
async def test_list_drafted_motions_filters_by_status_in_memory(monkeypatch):
    """`status_filter` is applied client-side (case-insensitive) on top of
    whatever the repo returned — useful for "only the completed drafts"
    follow-up questions."""
    from src.core.agents.llm.chat.tools.list_drafted_motions import (
        ListDraftedMotionsTool,
    )

    fake = AsyncMock(return_value=[
        _make_log(id="log-a", status="COMPLETED"),
        _make_log(id="log-b", status="DRAFTING"),
        _make_log(id="log-c", status="FAILED"),
    ])
    monkeypatch.setattr(
        "src.core.agents.llm.chat.tools.list_drafted_motions."
        "CaseGenerationLogRepository.list_for_case_all_users",
        fake,
    )

    out = await ListDraftedMotionsTool.invoke(
        _make_ctx(), status_filter="completed",
    )
    assert out["total"] == 1
    assert out["logs"][0]["log_id"] == "log-a"
    assert out["status_filter"] == "completed"


@pytest.mark.unit
async def test_list_drafted_motions_truncates_long_error_text(monkeypatch):
    from src.core.agents.llm.chat.tools.list_drafted_motions import (
        ListDraftedMotionsTool,
    )

    long_error = "x" * 5000
    fake = AsyncMock(return_value=[
        _make_log(status="FAILED", error=long_error),
    ])
    monkeypatch.setattr(
        "src.core.agents.llm.chat.tools.list_drafted_motions."
        "CaseGenerationLogRepository.list_for_case_all_users",
        fake,
    )

    out = await ListDraftedMotionsTool.invoke(_make_ctx())
    summarized_error = out["logs"][0]["error"]
    # ~200 char cap plus an ellipsis sentinel.
    assert len(summarized_error) <= 220
    assert summarized_error.endswith("…")


@pytest.mark.unit
async def test_list_drafted_motions_returns_error_envelope_on_exception(monkeypatch):
    from src.core.agents.llm.chat.tools.list_drafted_motions import (
        ListDraftedMotionsTool,
    )

    async def boom(**_kw):
        raise RuntimeError("db down")

    monkeypatch.setattr(
        "src.core.agents.llm.chat.tools.list_drafted_motions."
        "CaseGenerationLogRepository.list_for_case_all_users",
        boom,
    )

    out = await ListDraftedMotionsTool.invoke(_make_ctx())
    assert out["total"] == 0
    assert out["logs"] == []
    assert "db down" in out["error"]
