"""`CostTrackingCallback.on_llm_end` — usage extraction + cost write."""

from __future__ import annotations

import asyncio
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from src.core.common.cost_tracking import CostContext, CostTrackingCallback


def _make_result(message: AIMessage, model: str) -> LLMResult:
    """Build a real LLMResult with one ChatGeneration carrying the message."""
    gen = ChatGeneration(message=message)
    return LLMResult(
        generations=[[gen]],
        llm_output={"model_name": model},
    )


def _patch_record(monkeypatch) -> AsyncMock:
    """Stub the repo's record method and return the AsyncMock so tests can
    inspect call args after awaiting any background tasks."""
    fake = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "src.core.common.storage.database.LlmCostLogRepository.record",
        fake,
    )
    return fake


@pytest.mark.unit
async def test_on_llm_end_records_anthropic_usage(monkeypatch):
    record = _patch_record(monkeypatch)
    msg = AIMessage(
        content="hi",
        usage_metadata={
            "input_tokens": 1000,
            "output_tokens": 500,
            "total_tokens": 1500,
            "input_token_details": {"cache_read": 100, "cache_creation": 0},
        },
        response_metadata={"model_name": "claude-sonnet-4-6"},
    )
    cb = CostTrackingCallback(
        cost_context=CostContext(kind="chat", firm_id="firm-1", case_id="c1"),
    )
    await cb.on_llm_end(_make_result(msg, "claude-sonnet-4-6"), run_id=uuid4())

    # The repo write is fire-and-forget via asyncio.create_task — give
    # the event loop a tick so it lands before we assert.
    for _ in range(5):
        if record.await_count > 0:
            break
        await asyncio.sleep(0)

    record.assert_awaited_once()
    kw = record.await_args.kwargs
    assert kw["kind"] == "chat"
    assert kw["firm_id"] == "firm-1"
    assert kw["model"] == "claude-sonnet-4-6"
    assert kw["input_tokens"] == 1000
    assert kw["output_tokens"] == 500
    assert kw["cache_read_tokens"] == 100
    # 1000*3e-6 + 500*15e-6 + 100*0.3e-6 = 0.003 + 0.0075 + 0.00003 = 0.01053
    assert kw["cost_usd"] == Decimal("0.010530")
    assert "case_id" in kw["metadata"]
    assert kw["metadata"]["case_id"] == "c1"


@pytest.mark.unit
async def test_on_llm_end_adds_web_search_fee(monkeypatch):
    """server_tool_use content blocks should add $0.01 each on top of message tokens."""
    record = _patch_record(monkeypatch)
    msg = AIMessage(
        content=[
            {"type": "server_tool_use", "id": "srvtoolu_1", "name": "web_search", "input": {}},
            {"type": "server_tool_use", "id": "srvtoolu_2", "name": "web_search", "input": {}},
            {"type": "text", "text": "answer"},
        ],
        usage_metadata={
            "input_tokens": 1000,
            "output_tokens": 0,
            "total_tokens": 1000,
        },
        response_metadata={"model_name": "claude-sonnet-4-6"},
    )
    cb = CostTrackingCallback(
        cost_context=CostContext(kind="chat", firm_id="firm-1"),
    )
    await cb.on_llm_end(_make_result(msg, "claude-sonnet-4-6"), run_id=uuid4())
    for _ in range(5):
        if record.await_count > 0:
            break
        await asyncio.sleep(0)

    record.assert_awaited_once()
    kw = record.await_args.kwargs
    # 1000*3e-6 = 0.003 tokens cost + 2 × 0.01 web_search fee = 0.023
    assert kw["cost_usd"] == Decimal("0.023000")
    assert kw["metadata"]["web_search_uses"] == 2


@pytest.mark.unit
async def test_on_llm_end_skips_when_no_usage(monkeypatch):
    record = _patch_record(monkeypatch)
    msg = AIMessage(content="")
    cb = CostTrackingCallback(
        cost_context=CostContext(kind="chat", firm_id="firm-1"),
    )
    await cb.on_llm_end(_make_result(msg, ""), run_id=uuid4())
    await asyncio.sleep(0)
    record.assert_not_awaited()


@pytest.mark.unit
async def test_on_llm_end_swallows_repo_exception(monkeypatch):
    """Repo failures must NOT propagate — the LLM call should still
    complete cleanly even if Postgres is down."""
    async def boom(**_kw):
        raise RuntimeError("postgres down")

    monkeypatch.setattr(
        "src.core.common.storage.database.LlmCostLogRepository.record",
        boom,
    )
    msg = AIMessage(
        content="hi",
        usage_metadata={"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
        response_metadata={"model_name": "claude-haiku-4-5"},
    )
    cb = CostTrackingCallback(
        cost_context=CostContext(kind="chat", firm_id="firm-1"),
    )
    # No exception should escape.
    await cb.on_llm_end(_make_result(msg, "claude-haiku-4-5"), run_id=uuid4())
    await asyncio.sleep(0)
