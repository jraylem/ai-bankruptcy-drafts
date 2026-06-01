"""`build_summary` aggregation + projection math."""

from __future__ import annotations

import calendar
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from src.core.components.costs import service


_EMPTY_WORKFLOW = {
    "chat": {"total_cost_usd": Decimal("0"), "sessions": 0, "messages": 0, "cases": 0},
    "pleadings": {"total_cost_usd": Decimal("0"), "runs": 0, "cases": 0},
    "case_ingest": {"total_cost_usd": Decimal("0"), "cases": 0},
}


def _fake_repo(
    monkeypatch,
    *,
    total: Decimal,
    by_kind: list,
    daily: list,
    year_total: Decimal | None = None,
    workflow: dict | None = None,
) -> None:
    """Patch all three aggregate methods on LlmCostLogRepository.

    `aggregate_total` is called twice in the month-range path: once for
    the MTD window and once for the YTD window — we return different
    totals based on the `since` argument.
    """
    async def fake_total(*, firm_id, since, until):
        # Month start of `until` differentiates MTD vs YTD windows.
        is_ytd = since.month == 1 and since.day == 1
        if is_ytd and year_total is not None:
            return {
                "cost_usd": year_total,
                "input_tokens": 0, "output_tokens": 0,
                "cache_read_tokens": 0, "cache_write_tokens": 0,
            }
        return {
            "cost_usd": total,
            "input_tokens": 0, "output_tokens": 0,
            "cache_read_tokens": 0, "cache_write_tokens": 0,
        }

    monkeypatch.setattr(
        "src.core.common.storage.database.LlmCostLogRepository.aggregate_total",
        fake_total,
    )
    monkeypatch.setattr(
        "src.core.common.storage.database.LlmCostLogRepository.aggregate_by_kind",
        AsyncMock(return_value=by_kind),
    )
    monkeypatch.setattr(
        "src.core.common.storage.database.LlmCostLogRepository.daily_series",
        AsyncMock(return_value=daily),
    )
    monkeypatch.setattr(
        "src.core.common.storage.database.LlmCostLogRepository.workflow_aggregates",
        AsyncMock(return_value=workflow or _EMPTY_WORKFLOW),
    )


@pytest.mark.unit
async def test_month_summary_includes_linear_projection(monkeypatch):
    _fake_repo(
        monkeypatch,
        total=Decimal("100"),
        by_kind=[
            {"kind": "chat", "cost_usd": Decimal("60"), "input_tokens": 0, "output_tokens": 0},
            {"kind": "draft", "cost_usd": Decimal("40"), "input_tokens": 0, "output_tokens": 0},
        ],
        daily=[
            {"day": datetime(2026, 5, 1, tzinfo=timezone.utc), "cost_usd": Decimal("50")},
            {"day": datetime(2026, 5, 2, tzinfo=timezone.utc), "cost_usd": Decimal("50")},
        ],
        year_total=Decimal("500"),
    )
    # Force `now` to a fixed point: 2 days into a 30-day month (May has 31).
    now = datetime(2026, 5, 2, 12, 0, 0, tzinfo=timezone.utc)

    out = await service.build_summary(firm_id="firm-1", range_="month", now=now)

    assert out.range == "month"
    assert out.total_cost_usd == Decimal("100")
    assert len(out.by_kind) == 2
    # Projection math:
    #   month: 100 * (31 / 2) = 1550
    #   year:  500 * (365 / day_of_year(2026-05-02=122)) ≈ 1496.72
    assert out.projection is not None
    assert out.projection.this_month_cost_usd == Decimal("1550.00")
    days_in_year = 366 if calendar.isleap(2026) else 365
    day_of_year = datetime(2026, 5, 2).timetuple().tm_yday
    expected_year = (
        Decimal("500") * Decimal(days_in_year) / Decimal(day_of_year)
    ).quantize(Decimal("0.01"))
    assert out.projection.this_year_cost_usd == expected_year


@pytest.mark.unit
async def test_week_summary_omits_projection(monkeypatch):
    _fake_repo(
        monkeypatch,
        total=Decimal("12.34"),
        by_kind=[{"kind": "chat", "cost_usd": Decimal("12.34"), "input_tokens": 0, "output_tokens": 0}],
        daily=[],
    )
    out = await service.build_summary(firm_id="firm-1", range_="week")
    assert out.range == "week"
    assert out.total_cost_usd == Decimal("12.34")
    assert out.projection is None


@pytest.mark.unit
async def test_unknown_range_defaults_to_month(monkeypatch):
    _fake_repo(
        monkeypatch,
        total=Decimal("5"),
        by_kind=[],
        daily=[],
        year_total=Decimal("100"),
    )
    out = await service.build_summary(firm_id="firm-1", range_="bogus")
    assert out.range == "month"
    assert out.projection is not None


def _entry_for(metric, unit: str):
    """Find the entry with the given unit on a workflow metric, or None."""
    for e in metric.metrics:
        if e.unit == unit:
            return e
    return None


@pytest.mark.unit
async def test_workflow_metrics_computed_with_averages(monkeypatch):
    _fake_repo(
        monkeypatch,
        total=Decimal("300"),
        by_kind=[],
        daily=[],
        year_total=Decimal("300"),
        workflow={
            "chat": {"total_cost_usd": Decimal("100"), "sessions": 4, "messages": 20, "cases": 2},
            "pleadings": {"total_cost_usd": Decimal("180"), "runs": 3, "cases": 2},
            "case_ingest": {"total_cost_usd": Decimal("20"), "cases": 2},
        },
    )

    out = await service.build_summary(firm_id="firm-1", range_="month")

    # Chat: total + 3 breakdowns (session, message, case).
    chat = out.workflow_metrics.chat
    assert chat.total_cost_usd == Decimal("100")
    assert {e.unit for e in chat.metrics} == {"session", "message", "case"}
    assert _entry_for(chat, "session").count == 4
    assert _entry_for(chat, "session").avg_cost_usd == Decimal("25.000000")
    assert _entry_for(chat, "message").count == 20
    assert _entry_for(chat, "message").avg_cost_usd == Decimal("5.000000")
    assert _entry_for(chat, "case").count == 2
    assert _entry_for(chat, "case").avg_cost_usd == Decimal("50.000000")

    # Pleadings: total + 2 breakdowns (run, case).
    pleadings = out.workflow_metrics.pleadings
    assert pleadings.total_cost_usd == Decimal("180")
    assert {e.unit for e in pleadings.metrics} == {"run", "case"}
    assert _entry_for(pleadings, "run").count == 3
    assert _entry_for(pleadings, "run").avg_cost_usd == Decimal("60.000000")
    assert _entry_for(pleadings, "case").count == 2
    assert _entry_for(pleadings, "case").avg_cost_usd == Decimal("90.000000")

    # Case ingestion: total + 1 breakdown (case).
    case_ingest = out.workflow_metrics.case_ingest
    assert case_ingest.total_cost_usd == Decimal("20")
    assert {e.unit for e in case_ingest.metrics} == {"case"}
    assert _entry_for(case_ingest, "case").count == 2
    assert _entry_for(case_ingest, "case").avg_cost_usd == Decimal("10.000000")


@pytest.mark.unit
async def test_workflow_metrics_zero_count_avg_is_zero(monkeypatch):
    _fake_repo(
        monkeypatch,
        total=Decimal("0"),
        by_kind=[],
        daily=[],
        year_total=Decimal("0"),
    )

    out = await service.build_summary(firm_id="firm-1", range_="month")

    # Every entry's avg is 0 when count is 0.
    for entry in out.workflow_metrics.chat.metrics:
        assert entry.count == 0
        assert entry.avg_cost_usd == Decimal("0")
    for entry in out.workflow_metrics.pleadings.metrics:
        assert entry.count == 0
        assert entry.avg_cost_usd == Decimal("0")
    for entry in out.workflow_metrics.case_ingest.metrics:
        assert entry.count == 0
        assert entry.avg_cost_usd == Decimal("0")
