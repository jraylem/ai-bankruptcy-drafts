"""LlmCostLogRepository — record() must swallow exceptions; aggregates must build the right SQL."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.core.common.storage.database.repositories.llm_cost_log_repository import (
    LlmCostLogRepository,
)


class _FakeResult:
    def __init__(self, rows=None, row=None):
        self._rows = rows or []
        self._single = row

    def fetchall(self):
        return [SimpleNamespace(_mapping=r) for r in self._rows]

    def fetchone(self):
        return SimpleNamespace(_mapping=self._single) if self._single else None


class _FakeSession:
    def __init__(self, scripted: list[_FakeResult]):
        self._scripted = list(scripted)
        self.executes: list[tuple[str, dict]] = []
        self.added: list = []
        self.committed = 0

    async def execute(self, stmt, params=None):
        self.executes.append((str(stmt), params or {}))
        return self._scripted.pop(0) if self._scripted else _FakeResult()

    def add(self, instance):
        self.added.append(instance)

    async def commit(self):
        self.committed += 1


def _install_fake_session(monkeypatch, fake: _FakeSession) -> None:
    @asynccontextmanager
    async def fake_ctx():
        yield fake

    monkeypatch.setattr(
        "src.core.common.storage.database.repositories.llm_cost_log_repository."
        "BaseRepository._session",
        staticmethod(fake_ctx),
    )


# ─── record() ─────────────────────────────────────────────────────────


@pytest.mark.unit
async def test_record_inserts_row(monkeypatch):
    fake = _FakeSession([])
    _install_fake_session(monkeypatch, fake)
    await LlmCostLogRepository.record(
        kind="chat", firm_id="firm-1", model="claude-sonnet-4-6",
        input_tokens=100, output_tokens=50, cost_usd=Decimal("0.0015"),
        metadata={"case_id": "c1"},
    )
    assert len(fake.added) == 1
    log = fake.added[0]
    assert log.kind == "chat"
    assert log.firm_id == "firm-1"
    assert log.cost_usd == Decimal("0.0015")
    assert log.log_metadata == {"case_id": "c1"}
    assert fake.committed == 1


@pytest.mark.unit
async def test_record_swallows_session_exception(monkeypatch):
    """A Postgres error must not propagate — cost tracking is best-effort."""
    @asynccontextmanager
    async def boom_ctx():
        raise RuntimeError("postgres unreachable")
        yield  # never reached

    monkeypatch.setattr(
        "src.core.common.storage.database.repositories.llm_cost_log_repository."
        "BaseRepository._session",
        staticmethod(boom_ctx),
    )
    # No exception should escape.
    await LlmCostLogRepository.record(
        kind="chat", firm_id="firm-1", model="claude-haiku-4-5",
        cost_usd=Decimal("0.01"),
    )


# ─── aggregate_by_kind ────────────────────────────────────────────────


@pytest.mark.unit
async def test_aggregate_by_kind_returns_rows_in_order(monkeypatch):
    rows = [
        {"kind": "draft", "cost_usd": Decimal("50.10"), "input_tokens": 1000, "output_tokens": 500},
        {"kind": "chat", "cost_usd": Decimal("12.05"), "input_tokens": 300, "output_tokens": 200},
    ]
    fake = _FakeSession([_FakeResult(rows=rows)])
    _install_fake_session(monkeypatch, fake)
    out = await LlmCostLogRepository.aggregate_by_kind(
        firm_id="firm-1",
        since=datetime(2026, 5, 1, tzinfo=timezone.utc),
        until=datetime(2026, 5, 19, tzinfo=timezone.utc),
    )
    assert [r["kind"] for r in out] == ["draft", "chat"]
    assert out[0]["cost_usd"] == Decimal("50.10")
    # Verify the SQL is firm-scoped.
    stmt, params = fake.executes[0]
    assert "GROUP BY kind" in stmt
    assert "AND firm_id = :firm_id" in stmt
    assert params["firm_id"] == "firm-1"


@pytest.mark.unit
async def test_aggregate_by_kind_no_firm_clause_when_null(monkeypatch):
    fake = _FakeSession([_FakeResult(rows=[])])
    _install_fake_session(monkeypatch, fake)
    await LlmCostLogRepository.aggregate_by_kind(
        firm_id=None,
        since=datetime(2026, 5, 1, tzinfo=timezone.utc),
        until=datetime(2026, 5, 19, tzinfo=timezone.utc),
    )
    stmt, params = fake.executes[0]
    assert "firm_id" not in stmt  # no firm filter when None
    assert "firm_id" not in params


# ─── aggregate_total ──────────────────────────────────────────────────


@pytest.mark.unit
async def test_aggregate_total_sums_columns(monkeypatch):
    row = {
        "cost_usd": Decimal("123.45"),
        "input_tokens": 10000,
        "output_tokens": 5000,
        "cache_read_tokens": 200,
        "cache_write_tokens": 100,
    }
    fake = _FakeSession([_FakeResult(row=row)])
    _install_fake_session(monkeypatch, fake)
    out = await LlmCostLogRepository.aggregate_total(
        firm_id="firm-1",
        since=datetime(2026, 1, 1, tzinfo=timezone.utc),
        until=datetime(2026, 5, 19, tzinfo=timezone.utc),
    )
    assert out["cost_usd"] == Decimal("123.45")
    assert out["input_tokens"] == 10000


# ─── workflow_aggregates ──────────────────────────────────────────────


@pytest.mark.unit
async def test_workflow_aggregates_returns_per_unit_counts(monkeypatch):
    """Single SQL — chat: sessions+messages+cases; pleadings: runs+cases; case_ingest: cases."""
    fake = _FakeSession([
        _FakeResult(row={
            "chat_cost": Decimal("80.00"),
            "chat_sessions": 4,
            "chat_messages": 28,
            "chat_cases": 3,
            "pleadings_cost": Decimal("150.00"),
            "pleadings_runs": 3,
            "pleadings_cases": 2,
            "case_ingest_cost": Decimal("25.00"),
            "case_ingest_cases": 5,
        }),
    ])
    _install_fake_session(monkeypatch, fake)

    out = await LlmCostLogRepository.workflow_aggregates(
        firm_id="firm-1",
        since=datetime(2026, 5, 1, tzinfo=timezone.utc),
        until=datetime(2026, 5, 19, tzinfo=timezone.utc),
    )

    assert out["chat"] == {
        "total_cost_usd": Decimal("80.00"),
        "sessions": 4, "messages": 28, "cases": 3,
    }
    assert out["pleadings"] == {
        "total_cost_usd": Decimal("150.00"),
        "runs": 3, "cases": 2,
    }
    assert out["case_ingest"] == {
        "total_cost_usd": Decimal("25.00"),
        "cases": 5,
    }

    # Only ONE SQL statement.
    assert len(fake.executes) == 1
    sql = fake.executes[0][0]
    # All aliases appear in the single query.
    for alias in (
        "chat_cost", "chat_sessions", "chat_messages", "chat_cases",
        "pleadings_cost", "pleadings_runs", "pleadings_cases",
        "case_ingest_cost", "case_ingest_cases",
    ):
        assert alias in sql, f"missing alias {alias} in workflow_aggregates SQL"
    # Scope-based filtering uses the new semantic_id_kind column for chat + pleadings.
    assert "semantic_id_kind = 'case_session'" in sql
    assert "semantic_id_kind = 'pleading_run'" in sql
    # case_ingest stays kind-based (CaseIngestionAgent fires before case_id is known).
    assert "kind IN ('case_ingest', 'embeddings')" in sql
    assert "kind = 'case_ingest'" in sql
    # COUNT(DISTINCT semantic_id) replaces the old JSONB session_id extraction.
    assert "COUNT(DISTINCT semantic_id)" in sql
    assert "AND firm_id = :firm_id" in sql


@pytest.mark.unit
async def test_workflow_aggregates_empty_row_returns_zeros(monkeypatch):
    fake = _FakeSession([_FakeResult(row=None)])
    _install_fake_session(monkeypatch, fake)

    out = await LlmCostLogRepository.workflow_aggregates(
        firm_id=None,
        since=datetime(2026, 5, 1, tzinfo=timezone.utc),
        until=datetime(2026, 5, 19, tzinfo=timezone.utc),
    )

    # Chat has sessions/messages/cases; pleadings has runs/cases; case_ingest has cases.
    assert out["chat"] == {
        "total_cost_usd": Decimal("0"),
        "sessions": 0, "messages": 0, "cases": 0,
    }
    assert out["pleadings"] == {
        "total_cost_usd": Decimal("0"),
        "runs": 0, "cases": 0,
    }
    assert out["case_ingest"] == {
        "total_cost_usd": Decimal("0"),
        "cases": 0,
    }


# ─── daily_series ─────────────────────────────────────────────────────


@pytest.mark.unit
async def test_daily_series_returns_per_day_buckets(monkeypatch):
    rows = [
        {"day": datetime(2026, 5, 1, tzinfo=timezone.utc), "cost_usd": Decimal("12.10")},
        {"day": datetime(2026, 5, 2, tzinfo=timezone.utc), "cost_usd": Decimal("8.50")},
    ]
    fake = _FakeSession([_FakeResult(rows=rows)])
    _install_fake_session(monkeypatch, fake)
    out = await LlmCostLogRepository.daily_series(
        firm_id="firm-1",
        since=datetime(2026, 5, 1, tzinfo=timezone.utc),
        until=datetime(2026, 5, 19, tzinfo=timezone.utc),
    )
    assert len(out) == 2
    assert out[0]["cost_usd"] == Decimal("12.10")
    stmt, _ = fake.executes[0]
    assert "date_trunc('day', created_at)" in stmt
