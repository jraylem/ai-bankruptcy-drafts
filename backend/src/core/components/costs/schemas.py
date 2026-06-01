"""Wire schemas for the costs API. Decimals are serialized as JSON
numbers (FastAPI handles this automatically); the FE rounds to 2dp at
render time."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, Field

CostRange = Literal["week", "month"]


class CostsByKindEntry(BaseModel):
    kind: str
    cost_usd: Decimal
    input_tokens: int
    output_tokens: int


class DailyCostEntry(BaseModel):
    day: datetime
    cost_usd: Decimal


class CostsProjection(BaseModel):
    this_month_cost_usd: Decimal
    this_year_cost_usd: Decimal
    method: str = "linear-extrapolation"


WorkflowCountUnit = Literal["session", "message", "run", "case"]


class WorkflowMetricEntry(BaseModel):
    """One breakdown line on a workflow card (e.g. "$0.25 avg / session · 12 sessions").

    Each workflow can carry multiple entries — chat has session + message + case,
    pleadings has run + case, case_ingest has case only.
    """
    unit: WorkflowCountUnit
    count: int
    avg_cost_usd: Decimal


class WorkflowMetric(BaseModel):
    """One workflow's rollup. The `metrics` list carries every breakdown
    available for the workflow; the FE renders them as separate lines.

    `total_cost_usd` is the headline number. For chat and pleadings, it's
    a scope-based SUM over `semantic_id_kind`, so it's FULL-LOADED — every
    nested agent call inside the scope is counted, not just kind=draft/chat.
    """
    total_cost_usd: Decimal
    metrics: list[WorkflowMetricEntry]


class WorkflowMetrics(BaseModel):
    """Per-workflow totals + averages for the studio Cost Center cards.

    Each workflow's `total_cost_usd` is the FULL-LOADED scope sum —
    every LLM row that fired inside that workflow's scope counts,
    regardless of which agent produced it. The per-agent split lives
    on the "Cost by activity" panel in the UI."""
    chat: WorkflowMetric
    pleadings: WorkflowMetric
    case_ingest: WorkflowMetric


class CostsSummaryResponse(BaseModel):
    range: CostRange
    since: datetime
    until: datetime
    total_cost_usd: Decimal
    by_kind: list[CostsByKindEntry] = Field(default_factory=list)
    daily_series: list[DailyCostEntry] = Field(default_factory=list)
    workflow_metrics: WorkflowMetrics
    # Projection is only meaningful for 'month' range; null on 'week'
    # since weekly-projected-to-anything is a meaningless extrapolation.
    projection: Optional[CostsProjection] = None
