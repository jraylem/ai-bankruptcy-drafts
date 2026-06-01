"""Costs component — read-only telemetry for studio's Costs panel.

GET /api/v2/core/costs/summary?range=week|month — firm-scoped aggregate
of `llm_cost_logs` rows, sliced by `kind`, with linear projection for
this month / this year.
"""

from .router import router

__all__ = ["router"]
