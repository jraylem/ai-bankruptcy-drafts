"""Wire schemas for the v2 ECF inbox API.

Two list endpoints (ready + archived) share a row shape. The accept
endpoint returns the existing `CaseCreateResponse` from the cases
component — the same shape `POST /api/v2/core/cases` already returns,
so the FE can treat Accept/Summon and manual upload uniformly.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

SsnExtractionStatus = Literal["found", "not_found", "scanned_image"]
CaseInboxStatus = Literal[
    "ingesting", "ready", "accepted", "archived", "failed_ingest",
]


class MatchedUnfiledCaseSummary(BaseModel):
    """Minimal Case summary embedded on an inbox entry when a matching
    unfiled case was found at ingest time. Drives the Accept/Reject
    confirm modals' 'Existing unfiled case found' heads-up block."""
    id: str
    case_name: str
    ssn_last4: Optional[str] = None
    created_at: datetime


class CaseInboxEntry(BaseModel):
    """One inbox row — used by both /list and /archived responses."""
    id: str
    case_number: Optional[str] = None
    case_name: Optional[str] = None
    ssn_last4: Optional[str] = None
    ssn_extraction_status: SsnExtractionStatus
    court_district: Optional[str] = None
    status: CaseInboxStatus
    source: str
    received_at: Optional[datetime] = None
    created_at: datetime
    archived_at: Optional[datetime] = None
    dismissed_by_user_id: Optional[str] = None
    # Presigned R2 URL — 1h TTL. Re-signed on every list response.
    petition_pdf_url: Optional[str] = None
    # Phase 2 unfiled-petition match — populated at ingest time by the
    # matcher; re-evaluated at accept/dismiss time. The nested summary
    # carries enough info for the FE modal to render without a follow-up
    # GET /cases/<id> round-trip.
    matches_unfiled_case_id: Optional[str] = None
    matched_unfiled_case: Optional[MatchedUnfiledCaseSummary] = None


class CaseInboxListResponse(BaseModel):
    """Both /list and /archived return this shape. The FE distinguishes
    main-inbox vs archived rendering via `status` on each entry."""
    entries: list[CaseInboxEntry] = Field(default_factory=list)


class DismissResponse(BaseModel):
    """`POST /case-inbox/{id}/dismiss` ack.

    `case` is populated only on the Phase 2 reject-with-merge path —
    when the inbox row had an unfiled counterpart, the dismiss flow
    also promoted that unfiled case to filed, and the FE renders an
    outcome-aware toast reflecting that.
    """
    ok: bool = True
    id: str
    case: Optional["CaseResponse"] = None  # forward ref — resolved below


# Late import to keep schemas.py free of cross-module dependencies in
# the common case and avoid circular imports between cases + case_inbox.
from src.core.components.cases.schemas import CaseResponse  # noqa: E402

DismissResponse.model_rebuild()
