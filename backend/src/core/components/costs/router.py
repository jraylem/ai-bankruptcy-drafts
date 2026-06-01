"""HTTP routes for the studio Costs panel."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from src.auth.models import User
from src.common.dependencies import get_current_firm_user

from . import service
from .schemas import CostRange, CostsSummaryResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/costs", tags=["Costs"])


@router.get("/summary", response_model=CostsSummaryResponse)
async def costs_summary(
    range_: Annotated[CostRange, Query(alias="range")] = "month",
    user: Annotated[User, Depends(get_current_firm_user)] = None,  # type: ignore[assignment]
) -> CostsSummaryResponse:
    """Firm-scoped aggregate of LLM spend for the chosen range.

    `range=month` (default): MTD totals + monthly + yearly projections.
    `range=week`: rolling 7-day totals only (no projection — weekly
    extrapolation is meaningless).

    Auth: requires a firm user (uses the same dependency every
    tenant-scoped /core route uses). NULL-firm rows (e.g. anonymous
    pre-cookie-auth case ingestions) are excluded from the rollup.
    """
    firm_id = getattr(user, "firm_id", None)
    return await service.build_summary(firm_id=firm_id, range_=range_)
