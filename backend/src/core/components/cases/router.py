"""HTTP routes for the /cases endpoints — case creation, listing, retrieval, and supporting-doc uploads."""

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel

from src.auth.auth import get_current_user_optional
from src.auth.models import User
from src.core.common.cost_tracking import cost_attribution
from src.core.common.storage.database import CaseRepository

from .schemas import (
    CaseCreateResponse,
    CaseListResponse,
    CasePetitionUrlResponse,
    CaseResponse,
    SupportingDocUploadResponse,
)
from .service import (
    create_case_from_case_number,
    create_case_from_petition,
    get_case_petition_url,
    list_cases_with_signed_urls,
    upload_supporting_doc,
)


class CaseExtractByNumberRequest(BaseModel):
    case_number: str

router = APIRouter(prefix="/cases")


# ─── Routes ───


@router.post("", response_model=CaseCreateResponse)
async def create_case_endpoint(
    petition: UploadFile = File(...),
    current_user: Annotated[Optional[User], Depends(get_current_user_optional)] = None,
):
    """Create a new case by uploading a bankruptcy petition PDF.

    Reads the petition with Claude to extract case number and debtor name,
    persists a Case row, then ingests the petition PDF and matching
    Gmail / Court Drive emails into per-case pgvector collections.
    """
    pdf_bytes = await petition.read()
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="Empty petition upload")
    filename = petition.filename or "petition.pdf"
    firm_id = getattr(current_user, "firm_id", None) if current_user else None
    # Scope cost attribution so the case-ingestion + embedding rows in
    # llm_cost_logs carry the firm_id (and user_id when available).
    with cost_attribution(
        firm_id=firm_id,
        user_id=getattr(current_user, "id", None) if current_user else None,
    ):
        return await create_case_from_petition(
            filename=filename, pdf_bytes=pdf_bytes, firm_id=firm_id,
        )


@router.post("/extract-by-number", response_model=CaseCreateResponse)
async def extract_case_by_number_endpoint(
    body: CaseExtractByNumberRequest,
    current_user: Annotated[Optional[User], Depends(get_current_user_optional)] = None,
):
    """Create a new case by looking up the petition PDF via case number.

    Resolves the docket number through the courtdrive extractor chain
    (uploads cache → Google Drive → Gmail ECF link), then runs the same
    ingestion pipeline as the file-upload path. Mirrors POST /cases in
    cost-attribution and firm-scoping; differs only in input source.
    """
    firm_id = getattr(current_user, "firm_id", None) if current_user else None
    with cost_attribution(
        firm_id=firm_id,
        user_id=getattr(current_user, "id", None) if current_user else None,
    ):
        return await create_case_from_case_number(
            case_number=body.case_number, firm_id=firm_id,
        )


@router.get("", response_model=CaseListResponse)
async def list_cases_endpoint(
    limit: int = Query(20, ge=1, le=100, description="Page size, max 100."),
    offset: int = Query(0, ge=0, description="Pagination offset."),
):
    """Paginated list of active cases, newest first, with freshly-signed
    petition URLs (1h TTL) baked into each row so the FE can render the
    PDF directly without a follow-up per-case sign request.

    Capped at 100 per page; FE defaults to 20 and uses `has_more` to
    drive a Load More button — this keeps the BE from signing thousands
    of URLs at once when a firm has many cases.
    """
    return await list_cases_with_signed_urls(limit=limit, offset=offset)


@router.get("/{case_id}", response_model=CaseResponse)
async def get_case_endpoint(case_id: str):
    """Fetch a single case by its sanitized case_id."""
    case = await CaseRepository.get(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")
    return CaseResponse.from_orm_case(case)


@router.get("/{case_id}/petition-url", response_model=CasePetitionUrlResponse)
async def get_case_petition_url_endpoint(case_id: str):
    """Return a freshly-signed R2 URL for this case's petition PDF.

    The persisted `Case.petition_pdf_url` expires over time; FE callers
    that need a working preview URL must request one here on demand.
    """
    return await get_case_petition_url(case_id)


@router.post("/{case_id}/supporting-docs", response_model=list[SupportingDocUploadResponse])
async def upload_supporting_docs_endpoint(
    case_id: str,
    files: list[UploadFile] = File(...),
):
    """Upload one or more supporting docs for a user_input_with_supporting_docs field.

    The FE uploads files here BEFORE resuming a draft/dry-run that paused
    on such a field. Returns one SupportingDocUploadResponse per uploaded
    file (in the same order); the FE concatenates every returned `file_url`
    into the resume pick's `file_urls` list.

    Each file is validated and uploaded sequentially — if ANY file fails
    validation (empty, unknown extension, case not found), the whole request
    returns the error and no files are persisted beyond that point.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    responses: list[SupportingDocUploadResponse] = []
    for file in files:
        content = await file.read()
        filename = file.filename or "unnamed"
        responses.append(
            await upload_supporting_doc(case_id=case_id, filename=filename, content=content)
        )
    return responses
