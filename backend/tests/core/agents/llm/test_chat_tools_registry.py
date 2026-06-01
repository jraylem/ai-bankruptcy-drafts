"""Registry behavior + the initial tool set's Anthropic-bound shape."""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from src.core.agents.llm.chat.tools.base import BaseChatTool
from src.core.agents.llm.chat.tools.registry import (
    _REGISTRY,
    get_all_tools,
    get_tool_by_name,
    register_tool,
)


@pytest.mark.unit
def test_initial_tool_set_is_registered():
    names = {t.name for t in get_all_tools()}
    assert {
        "case_vector_search",
        "case_emails_search",
        "gmail_search",
        "petition_vision_lookup",
        "list_drafted_motions",
    } <= names


@pytest.mark.unit
def test_get_tool_by_name_finds_known_and_returns_none_for_unknown():
    assert get_tool_by_name("case_vector_search") is not None
    assert get_tool_by_name("not_a_real_tool") is None


@pytest.mark.unit
def test_web_search_is_not_in_local_registry():
    """`web_search` is Anthropic's server-hosted tool — declared in
    `_build_llm` but NOT a `BaseChatTool` subclass. The local registry
    should NOT know about it; `_dispatch_tools` has a separate guard to
    skip its tool_calls instead of trying to invoke it."""
    assert get_tool_by_name("web_search") is None


@pytest.mark.unit
def test_register_tool_is_idempotent_across_calls():
    class _Args(BaseModel):
        x: str

    class _Dummy(BaseChatTool):
        name = "dummy_idempotency_probe"
        description = "noop"
        input_schema = _Args

        @classmethod
        async def invoke(cls, ctx, **kwargs):  # noqa: D401
            return {}

    try:
        register_tool(_Dummy)
        register_tool(_Dummy)
        register_tool(_Dummy)
        matches = [t for t in get_all_tools() if t is _Dummy]
        assert len(matches) == 1
    finally:
        if _Dummy in _REGISTRY:
            _REGISTRY.remove(_Dummy)


@pytest.mark.unit
def test_to_langchain_tool_emits_anthropic_compatible_dict():
    from src.core.agents.llm.chat.tools.case_vector_search import (
        CaseVectorSearchTool,
    )

    spec = CaseVectorSearchTool.to_langchain_tool()
    assert spec["name"] == "case_vector_search"
    assert "description" in spec and spec["description"]
    schema = spec["input_schema"]
    assert "title" not in schema
    assert "properties" in schema
    assert "query" in schema["properties"]
    assert "k" in schema["properties"]
