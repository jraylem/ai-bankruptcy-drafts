"""HTTP routes for the v2 ECF inbox.

Four endpoints. All firm-scoped via `get_current_firm_user`.

  GET  /api/v2/core/case-inbox/list        — status='ready' inbox
  GET  /api/v2/core/case-inbox/archived    — status='archived' (summon list)
  POST /api/v2/core/case-inbox/{id}/accept — Accept OR Summon (same endpoint)
  POST /api/v2/core/case-inbox/{id}/dismiss — soft-delete to archived
"""

from __future__ import annotations

import logging
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Path, Query

from src.auth.models import User
from src.common.dependencies import get_current_firm_user
from src.core.components.cases.schemas import CaseCreateResponse, CaseResponse

from . import service
from .schemas import CaseInboxListResponse, DismissResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/case-inbox", tags=["Case Inbox"])


@router.get("/list", response_model=CaseInboxListResponse)
async def list_ready(
    user: Annotated[User, Depends(get_current_firm_user)] = None,  # type: ignore[assignment]
) -> CaseInboxListResponse:
    """Firm-scoped list of pending petitions (status='ready')."""
    return await service.list_ready(firm_id=user.firm_id)


@router.get("/archived", response_model=CaseInboxListResponse)
async def list_archived(
    q: Annotated[Optional[str], Query(description="Case number / debtor name search")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    user: Annotated[User, Depends(get_current_firm_user)] = None,  # type: ignore[assignment]
) -> CaseInboxListResponse:
    """Archived petitions — recoverable via the same /accept endpoint
    (FE labels the button 'Summon' when the source is archived)."""
    return await service.list_archived(
        firm_id=user.firm_id, q=q, limit=limit, offset=offset,
    )


@router.post("/{id}/accept", response_model=CaseCreateResponse)
async def accept(
    id: Annotated[str, Path()],
    user: Annotated[User, Depends(get_current_firm_user)] = None,  # type: ignore[assignment]
) -> CaseCreateResponse:
    """Accept a ready row OR Summon an archived row — same endpoint, same
    downstream Case-creation flow (`create_case_from_petition`)."""
    return await service.accept(inbox_id=id, firm_id=user.firm_id, user_id=user.id)


@router.post("/{id}/dismiss", response_model=DismissResponse)
async def dismiss(
    id: Annotated[str, Path()],
    user: Annotated[User, Depends(get_current_firm_user)] = None,  # type: ignore[assignment]
) -> DismissResponse:
    """Soft-delete to archived. R2 bytes stay so the row remains
    summonable via the archived list.

    Phase 2: when the inbox row matches an unfiled counterpart, the
    dismiss flow ALSO promotes that unfiled case to filed before
    archiving. The promoted case is returned on `case` so the FE can
    render an outcome-aware toast.
    """
    case_response = await service.dismiss(
        inbox_id=id, firm_id=user.firm_id, user_id=user.id,
    )
    merged_case: Optional[CaseResponse] = (
        case_response.case if case_response is not None else None
    )
    return DismissResponse(id=id, case=merged_case)
