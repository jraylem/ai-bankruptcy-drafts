"""Cases service — end-to-end ingestion of a bankruptcy petition PDF.

Top-level flow for POST /core/cases:
  1. Claude reads the petition PDF and returns structured {case_number, case_name, ...}
  2. Normalize the raw case number (e.g. '0:26-bk-10700' -> '26-10700')
  3. Sanitize for collection naming (e.g. '26-10700' -> '26_10700')
  4. Reject if a Case row with that id already exists (HTTP 409)
  5. Upload the petition PDF to R2
  6. Insert a Case row (DB first, collections anchored to a real case)
  7. Index the petition into case_file_{id}
  8. Backfill + index Gmail and Court Drive emails into their collections
"""

import asyncio
import logging
import uuid
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from src.core.agents.llm.case_ingestion import CaseIngestionAgent, CaseMetadata
from src.core.agents.types.sources import DEFAULT_SUPPORTING_DOC_EXTENSIONS
from src.core.common.storage.database import Case, CaseRepository
from src.core.common.cost_tracking import cost_attribution
from src.core.common.storage.r2 import r2_service
from src.core.components.case_inbox.pdf_parser import extract_ssn_last_four

from .email_indexer import EmailIndexer
from .identity import (
    case_resource_key,
    normalize_case_number as _normalize_case_number,
    sanitize_case_id as _sanitize_case_id,
)
from .pdf_indexer import PdfIndexer
from .schemas import (
    CaseCreateResponse,
    CaseListResponse,
    CasePetitionUrlResponse,
    CaseResponse,
    SupportingDocUploadResponse,
)

logger = logging.getLogger(__name__)

# Normalization helpers + the resource-key resolver live in cases/identity.py
# (leaf module with no agents/* imports) so callers from anywhere — including
# the agents/orchestration pipeline — can import them without circular-
# dependency risk. Re-exported here so existing call sites that did
# `from src.core.components.cases.service import _normalize_case_number`
# keep working.


async def create_case_from_petition(
    filename: str,
    pdf_bytes: bytes,
    *,
    firm_id: str | None,
) -> CaseCreateResponse:
    """End-to-end ingestion of a bankruptcy petition PDF.

    The LLM is the authoritative signal for filed vs unfiled. If
    `metadata.case_number` is None, the petition has not been filed yet
    (voluntary petition in preparation) and we create an `unfiled` Case
    row — no R2 collection naming, no pgvector indexing. When filing
    occurs later, Phase 2's `promote_unfiled` flow materializes those.

    The PK is always a UUID; the resource_key (sanitized case_number)
    drives R2 paths + pgvector collection names for filed cases. Unfiled
    cases use the UUID as their R2 path fallback.
    """
    metadata: CaseMetadata = await CaseIngestionAgent.run(pdf_bytes, filename)
    case_id = str(uuid.uuid4())
    ssn_last4, ssn_extraction_status = extract_ssn_last_four(pdf_bytes)

    if metadata.case_number is None:
        # Unfiled petition — no case_number, no resource collections,
        # no indexing. The row exists so paralegals can edit it later
        # and so a future ECF notice can match into it (Phase 2).
        case = await CaseRepository.create(
            case_id=case_id,
            case_name=metadata.case_name,
            firm_id=firm_id,
            resource_key=None,
            case_number=None,
            case_number_original=None,
            court_district=metadata.court_district,
            chapter=metadata.chapter,
            petition_pdf_url=None,
            ssn_last4=ssn_last4,
            ssn_extraction_status=ssn_extraction_status,
            status="unfiled",
        )

        # Still upload the PDF to R2 so the unfiled case has a viewable
        # document — the petition was provided, just not filed. Keyed
        # off the UUID since no sanitized case_number exists.
        await r2_service.upload_file(
            file_content=pdf_bytes,
            template_id=case_id,
            filename="petition.pdf",
            prefix="cases",
            content_type="application/pdf",
        )
        petition_pdf_url = await r2_service.get_presigned_url(
            template_id=case_id,
            filename="petition.pdf",
            prefix="cases",
        )
        case.petition_pdf_url = petition_pdf_url

        return CaseCreateResponse(
            case=CaseResponse.from_orm_case(case),
            case_file_chunks_indexed=0,
            gmail_emails_indexed=0,
            courtdrive_emails_indexed=0,
        )

    # Filed petition — normalize case_number and derive resource_key
    # for R2 + collection naming (keeps the "resource = sanitized
    # case_number" invariant across legacy + new filed rows).
    normalized = _normalize_case_number(metadata.case_number)
    resource_key = _sanitize_case_id(normalized)

    existing = await CaseRepository.get_by_case_number(normalized)
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Case {normalized} already exists",
        )

    await r2_service.upload_file(
        file_content=pdf_bytes,
        template_id=resource_key,
        filename="petition.pdf",
        prefix="cases",
        content_type="application/pdf",
    )
    petition_pdf_url = await r2_service.get_presigned_url(
        template_id=resource_key,
        filename="petition.pdf",
        prefix="cases",
    )

    try:
        case = await CaseRepository.create(
            case_id=case_id,
            case_name=metadata.case_name,
            firm_id=firm_id,
            resource_key=resource_key,
            case_number=normalized,
            case_number_original=metadata.case_number,
            court_district=metadata.court_district,
            chapter=metadata.chapter,
            petition_pdf_url=petition_pdf_url,
            ssn_last4=ssn_last4,
            ssn_extraction_status=ssn_extraction_status,
            status="filed",
        )
    except IntegrityError:
        # Race: another request inserted the same case_number between
        # our find_by_case_number probe and this INSERT. Partial UNIQUE
        # `uq_cases_case_number` is the source of truth.
        raise HTTPException(
            status_code=409,
            detail=f"Case {normalized} already exists",
        )

    # Now that case_id is known, nest a scope that adds the semantic
    # linkage. The outer scope (opened in cases/router.py) supplies
    # firm_id + user_id; this inner scope attaches semantic_id=case_id
    # to every cost row produced by the downstream indexers.
    with cost_attribution(
        case_id=case_id,
        semantic_id=case_id,
        semantic_id_kind="case",
    ):
        case_file_chunks = await PdfIndexer.index(
            case_id=case_id,
            resource_key=resource_key,
            pdf_bytes=pdf_bytes,
            case_metadata=metadata,
        )

        gmail_count, courtdrive_count = await EmailIndexer.index(
            case_id=case_id,
            resource_key=resource_key,
            case_number=normalized,
        )

    return CaseCreateResponse(
        case=CaseResponse.from_orm_case(case),
        case_file_chunks_indexed=case_file_chunks,
        gmail_emails_indexed=gmail_count,
        courtdrive_emails_indexed=courtdrive_count,
    )


async def retrieve_petition_pdf_by_case_number(case_number: str) -> tuple[str, bytes]:
    """Resolve a case_number to (filename, pdf_bytes) via the courtdrive
    extractor chain: local uploads cache → Google Drive → Gmail ECF link.

    Pure I/O — no LLM, no DB writes. Typed extractor exceptions are
    surfaced as HTTPException so the router doesn't have to know about
    courtdrive internals.
    """
    from src.courtdrive.petition_extractor import (
        PetitionAvailableForDownload,
        PetitionNotFoundError,
        download_petition_from_email,
        extract_petition_pdf,
    )

    case_number = (case_number or "").strip()
    if not case_number:
        raise HTTPException(status_code=400, detail="case_number is required")

    try:
        pdf_path = await extract_petition_pdf(case_number)
    except PetitionAvailableForDownload:
        # Gmail ECF link found but not yet downloaded — fetch eagerly.
        try:
            pdf_path = await download_petition_from_email(case_number)
        except PetitionNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
    except PetitionNotFoundError as exc:
        status = 410 if exc.reason == "link_expired" else 404
        raise HTTPException(status_code=status, detail=str(exc))

    pdf_bytes = pdf_path.read_bytes()
    if not pdf_bytes:
        raise HTTPException(status_code=502, detail="Extracted petition is empty")
    return pdf_path.name, pdf_bytes


async def create_case_from_case_number(
    case_number: str,
    *,
    firm_id: str | None,
) -> CaseCreateResponse:
    """Compose petition retrieval + standard ingestion.

    Both /case/new tabs (Upload PDF + Case Number) converge on
    `create_case_from_petition` so downstream behavior is identical.
    """
    filename, pdf_bytes = await retrieve_petition_pdf_by_case_number(case_number)
    return await create_case_from_petition(
        filename=filename, pdf_bytes=pdf_bytes, firm_id=firm_id,
    )


async def list_cases_with_signed_urls(*, limit: int, offset: int) -> CaseListResponse:
    """Paginated list of active cases with freshly-signed petition URLs.

    Re-signs every returned case's petition URL in parallel (1h TTL, the
    r2 default) so the FE can render PDFs without per-case follow-up
    fetches. Capping to a single page (limit) keeps the signing cost
    bounded — at 1000 cases we'd otherwise sign 1000 URLs per call.

    If a case has no stored petition (`petition_pdf_url is None`), it's
    left as None — the FE skips the preview for that case.
    """
    if limit <= 0:
        raise HTTPException(status_code=400, detail="limit must be >= 1")
    if limit > 100:
        raise HTTPException(status_code=400, detail="limit must be <= 100")
    if offset < 0:
        raise HTTPException(status_code=400, detail="offset must be >= 0")

    rows, total = await CaseRepository.list_paginated(limit=limit, offset=offset)

    async def _sign(case: Case) -> CaseResponse:
        response = CaseResponse.from_orm_case(case)
        if response.petition_pdf_url is None:
            return response
        try:
            response.petition_pdf_url = await r2_service.get_presigned_url(
                template_id=case_resource_key(case),
                filename="petition.pdf",
                prefix="cases",
            )
        except Exception as exc:  # noqa: BLE001 — surface as null URL, don't break the whole list
            logger.warning("Failed to re-sign petition URL for case %s: %s", case.id, exc)
            response.petition_pdf_url = None
        return response

    cases = await asyncio.gather(*(_sign(r) for r in rows))
    return CaseListResponse(
        cases=list(cases),
        total=total,
        limit=limit,
        offset=offset,
        has_more=offset + len(cases) < total,
    )


async def get_case_petition_url(case_id: str) -> CasePetitionUrlResponse:
    """Return a freshly-signed R2 URL for the case's petition PDF.

    The `petition_pdf_url` column on the Case row is signed once at
    create time and expires once R2's TTL elapses; callers that need a
    working URL later must go through this endpoint. The R2 key derives
    from `case_resource_key(case)` (legacy_id for migrated rows,
    sanitized case_number for new filed rows, UUID for unfiled).
    """
    case = await CaseRepository.get(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")

    petition_pdf_url = await r2_service.get_presigned_url(
        template_id=case_resource_key(case),
        filename="petition.pdf",
        prefix="cases",
    )
    return CasePetitionUrlResponse(petition_pdf_url=petition_pdf_url)


_SUPPORTING_DOC_CONTENT_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "txt": "text/plain",
    "md": "text/markdown",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
}


async def upload_supporting_doc(
    case_id: str,
    filename: str,
    content: bytes,
) -> SupportingDocUploadResponse:
    """Upload one supporting doc under cases/{case_id}/supporting_docs/{uuid}.{ext}.

    Validates the case exists, the filename has an allowed extension, and
    the upload isn't empty. Returns the R2 key (file_url) the FE embeds in
    a SupportingDocsPick when resuming a user_input_with_supporting_docs
    field.
    """
    if not content:
        raise HTTPException(status_code=400, detail="Empty supporting-doc upload")

    case = await CaseRepository.get(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")

    ext = Path(filename).suffix.lstrip(".").lower()
    if not ext:
        raise HTTPException(
            status_code=400,
            detail=f"Supporting doc '{filename}' has no file extension",
        )
    if ext not in DEFAULT_SUPPORTING_DOC_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Supporting doc extension '{ext}' not supported. "
                f"Supported: {', '.join(DEFAULT_SUPPORTING_DOC_EXTENSIONS)}."
            ),
        )

    stored_name = f"{uuid.uuid4()}.{ext}"
    r2_filename = f"supporting_docs/{stored_name}"
    content_type = _SUPPORTING_DOC_CONTENT_TYPES.get(ext, "application/octet-stream")

    # Use case_resource_key so legacy cases keep landing under
    # cases/<sanitized>/supporting_docs/... — matches both their
    # existing R2 layout and any persisted SupportingDocsPick file_urls
    # that were saved before the migration.
    resource_key = case_resource_key(case)
    key = await r2_service.upload_file(
        file_content=content,
        template_id=resource_key,
        filename=r2_filename,
        prefix="cases",
        content_type=content_type,
    )
    presigned_url = await r2_service.get_presigned_url(
        template_id=resource_key,
        filename=r2_filename,
        prefix="cases",
    )

    return SupportingDocUploadResponse(
        file_url=key,
        presigned_url=presigned_url,
        filename=filename,
    )
