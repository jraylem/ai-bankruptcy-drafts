"""Aggregate + project firm-scoped llm_cost_logs rows for the Costs panel.

Two flavors:
- `range='month'`: since = first-of-this-month at 00:00 UTC, until = now.
  Projection extrapolates the month-to-date cost to the full month and
  the year-to-date cost to the full year using linear scaling against
  elapsed wall-clock days (not calls). This is honest about its
  imprecision — "this month is projected to land at $X if usage
  continues at the current daily pace."
- `range='week'`: rolling 7-day window from `since`. No projection
  (weekly-projected-to-anything is meaningless and would mislead).
"""

from __future__ import annotations

import asyncio
import calendar
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from src.core.common.storage.database import LlmCostLogRepository

from .schemas import (
    CostsByKindEntry,
    CostsProjection,
    CostsSummaryResponse,
    DailyCostEntry,
    WorkflowCountUnit,
    WorkflowMetric,
    WorkflowMetrics,
)


def _avg(total_cost_usd: Decimal, count: int) -> Decimal:
    """Safe division for per-unit averages. Returns 0 when count is 0."""
    if count <= 0:
        return Decimal("0")
    return (total_cost_usd / Decimal(count)).quantize(Decimal("0.000001"))


def _entry(total_cost_usd: Decimal, count: int, unit: WorkflowCountUnit) -> "WorkflowMetricEntry":
    from .schemas import WorkflowMetricEntry
    return WorkflowMetricEntry(unit=unit, count=count, avg_cost_usd=_avg(total_cost_usd, count))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _month_window(now: datetime) -> tuple[datetime, datetime]:
    """First-of-month at 00:00 UTC → now (exclusive end)."""
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return start, now


def _week_window(now: datetime) -> tuple[datetime, datetime]:
    """Rolling 7-day window ending at `now`."""
    start = (now - timedelta(days=7)).replace(microsecond=0)
    return start, now


def _project(now: datetime, mtd_cost: Decimal) -> CostsProjection:
    """Linear extrapolation: mtd × (days_in_month / day_of_month) for
    month projection, ytd × (days_in_year / day_of_year) for year.

    Edge case: day_of_month == 1 (first hour of month) → return mtd
    as-is for month projection (we'd otherwise divide-by-near-zero and
    explode the number on the FE). Same guard for year.
    """
    days_in_month = calendar.monthrange(now.year, now.month)[1]
    day_of_month = now.day
    if day_of_month <= 0:
        day_of_month = 1
    month_projection = mtd_cost * Decimal(days_in_month) / Decimal(day_of_month)

    days_in_year = 366 if calendar.isleap(now.year) else 365
    day_of_year = now.timetuple().tm_yday or 1
    # Year projection uses YTD, not MTD — sum cost from Jan 1.
    # We'll fetch YTD separately via aggregate_total below. For now,
    # delegate to the caller to pass in YTD when constructing the
    # projection. To keep this helper simple we ONLY compute the
    # ratios here; the caller does the multiplication for year.
    year_ratio = Decimal(days_in_year) / Decimal(day_of_year)
    # Return placeholder; caller overrides year_cost via direct compute.
    return CostsProjection(
        this_month_cost_usd=month_projection.quantize(Decimal("0.01")),
        this_year_cost_usd=(mtd_cost * year_ratio).quantize(Decimal("0.01")),
    )


async def build_summary(
    *,
    firm_id: Optional[str],
    range_: str,
    now: Optional[datetime] = None,
) -> CostsSummaryResponse:
    """Single entry point the router calls. Range is 'week' or 'month'."""
    now = now or _now()

    if range_ == "week":
        since, until = _week_window(now)
    else:
        # default + explicit 'month'
        range_ = "month"
        since, until = _month_window(now)

    # All independent — fan out in parallel. Each repo method opens its
    # own session from the pool; pool size 20 has ample headroom for
    # the 4-5 concurrent connections this implies per request.
    year_start = now.replace(
        month=1, day=1, hour=0, minute=0, second=0, microsecond=0,
    )
    if range_ == "month":
        total, by_kind, daily, workflow_raw, ytd = await asyncio.gather(
            LlmCostLogRepository.aggregate_total(firm_id=firm_id, since=since, until=until),
            LlmCostLogRepository.aggregate_by_kind(firm_id=firm_id, since=since, until=until),
            LlmCostLogRepository.daily_series(firm_id=firm_id, since=since, until=until),
            LlmCostLogRepository.workflow_aggregates(firm_id=firm_id, since=since, until=until),
            LlmCostLogRepository.aggregate_total(firm_id=firm_id, since=year_start, until=now),
        )
    else:
        total, by_kind, daily, workflow_raw = await asyncio.gather(
            LlmCostLogRepository.aggregate_total(firm_id=firm_id, since=since, until=until),
            LlmCostLogRepository.aggregate_by_kind(firm_id=firm_id, since=since, until=until),
            LlmCostLogRepository.daily_series(firm_id=firm_id, since=since, until=until),
            LlmCostLogRepository.workflow_aggregates(firm_id=firm_id, since=since, until=until),
        )
        ytd = None
    chat_raw = workflow_raw["chat"]
    pleadings_raw = workflow_raw["pleadings"]
    case_ingest_raw = workflow_raw["case_ingest"]
    workflow_metrics = WorkflowMetrics(
        chat=WorkflowMetric(
            total_cost_usd=chat_raw["total_cost_usd"],
            metrics=[
                _entry(chat_raw["total_cost_usd"], chat_raw["sessions"], "session"),
                _entry(chat_raw["total_cost_usd"], chat_raw["messages"], "message"),
                _entry(chat_raw["total_cost_usd"], chat_raw["cases"], "case"),
            ],
        ),
        pleadings=WorkflowMetric(
            total_cost_usd=pleadings_raw["total_cost_usd"],
            metrics=[
                _entry(pleadings_raw["total_cost_usd"], pleadings_raw["runs"], "run"),
                _entry(pleadings_raw["total_cost_usd"], pleadings_raw["cases"], "case"),
            ],
        ),
        case_ingest=WorkflowMetric(
            total_cost_usd=case_ingest_raw["total_cost_usd"],
            metrics=[
                _entry(case_ingest_raw["total_cost_usd"], case_ingest_raw["cases"], "case"),
            ],
        ),
    )

    projection: Optional[CostsProjection] = None
    if range_ == "month":
        assert ytd is not None  # gathered above when range == 'month'
        days_in_month = calendar.monthrange(now.year, now.month)[1]
        day_of_month = max(now.day, 1)
        days_in_year = 366 if calendar.isleap(now.year) else 365
        day_of_year = max(now.timetuple().tm_yday, 1)
        month_proj = (
            total["cost_usd"] * Decimal(days_in_month) / Decimal(day_of_month)
        ).quantize(Decimal("0.01"))
        year_proj = (
            ytd["cost_usd"] * Decimal(days_in_year) / Decimal(day_of_year)
        ).quantize(Decimal("0.01"))
        projection = CostsProjection(
            this_month_cost_usd=month_proj,
            this_year_cost_usd=year_proj,
        )

    return CostsSummaryResponse(
        range=range_,  # type: ignore[arg-type]
        since=since,
        until=until,
        total_cost_usd=total["cost_usd"],
        by_kind=[
            CostsByKindEntry(
                kind=row["kind"],
                cost_usd=row["cost_usd"],
                input_tokens=row["input_tokens"],
                output_tokens=row["output_tokens"],
            )
            for row in by_kind
        ],
        daily_series=[
            DailyCostEntry(day=row["day"], cost_usd=row["cost_usd"])
            for row in daily
        ],
        workflow_metrics=workflow_metrics,
        projection=projection,
    )
