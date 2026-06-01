"""Tests for tool construction — graceful degradation when context
is missing required scopes (no firm OAuth, no case_file_collection,
no petition_pdf_url) AND invocation behavior of the built tools.

Real Anthropic / Gmail API calls are not exercised here — those are
integration concerns. We verify the constructors return `None` when
they should, a callable tool when they shouldn't, and (with mocks)
that the wrapped tools dispatch correctly when invoked.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.studio_v2.tools import StudioV2ToolContext
from src.core.studio_v2.tools.case_vector_query import build_case_vector_query_tool
from src.core.studio_v2.tools.gmail_search import (
    build_gmail_search_tool,
    load_firm_gmail_credentials,
)
from src.core.studio_v2.tools.vision_fallback import build_vision_fallback_tool


class _FakeCase:
    """Minimal stand-in for the SQLAlchemy Case row."""

    def __init__(
        self,
        *,
        case_id: str = "case-1",
        case_number: str = "26-12345-ABC",
        case_name: str = "Doe, John",
        case_file_collection: str | None = None,
        petition_pdf_url: str | None = None,
    ):
        self.id = case_id
        self.case_number = case_number
        self.case_name = case_name
        self.case_file_collection = case_file_collection
        self.petition_pdf_url = petition_pdf_url


@pytest.mark.unit
def test_gmail_tool_returns_none_when_oauth_missing():
    ctx = StudioV2ToolContext(case=_FakeCase(), firm_oauth=None)
    assert build_gmail_search_tool(ctx) is None


@pytest.mark.unit
def test_case_vector_tool_returns_none_when_collection_missing():
    ctx = StudioV2ToolContext(case=_FakeCase(case_file_collection=None))
    assert build_case_vector_query_tool(ctx) is None


@pytest.mark.unit
def test_case_vector_tool_built_when_collection_present():
    ctx = StudioV2ToolContext(case=_FakeCase(case_file_collection="case_file_abc"))
    tool = build_case_vector_query_tool(ctx)
    assert tool is not None
    assert callable(tool)


@pytest.mark.unit
def test_vision_tool_returns_none_when_petition_missing():
    ctx = StudioV2ToolContext(case=_FakeCase(petition_pdf_url=None))
    assert build_vision_fallback_tool(ctx) is None


@pytest.mark.unit
def test_vision_tool_built_when_petition_present():
    ctx = StudioV2ToolContext(
        case=_FakeCase(petition_pdf_url="https://r2/petitions/abc.pdf"),
    )
    tool = build_vision_fallback_tool(ctx)
    assert tool is not None
    assert callable(tool)


# ─── load_firm_gmail_credentials ─────────────────────────────────────


@pytest.mark.unit
def test_load_firm_gmail_credentials_returns_none_when_token_missing(tmp_path):
    """No token.json file on disk → returns None (logged warning)."""
    fake_path = tmp_path / "missing_token.json"
    with patch(
        "src.core.components.case_inbox.gmail._TOKEN_PATH",
        str(fake_path),
    ):
        assert load_firm_gmail_credentials() is None


@pytest.mark.unit
def test_load_firm_gmail_credentials_returns_none_on_load_error(tmp_path):
    """Malformed token file → load raises → caught + returns None."""
    fake_path = tmp_path / "bad_token.json"
    fake_path.write_text("not valid json")
    with patch(
        "src.core.components.case_inbox.gmail._TOKEN_PATH",
        str(fake_path),
    ):
        assert load_firm_gmail_credentials() is None


# ─── gmail_search wrapped-tool invocation ────────────────────────────


@pytest.mark.unit
def test_gmail_tool_invocation_scopes_query_and_calls_underlying():
    """The built tool wraps every call: case-scope clause AND-appended,
    underlying GmailSearch._run invoked with max_results=25."""
    fake_underlying = MagicMock()
    fake_underlying._run.return_value = [{"id": "msg1", "body": "hello"}]
    ctx = StudioV2ToolContext(
        case=_FakeCase(case_number="26-15038-PDR"),
        firm_oauth=MagicMock(),
    )
    with patch(
        "langchain_google_community.gmail.utils.build_resource_service",
        return_value=MagicMock(),
    ), patch(
        "langchain_google_community.gmail.search.GmailSearch",
        return_value=fake_underlying,
    ):
        tool = build_gmail_search_tool(ctx)
        assert tool is not None
        # LangChain @tool wraps as a Tool with .invoke({"query": ...})
        result = tool.invoke({"query": '"proof of claim"'})
        assert result == [{"id": "msg1", "body": "hello"}]
        fake_underlying._run.assert_called_once()
        sent_query = fake_underlying._run.call_args[0][0]
        assert "proof of claim" in sent_query
        assert "26-15038" in sent_query  # scope clause appended
        assert fake_underlying._run.call_args[1]["max_results"] == 25


@pytest.mark.unit
def test_gmail_tool_invocation_skips_scoping_when_no_case_number():
    """Empty case_number → query passes through unmodified."""
    fake_underlying = MagicMock()
    fake_underlying._run.return_value = []
    ctx = StudioV2ToolContext(
        case=_FakeCase(case_number=""),
        firm_oauth=MagicMock(),
    )
    with patch(
        "langchain_google_community.gmail.utils.build_resource_service",
        return_value=MagicMock(),
    ), patch(
        "langchain_google_community.gmail.search.GmailSearch",
        return_value=fake_underlying,
    ):
        tool = build_gmail_search_tool(ctx)
        assert tool is not None
        tool.invoke({"query": "any query"})
        sent_query = fake_underlying._run.call_args[0][0]
        assert sent_query == "any query"


@pytest.mark.unit
def test_gmail_tool_returns_none_when_resource_build_raises():
    """Underlying build_resource_service raises → wrapper catches +
    returns None so the toolset builder can skip it."""
    ctx = StudioV2ToolContext(
        case=_FakeCase(),
        firm_oauth=MagicMock(),
    )
    with patch(
        "langchain_google_community.gmail.utils.build_resource_service",
        side_effect=RuntimeError("oauth refresh failed"),
    ):
        assert build_gmail_search_tool(ctx) is None


# ─── vision_fallback wrapped-tool invocation ─────────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
async def test_vision_tool_returns_error_when_fetch_raises():
    """`fetch_petition_pdf_bytes` raises → tool catches + returns
    {answer: None, error: <msg>}. Never raises into the agent loop.

    Patch must be in place BEFORE `build_vision_fallback_tool` runs —
    the function imports `fetch_petition_pdf_bytes` into its local
    scope and closes the inner tool over that binding."""
    ctx = StudioV2ToolContext(
        case=_FakeCase(petition_pdf_url="https://r2/petitions/abc.pdf"),
    )
    with patch(
        "src.core.agents.utils.petition_pdf.fetch_petition_pdf_bytes",
        new=AsyncMock(side_effect=RuntimeError("network down")),
    ):
        tool = build_vision_fallback_tool(ctx)
        assert tool is not None
        result = await tool.ainvoke({"question": "Is the box checked?"})
        assert result["question"] == "Is the box checked?"
        assert result["answer"] is None
        assert "network down" in result["error"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_vision_tool_returns_error_when_fetch_returns_none():
    """`fetch_petition_pdf_bytes` returns None (download failed) →
    tool returns a 'Could not download' error result."""
    ctx = StudioV2ToolContext(
        case=_FakeCase(petition_pdf_url="https://r2/petitions/abc.pdf"),
    )
    with patch(
        "src.core.agents.utils.petition_pdf.fetch_petition_pdf_bytes",
        new=AsyncMock(return_value=None),
    ):
        tool = build_vision_fallback_tool(ctx)
        assert tool is not None
        result = await tool.ainvoke({"question": "Anything"})
        assert result["answer"] is None
        assert "Could not download" in result["error"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_vision_tool_returns_answer_on_success():
    """Successful PDF fetch + LLM call → returns the LLM's text in
    `answer`. Multi-block list content is flattened to string."""
    ctx = StudioV2ToolContext(
        case=_FakeCase(
            petition_pdf_url="https://r2/petitions/abc.pdf",
            case_number="26-15038-PDR",
            case_name="Doe",
        ),
    )
    fake_llm = MagicMock()
    fake_llm.with_config = MagicMock(return_value=fake_llm)
    fake_response = MagicMock()
    fake_response.content = [{"type": "text", "text": "Chapter 13 is checked."}]
    fake_llm.ainvoke = AsyncMock(return_value=fake_response)

    with patch(
        "src.core.agents.utils.petition_pdf.fetch_petition_pdf_bytes",
        new=AsyncMock(return_value=b"%PDF-1.4 fake content"),
    ), patch(
        "langchain_anthropic.ChatAnthropic",
        return_value=fake_llm,
    ):
        tool = build_vision_fallback_tool(ctx)
        assert tool is not None
        result = await tool.ainvoke({"question": "Which chapter?"})
        assert result["question"] == "Which chapter?"
        assert result["answer"] == "Chapter 13 is checked."
        assert "error" not in result or result.get("error") is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_vision_tool_returns_error_on_llm_failure():
    """LLM ainvoke raises → tool catches + returns error result."""
    ctx = StudioV2ToolContext(
        case=_FakeCase(petition_pdf_url="https://r2/petitions/abc.pdf"),
    )
    fake_llm = MagicMock()
    fake_llm.with_config = MagicMock(return_value=fake_llm)
    fake_llm.ainvoke = AsyncMock(side_effect=RuntimeError("anthropic 503"))

    with patch(
        "src.core.agents.utils.petition_pdf.fetch_petition_pdf_bytes",
        new=AsyncMock(return_value=b"%PDF-1.4 fake content"),
    ), patch(
        "langchain_anthropic.ChatAnthropic",
        return_value=fake_llm,
    ):
        tool = build_vision_fallback_tool(ctx)
        assert tool is not None
        result = await tool.ainvoke({"question": "Anything"})
        assert result["answer"] is None
        assert "anthropic 503" in result["error"]


# ─── case_vector_query wrapped-tool invocation ───────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
async def test_case_vector_tool_invocation_dispatches_to_toolbox():
    """The built tool calls ToolBox.query_case_specific with the
    bound collection_name (from ctx) + query / k from the LLM.
    Result is `.model_dump()`-ed before returning."""
    ctx = StudioV2ToolContext(
        case=_FakeCase(case_file_collection="case_file_xyz"),
    )

    fake_result = MagicMock()
    fake_result.model_dump.return_value = {
        "results": [{"content": "petition chunk", "relevance_score": 0.91}],
        "total": 1,
    }
    with patch(
        "src.core.common.toolbox.ToolBox.query_case_specific",
        new=AsyncMock(return_value=fake_result),
    ) as mock_query:
        tool = build_case_vector_query_tool(ctx)
        assert tool is not None
        result = await tool.ainvoke({"query": "trustee name", "top_k": 5})
        assert result["total"] == 1
        assert result["results"][0]["content"] == "petition chunk"
        mock_query.assert_called_once()
        # Verify collection_name was forwarded from ctx
        call_kwargs = mock_query.call_args.kwargs
        assert call_kwargs.get("collection_name") == "case_file_xyz"
        assert call_kwargs.get("query") == "trustee name"
        assert call_kwargs.get("k") == 5


@pytest.mark.unit
@pytest.mark.asyncio
async def test_case_vector_tool_caps_top_k_at_20():
    """LLM asking for top_k > 20 gets capped to 20."""
    ctx = StudioV2ToolContext(
        case=_FakeCase(case_file_collection="case_file_xyz"),
    )
    fake_result = MagicMock()
    fake_result.model_dump.return_value = {"results": [], "total": 0}
    with patch(
        "src.core.common.toolbox.ToolBox.query_case_specific",
        new=AsyncMock(return_value=fake_result),
    ) as mock_query:
        tool = build_case_vector_query_tool(ctx)
        assert tool is not None
        await tool.ainvoke({"query": "x", "top_k": 100})
        assert mock_query.call_args.kwargs.get("k") == 20


@pytest.mark.unit
@pytest.mark.asyncio
async def test_case_vector_tool_returns_error_on_lookup_failure():
    """Vector lookup raises → tool catches + returns error dict so the
    agent can decide whether to retry or pivot to gmail_search."""
    ctx = StudioV2ToolContext(
        case=_FakeCase(case_file_collection="case_file_xyz"),
    )
    with patch(
        "src.core.common.toolbox.ToolBox.query_case_specific",
        new=AsyncMock(side_effect=RuntimeError("pgvector down")),
    ):
        tool = build_case_vector_query_tool(ctx)
        assert tool is not None
        result = await tool.ainvoke({"query": "anything"})
        assert result == {"results": [], "total": 0, "error": "pgvector down"}
