"""Service layer for the v2 ECF inbox.

Three flows:
  - list_ready / list_archived : firm-scoped fetch + presign petition URLs
  - dismiss                     : soft-delete (transitions to status='archived'
                                  with dismissed_by_user_id populated).
                                  When the case_inbox row matches an unfiled
                                  petition, ALSO promotes the unfiled case
                                  to filed (Phase 2 merge-on-reject).
  - accept / summon             : creates or merges into a Case. New case via
                                  create_case_from_petition (same path as
                                  manual dropzone). Merge via promote_unfiled
                                  when an unfiled counterpart is found.
                                  Returns the CaseCreateResponse either way.

The matcher's verdict is binding for BOTH accept and dismiss when a
match exists — the difference between the two actions collapses to
inbox state (`accepted`+navigate vs `archived`) and not to whether the
underlying merge happens.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import HTTPException

from src.core.agents.llm.case_ingestion import CaseIngestionAgent, CaseMetadata
from src.core.common.cost_tracking import cost_attribution
from src.core.common.storage.database import (
    Case,
    CaseInbox,
    CaseInboxRepository,
    CaseRepository,
)
from src.core.common.storage.r2 import r2_service
from src.core.components.cases.email_indexer import EmailIndexer
from src.core.components.cases.identity import (
    case_resource_key,
    normalize_case_number,
    sanitize_case_id,
)
from src.core.components.cases.pdf_indexer import PdfIndexer
from src.core.components.cases.schemas import CaseCreateResponse, CaseResponse
from src.core.components.cases.service import create_case_from_petition

from .schemas import CaseInboxEntry, CaseInboxListResponse, MatchedUnfiledCaseSummary

logger = logging.getLogger(__name__)

_PRESIGNED_TTL_SECONDS = 3600


async def list_ready(*, firm_id: str) -> CaseInboxListResponse:
    """Main `/inbox` list. Returns ready rows + presigned R2 URLs."""
    rows = await CaseInboxRepository.list_ready(firm_id=firm_id)
    matched_summaries = await _fetch_matched_unfiled_summaries(rows)
    return CaseInboxListResponse(
        entries=[await _to_entry(r, matched_summaries) for r in rows],
    )


async def list_archived(
    *,
    firm_id: str,
    q: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> CaseInboxListResponse:
    """`/inbox/archived` — search-filterable, paginated."""
    rows = await CaseInboxRepository.list_archived(
        firm_id=firm_id, q=q, limit=limit, offset=offset,
    )
    matched_summaries = await _fetch_matched_unfiled_summaries(rows)
    return CaseInboxListResponse(
        entries=[await _to_entry(r, matched_summaries) for r in rows],
    )


async def dismiss(
    *,
    inbox_id: str,
    firm_id: str,
    user_id: str,
) -> Optional[CaseCreateResponse]:
    """Soft-delete a ready row → status='archived'.

    Phase 2: when the row has a matched unfiled counterpart (re-evaluated
    at action time), ALSO promotes the unfiled case to filed before
    archiving the inbox row. Returns the CaseCreateResponse for the
    promoted case in that path so the FE can render an accurate toast;
    returns None when no match exists (pure-archive — original behavior).
    """
    row = await CaseInboxRepository.get(id=inbox_id)
    if row is None or row.firm_id != firm_id:
        raise HTTPException(status_code=404, detail="Inbox entry not found")
    if row.status != "ready":
        raise HTTPException(
            status_code=409,
            detail=f"Cannot dismiss — entry is already {row.status}",
        )

    case_response: Optional[CaseCreateResponse] = None
    if _matcher_can_run(row):
        case_response = await _resolve_match_or_create(
            row=row,
            user_id=user_id,
            create_when_no_match=False,
        )

    rowcount = await CaseInboxRepository.mark_dismissed_to_archive(
        id=inbox_id, user_id=user_id,
    )
    if rowcount == 0:
        raise HTTPException(
            status_code=409,
            detail="Already handled by another firm member",
        )
    return case_response


async def accept(
    *,
    inbox_id: str,
    firm_id: str,
    user_id: str,
) -> CaseCreateResponse:
    """Accept (or Summon) — converts an inbox row into a real Case.

    Two routing paths:
      - No matched unfiled counterpart → create_case_from_petition (the
        manual-dropzone flow; LLM extracts fresh, indexes everything).
      - Matched unfiled counterpart    → promote_unfiled (flip status to
        filed in-place; reuse the existing cases row).

    Either way, the inbox row is marked accepted and the case_inbox R2
    copy is deleted afterward.
    """
    row = await CaseInboxRepository.get(id=inbox_id)
    if row is None or row.firm_id != firm_id:
        raise HTTPException(status_code=404, detail="Inbox entry not found")
    if row.status not in ("ready", "archived"):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot accept — entry is {row.status}",
        )

    case_response = await _resolve_match_or_create(
        row=row,
        user_id=user_id,
        create_when_no_match=True,
    )
    if case_response is None:
        # Helper only returns None when create_when_no_match=False — the
        # accept path always creates or merges, so this is unreachable.
        raise HTTPException(
            status_code=500,
            detail="accept resolution returned no case unexpectedly",
        )

    rowcount = await CaseInboxRepository.mark_accepted(
        id=inbox_id,
        case_id=case_response.case.id,
        user_id=user_id,
    )
    if rowcount == 0:
        raise HTTPException(
            status_code=409,
            detail="Already handled by another firm member",
        )

    try:
        await r2_service.delete_object(key=row.petition_r2_key)
    except Exception as e:
        logger.warning(
            "Failed to delete inbox R2 key %s after accept: %s",
            row.petition_r2_key, e,
        )

    from src.common.audit import log_audit_event
    await log_audit_event(
        firm_id=firm_id,
        action="case.accepted",
        user_id=user_id,
        resource_type="case",
        resource_id=case_response.case.id,
        metadata={"inbox_id": inbox_id, "case_number": case_response.case.case_number},
    )

    return case_response


# ─── private helpers ──────────────────────────────────────────────────


def _matcher_can_run(row: CaseInbox) -> bool:
    """Matcher needs (firm_id, ssn_last4, case_name) to operate.

    Rows missing any of those (e.g. SSN extraction failed at ingest)
    cannot match an unfiled counterpart. Skipping the matcher entirely
    in that case keeps the dismiss path's existing pure-archive behavior
    intact when there's no signal to act on.
    """
    return bool(row.firm_id and row.ssn_last4 and row.case_name)


async def _resolve_match_or_create(
    *,
    row: CaseInbox,
    user_id: str,
    create_when_no_match: bool,
) -> Optional[CaseCreateResponse]:
    """Shared accept/dismiss routing — matcher re-run + merge OR create.

    Re-runs find_unfiled_match at action time (don't trust the ingest-
    time hint blindly; a new unfiled case could have appeared, or the
    stored match could have been promoted via another path). Persists
    the fresh result back to the row, then routes:

      - Fresh match found    → load + guard + R2 move + promote_unfiled
      - No match found:
        - create_when_no_match=True  → create_case_from_petition
        - create_when_no_match=False → return None (dismiss-no-match)

    Returns the CaseCreateResponse for the resulting case, or None only
    in the dismiss-no-match branch.
    """
    fresh_match_id: Optional[str] = None
    if _matcher_can_run(row):
        fresh_match_id = await CaseRepository.find_unfiled_match(
            firm_id=row.firm_id,
            ssn_last4=row.ssn_last4,
            case_name=row.case_name,
        )

    if fresh_match_id != row.matches_unfiled_case_id:
        await CaseInboxRepository.update_matches_unfiled_case_id(
            id=row.id, matches_unfiled_case_id=fresh_match_id,
        )

    if fresh_match_id is None:
        if not create_when_no_match:
            return None
        return await _create_new_case(row=row, user_id=user_id)

    return await _merge_into_unfiled(
        row=row, target_case_id=fresh_match_id, user_id=user_id,
    )


async def _create_new_case(
    *, row: CaseInbox, user_id: str,
) -> CaseCreateResponse:
    """No-match path: download bytes, delegate to create_case_from_petition."""
    pdf_bytes = await _download_inbox_pdf(row)
    filename = f"inbox_{row.id}.pdf"
    with cost_attribution(firm_id=row.firm_id, user_id=user_id):
        return await create_case_from_petition(
            filename=filename, pdf_bytes=pdf_bytes, firm_id=row.firm_id,
        )


async def _merge_into_unfiled(
    *, row: CaseInbox, target_case_id: str, user_id: str,
) -> CaseCreateResponse:
    """Match path: promote the unfiled case to filed using THIS notice's
    PDF + LLM-extracted metadata. Re-uses the existing cases.id.
    """
    target = await CaseRepository.get(target_case_id)
    if target is None:
        # Stored match pointed at a row that vanished (extremely unlikely
        # — soft-delete makes rows inactive but get() filters is_active).
        raise HTTPException(
            status_code=409,
            detail="Matched unfiled case is no longer accessible; please retry.",
        )

    # Defensive cross-firm guard — matcher already enforces this at ingest,
    # but a re-check at the irreversible promotion moment makes the
    # security model self-evident.
    if target.firm_id != row.firm_id:
        logger.warning(
            "Cross-firm match attempt blocked: inbox_firm=%s target_firm=%s "
            "inbox_id=%s target_id=%s",
            row.firm_id, target.firm_id, row.id, target.id,
        )
        raise HTTPException(
            status_code=409,
            detail="Matched case is in a different firm; please retry.",
        )

    # Stale-status guard — concurrent promotion via another path.
    if target.status != "unfiled":
        raise HTTPException(
            status_code=409,
            detail="Matched case has already been filed; please retry.",
        )

    pdf_bytes = await _download_inbox_pdf(row)
    filename = f"inbox_{row.id}.pdf"

    with cost_attribution(
        firm_id=row.firm_id,
        user_id=user_id,
        case_id=target.id,
        semantic_id=target.id,
        semantic_id_kind="case",
    ):
        metadata: CaseMetadata = await CaseIngestionAgent.run(pdf_bytes, filename)

        if metadata.case_number is None:
            # The court notice's PDF didn't surface a case_number — the
            # notice itself implies the case IS filed, so this is an LLM
            # extraction failure rather than legitimate unfiled state.
            # Bail rather than promote with case_number=NULL (which would
            # violate the "filed → case_number NOT NULL" invariant).
            raise HTTPException(
                status_code=422,
                detail=(
                    "Could not extract a case_number from the court notice "
                    "PDF; cannot merge into the unfiled case."
                ),
            )

        normalized = normalize_case_number(metadata.case_number)
        resource_key = sanitize_case_id(normalized)
        old_resource_key = case_resource_key(target)

        # Move the petition PDF in R2: cases/<uuid>/petition.pdf → cases/<sanitized>/petition.pdf.
        # The unfiled row had a draft PDF; the court notice's PDF is the
        # canonical filed document and replaces it.
        new_r2_key = f"cases/{resource_key}/petition.pdf"
        old_r2_key = f"cases/{old_resource_key}/petition.pdf"
        await r2_service.upload_by_key(
            key=new_r2_key,
            file_content=pdf_bytes,
            content_type="application/pdf",
        )
        petition_pdf_url = await r2_service.get_presigned_url(
            template_id=resource_key,
            filename="petition.pdf",
            prefix="cases",
        )
        if old_r2_key != new_r2_key:
            try:
                await r2_service.delete_object(key=old_r2_key)
            except Exception as e:
                logger.warning(
                    "Failed to delete old unfiled R2 key %s after merge: %s",
                    old_r2_key, e,
                )

        promoted: Case = await CaseRepository.promote_unfiled(
            case_id=target.id,
            case_number=normalized,
            case_number_original=metadata.case_number,
            court_district=metadata.court_district,
            chapter=metadata.chapter,
            resource_key=resource_key,
            petition_pdf_url=petition_pdf_url,
        )

        case_file_chunks = await PdfIndexer.index(
            case_id=promoted.id,
            resource_key=resource_key,
            pdf_bytes=pdf_bytes,
            case_metadata=metadata,
        )
        gmail_count, courtdrive_count = await EmailIndexer.index(
            case_id=promoted.id,
            resource_key=resource_key,
            case_number=normalized,
        )

    return CaseCreateResponse(
        case=CaseResponse.from_orm_case(promoted),
        case_file_chunks_indexed=case_file_chunks,
        gmail_emails_indexed=gmail_count,
        courtdrive_emails_indexed=courtdrive_count,
    )


async def _download_inbox_pdf(row: CaseInbox) -> bytes:
    """Fetch the petition bytes from R2 (in-memory, never disk)."""
    try:
        return await r2_service.download_by_key(key=row.petition_r2_key)
    except Exception as e:
        logger.exception("R2 download failed for inbox %s", row.id)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch petition bytes from R2: {e}",
        )


async def _fetch_matched_unfiled_summaries(
    rows: list[CaseInbox],
) -> dict[str, MatchedUnfiledCaseSummary]:
    """Batch-fetch nested summaries for rows with matches_unfiled_case_id.

    Returns {cases.id: summary}. Most inbox rows have no match so this
    will return {} or a tiny dict.
    """
    ids = {r.matches_unfiled_case_id for r in rows if r.matches_unfiled_case_id}
    if not ids:
        return {}
    out: dict[str, MatchedUnfiledCaseSummary] = {}
    for cid in ids:
        case = await CaseRepository.get(cid)
        if case is None:
            continue
        out[cid] = MatchedUnfiledCaseSummary(
            id=case.id,
            case_name=case.case_name,
            ssn_last4=case.ssn_last4,
            created_at=case.created_at,
        )
    return out


async def _to_entry(
    row: CaseInbox,
    matched_summaries: dict[str, MatchedUnfiledCaseSummary] | None = None,
) -> CaseInboxEntry:
    """Map ORM row → wire shape, re-signing the R2 URL for display."""
    petition_url: Optional[str] = None
    if row.petition_r2_key:
        try:
            petition_url = await r2_service.get_presigned_url_by_key(
                key=row.petition_r2_key, expires_in=_PRESIGNED_TTL_SECONDS,
            )
        except Exception as e:
            logger.warning(
                "presign failed for inbox %s (key=%s): %s",
                row.id, row.petition_r2_key, e,
            )
    matched_unfiled_case: Optional[MatchedUnfiledCaseSummary] = None
    if row.matches_unfiled_case_id and matched_summaries:
        matched_unfiled_case = matched_summaries.get(row.matches_unfiled_case_id)
    return CaseInboxEntry(
        id=row.id,
        case_number=row.case_number,
        case_name=row.case_name,
        ssn_last4=row.ssn_last4,
        ssn_extraction_status=row.ssn_extraction_status or "not_found",
        court_district=row.court_district,
        status=row.status,  # type: ignore[arg-type]
        source=row.source,
        received_at=row.received_at,
        created_at=row.created_at,
        archived_at=row.archived_at,
        dismissed_by_user_id=row.dismissed_by_user_id,
        petition_pdf_url=petition_url,
        matches_unfiled_case_id=row.matches_unfiled_case_id,
        matched_unfiled_case=matched_unfiled_case,
    )
