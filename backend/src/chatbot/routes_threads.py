"""Thread management routes for the chatbot module."""

import hashlib
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends
from pathlib import Path
from typing import Any, Literal, Optional
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from ..auth.models import User
from ..common.dependencies import get_current_firm_user
from .database import (
    AsyncSessionLocal,
    create_or_update_chat_thread,
    create_session,
    create_session_with_id,
    deactivate_session,
    get_latest_session_pdf,
    get_session_pdfs as db_get_session_pdfs,
    get_session_chat_thread as db_get_session_chat_thread,
    get_user_inbox_initialized_at,
    get_user_session as db_get_user_session,
    list_all_threads as db_list_all_threads,
    list_messages as db_list_messages,
    list_sessions as db_list_sessions,
    create_or_update_session_pdf_metadata,
    set_user_inbox_initialized_at,
    update_session_petition_inbox_state,
    update_thread_metadata as db_update_thread_metadata,
    delete_thread as db_delete_thread,
    log_user_action,
)
from ..courtdrive.service import (
    extract_ssn_from_uploaded_petition_pdfs,
    normalize_case_value,
    normalize_client_name,
    scan_uploaded_petition_identities,
    strip_case_number_suffix,
)
from ..courtdrive.ingestion_db import (
    create_or_update_ingestion,
    get_all_ingestions_for_session,
    list_pending_acceptance_states,
    mark_pending_acceptance_viewed,
)
from ..gmail.workflow_services import DEFAULT_TRIGGER_SENDERS
from .pending_petitions import (
    PendingPetitionResolutionError,
    PendingPetitionResolutionService,
    _resolve_managed_path,
)

router = APIRouter()

_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
_UPLOADS_ROOT = _BACKEND_ROOT / "uploads"
pending_petition_resolution_service = PendingPetitionResolutionService()


class PendingPetitionResolveRequest(BaseModel):
    """Request body for resolving one pending petition."""

    action: Literal["accept", "deny", "merge", "replace", "merge_schedule"]
    target_session_id: Optional[str] = None
    client_name: Optional[str] = None
    ssn_last4: Optional[str] = None
    case_number: Optional[str] = None
    sender_emails: list[str] = Field(default_factory=lambda: list(DEFAULT_TRIGGER_SENDERS))
    max_results: int = Field(default=25, ge=1, le=200)


def _utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


def _resolve_upload_path(path: Optional[str]) -> Optional[Path]:
    """Resolve stored PDF paths against the backend uploads directory."""
    candidate = (path or "").strip()
    if not candidate:
        return None

    parsed = Path(candidate)
    if candidate.startswith("/uploads/"):
        resolved = (_BACKEND_ROOT / candidate.lstrip("/")).resolve()
    elif parsed.is_absolute():
        resolved = parsed.resolve()
    elif parsed.parts and parsed.parts[0] == "uploads":
        resolved = (_BACKEND_ROOT / parsed).resolve()
    else:
        resolved = (_UPLOADS_ROOT / parsed).resolve()
    return resolved


def _is_within_uploads_root(path: Path) -> bool:
    """Return True when the path lives under the managed uploads directory."""
    try:
        path.relative_to(_UPLOADS_ROOT)
        return True
    except ValueError:
        return False


def _is_uploads_root_pdf(path: Optional[str]) -> bool:
    """Return True when the path points to a PDF stored anywhere under /uploads."""
    resolved = _resolve_upload_path(path)
    return bool(
        resolved
        and resolved.suffix.lower() == ".pdf"
        and _is_within_uploads_root(resolved)
    )


def _is_pending_inbox_external_upload(filename: Optional[str]) -> bool:
    """Allow only CourtDrive petition PDFs, not session uploads like bankruptcy_petition_<session_id>.pdf."""
    normalized_name = Path((filename or "").strip()).name
    return (
        normalized_name.startswith("Bankruptcy_Petition_")
        and normalized_name.lower().endswith(".pdf")
    )


def _compute_file_fingerprint(path: Optional[str]) -> Optional[str]:
    """Compute a stable fingerprint for a stored PDF path when possible."""
    resolved = _resolve_upload_path(path)
    if not resolved or not resolved.exists() or not resolved.is_file():
        return None

    digest = hashlib.sha256()
    with resolved.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _normalize_pending_file_path(path: Optional[str]) -> Optional[str]:
    """Return a stable absolute path string for dedupe comparisons."""
    resolved = _resolve_upload_path(path)
    if resolved:
        return str(resolved)
    candidate = (path or "").strip()
    return candidate or None


def _serialize_pdf_document(pdf) -> dict[str, Any]:
    """Serialize a PDF row for pending Inbox responses."""
    return {
        "id": pdf.id,
        "filename": pdf.filename,
        "original_filename": pdf.original_filename,
        "path": pdf.file_path,
        "size_bytes": pdf.file_size,
        "uploaded_at": pdf.uploaded_at.isoformat()
        if getattr(pdf, "uploaded_at", None)
        else None,
        "inbox_checked_at": pdf.inbox_checked_at.isoformat()
        if getattr(pdf, "inbox_checked_at", None)
        else None,
        "petition_status": getattr(pdf, "petition_status", None),
        "is_active": bool(getattr(pdf, "is_active", False)),
    }


def _build_external_pending_result(
    session_id: str,
    thread_id: str,
    upload_record: dict[str, Any],
    petition_document: dict[str, Any],
    *,
    status: str,
) -> dict[str, Any]:
    """Build the stored pending result for one external upload."""
    title = (upload_record.get("client_name") or "").strip() or None
    case_number = (upload_record.get("case_number") or "").strip() or None
    received_at = (
        petition_document.get("uploaded_at")
        or _utc_now().isoformat()
    )

    return {
        "id": thread_id,
        "session_id": session_id,
        "status": status,
        "source": "external_upload",
        "source_label": "External upload",
        "title": title,
        "client_name": title,
        "ssn_last4": (upload_record.get("ssn_last4") or "").strip() or None,
        "case_number": case_number,
        "received_at": received_at,
        "matched_external_filename": upload_record.get("filename"),
        "matched_external_case_number": upload_record.get("case_number"),
        "matched_external_court_region": upload_record.get("court_region"),
        "petition_file_path": petition_document.get("path"),
        "petition_file_fingerprint": (
            upload_record.get("file_fingerprint")
            or petition_document.get("fingerprint")
        ),
        "petition_document": petition_document,
        "petition_status": petition_document.get("petition_status"),
        "inbox_checked_at": petition_document.get("inbox_checked_at"),
    }


def _build_pending_petition_entry(
    session_obj,
    thread,
    pending_state: dict[str, Any],
    petition_document: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build one pending Inbox item from a stored pending_acceptance record."""
    pending_result = pending_state.get("result")
    if not isinstance(pending_result, dict):
        pending_result = {}

    normalized_petition = petition_document if isinstance(petition_document, dict) else {}
    title = (
        (pending_result.get("title") or "").strip()
        or (pending_result.get("client_name") or "").strip()
        or (getattr(thread, "title", None) or "").strip()
        or "Pending Petition"
    )

    return {
        "id": pending_result.get("id") or (thread.id if thread else session_obj.id),
        "session_id": session_obj.id,
        "title": title,
        "ssn_last4": (pending_result.get("ssn_last4") or "").strip() or None,
        "case_number": (
            (pending_result.get("case_number") or "").strip()
            or (getattr(thread, "case_number", None) or "").strip()
            or None
        ),
        "received_at": pending_result.get("received_at")
        or normalized_petition.get("uploaded_at")
        or (getattr(thread, "updated_at", None) or getattr(thread, "created_at", None)),
        "source": pending_result.get("source_label") or "Pending petition",
        "source_type": pending_result.get("source") or "pending_acceptance",
        "status": pending_state.get("status") or pending_result.get("status") or "pending_acceptance",
        "matched_external_filename": pending_result.get("matched_external_filename"),
        "matched_external_case_number": pending_result.get("matched_external_case_number"),
        "matched_external_court_region": pending_result.get("matched_external_court_region"),
        "petition_file_path": pending_result.get("petition_file_path")
        or normalized_petition.get("path"),
        "petition_document": normalized_petition or None,
        "petition_status": normalized_petition.get("petition_status")
        or pending_result.get("petition_status"),
        "inbox_checked_at": normalized_petition.get("inbox_checked_at")
        or pending_result.get("inbox_checked_at"),
        "is_viewed": bool(pending_state.get("is_viewed", False)),
    }


async def _load_user_session_path_owners(user_id: str, firm_id: str | None = None) -> dict[str, set[str]]:
    """Map PDF paths to the user's sessions so we do not duplicate pending records."""
    session_path_owners: dict[str, set[str]] = {}
    async with AsyncSessionLocal() as session:
        where = "s.user_id = :user_id"
        params: dict = {"user_id": user_id}
        if firm_id:
            where += " AND s.firm_id = :firm_id"
            params["firm_id"] = firm_id
        result = await session.execute(
            text(
                f"""
                SELECT pd.file_path, pd.session_id
                FROM pdf_documents pd
                JOIN sessions s ON s.id = pd.session_id
                WHERE {where}
                """
            ),
            params,
        )
        for row in result.fetchall():
            file_path = (row._mapping.get("file_path") or "").strip()
            session_id = (row._mapping.get("session_id") or "").strip()
            if not file_path or not session_id:
                continue
            resolved_path = _resolve_upload_path(file_path)
            resolved = str(resolved_path) if resolved_path else str(Path(file_path).resolve())
            session_path_owners.setdefault(resolved, set()).add(session_id)
    return session_path_owners


async def _set_thread_active(thread_id: str, is_active: bool) -> None:
    """Toggle a thread active flag."""
    async with AsyncSessionLocal() as session:
        await session.execute(
            text(
                """
                UPDATE chat_threads
                SET is_active = :is_active, updated_at = now()
                WHERE id = :thread_id
                """
            ),
            {"thread_id": thread_id, "is_active": is_active},
        )
        await session.commit()


async def _claim_pending_session_slot(
    user_id: str,
    normalized_file_path: str,
    tentative_session_id: str,
) -> tuple[bool, str]:
    """Atomically claim a slot in pending_session_file_locks using the DB PRIMARY KEY.

    Returns (True, tentative_session_id) when we inserted successfully — caller
    must go on to create the session.
    Returns (False, existing_session_id) when another request already owns this
    slot — caller must return the existing session without creating anything.
    """
    async with AsyncSessionLocal() as db:
        try:
            await db.execute(
                text(
                    """
                    INSERT INTO pending_session_file_locks (user_id, file_path, session_id)
                    VALUES (:user_id, :file_path, :session_id)
                    """
                ),
                {
                    "user_id": user_id,
                    "file_path": normalized_file_path,
                    "session_id": tentative_session_id,
                },
            )
            await db.commit()
            return True, tentative_session_id
        except IntegrityError:
            await db.rollback()
            result = await db.execute(
                text(
                    """
                    SELECT session_id
                    FROM pending_session_file_locks
                    WHERE user_id = :user_id AND file_path = :file_path
                    """
                ),
                {"user_id": user_id, "file_path": normalized_file_path},
            )
            row = result.fetchone()
            return False, str(row._mapping["session_id"]) if row else tentative_session_id


async def _create_external_upload_pending_session(
    *,
    current_user_id: str,
    firm_id: Optional[str] = None,
    upload_record: dict[str, Any],
    inbox_checked_at: datetime | None,
    petition_status: str,
    ingestion_status: str,
) -> str:
    """Persist one external upload as a session-backed pending petition record.

    Uses a DB-level PRIMARY KEY on pending_session_file_locks to guarantee that
    concurrent requests for the same (user_id, file_path) can never produce more
    than one session, even across multiple workers or app instances.
    """
    record_path = (upload_record.get("path") or "").strip()
    normalized_path = _normalize_pending_file_path(record_path) or record_path

    if normalized_path:
        tentative_session_id = str(uuid.uuid4())
        is_new, session_id = await _claim_pending_session_slot(
            current_user_id, normalized_path, tentative_session_id
        )
        if not is_new:
            return session_id

        return await _do_create_pending_session(
            current_user_id=current_user_id,
            firm_id=firm_id,
            upload_record=upload_record,
            record_path=record_path,
            session_id=session_id,
            inbox_checked_at=inbox_checked_at,
            petition_status=petition_status,
            ingestion_status=ingestion_status,
        )

    return await _do_create_pending_session(
        current_user_id=current_user_id,
        firm_id=firm_id,
        upload_record=upload_record,
        record_path=record_path,
        session_id=None,
        inbox_checked_at=inbox_checked_at,
        petition_status=petition_status,
        ingestion_status=ingestion_status,
    )


async def _do_create_pending_session(
    *,
    current_user_id: str,
    firm_id: Optional[str] = None,
    upload_record: dict[str, Any],
    record_path: str,
    session_id: Optional[str],
    inbox_checked_at: datetime | None,
    petition_status: str,
    ingestion_status: str,
) -> str:
    """Create the session, thread, PDF document and ingestion record."""
    pending_session = (
        await create_session_with_id(session_id, user_id=current_user_id, firm_id=firm_id)
        if session_id
        else await create_session(user_id=current_user_id, firm_id=firm_id)
    )
    pending_thread = await create_or_update_chat_thread(pending_session.id)
    await _set_thread_active(pending_thread.id, False)

    title = (upload_record.get("client_name") or "").strip()
    case_number = (upload_record.get("case_number") or "").strip() or None
    await db_update_thread_metadata(
        pending_thread.id,
        title=title if title else None,
        summary="Pending external petition awaiting Inbox review.",
        case_number=case_number,
    )

    filename = (upload_record.get("filename") or "").strip() or (
        Path(record_path).name if record_path else "petition.pdf"
    )
    file_size = int(upload_record.get("file_size") or 0)

    pdf_doc = await create_or_update_session_pdf_metadata(
        session_id=pending_session.id,
        filename=filename,
        original_filename=filename,
        file_path=record_path,
        file_size=file_size,
        collection_name=f"case_documents_{pending_session.id}",
        inbox_checked_at=inbox_checked_at,
        petition_status=petition_status,
        source="manual",
    )
    petition_document = _serialize_pdf_document(pdf_doc)
    petition_document["fingerprint"] = (
        upload_record.get("file_fingerprint") or _compute_file_fingerprint(record_path)
    )
    pending_result = _build_external_pending_result(
        pending_session.id,
        pending_thread.id,
        upload_record,
        petition_document,
        status=ingestion_status,
    )

    await create_or_update_ingestion(
        session_id=pending_session.id,
        ingestion_type="pending_acceptance",
        status=ingestion_status,
        case_number=case_number,
        collection_name=f"case_candidates_{pending_session.id}",
        result=pending_result,
        is_viewed=False,
    )
    return pending_session.id


def _pending_inbox_dedupe_key(
    pending_state: dict[str, Any],
    latest_pdf,
) -> Optional[str]:
    """Return a stable dedupe key for pending external-upload inbox items."""
    pending_result = pending_state.get("result")
    if not isinstance(pending_result, dict):
        pending_result = {}

    fingerprint = (pending_result.get("petition_file_fingerprint") or "").strip()
    if fingerprint:
        return f"fingerprint:{fingerprint}"

    normalized_path = _normalize_pending_file_path(getattr(latest_pdf, "file_path", None))
    if normalized_path:
        return f"path:{normalized_path}"

    return None


async def _archive_duplicate_pending_session(
    session_id: str,
    *,
    duplicate_key: str,
) -> None:
    """Archive a duplicate pending external-upload session so it leaves Inbox."""
    archived_at = _utc_now()
    await create_or_update_ingestion(
        session_id=session_id,
        ingestion_type="pending_acceptance",
        status="auto_archived",
        collection_name=f"case_state_{session_id}",
        result={
            "status": "auto_archived",
            "auto_archived_at": archived_at.isoformat(),
            "petition_status": "auto_archived",
            "inbox_checked_at": archived_at.isoformat(),
            "reason": "duplicate_pending_petition",
            "duplicate_key": duplicate_key,
        },
    )
    await update_session_petition_inbox_state(
        session_id,
        petition_status="auto_archived",
        inbox_checked_at=archived_at,
    )
    await deactivate_session(session_id)
    await _release_pending_session_slot(session_id)


async def _release_pending_session_slot(session_id: str) -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(
            text("DELETE FROM pending_session_file_locks WHERE session_id = :session_id"),
            {"session_id": session_id},
        )
        await db.commit()


async def _list_accepted_session_ids() -> set[str]:
    """
    Sessions are considered accepted when either:
    - a court-mail trigger is active, or
    - pending_acceptance status has been marked accepted.
    """
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text(
                """
                SELECT DISTINCT session_id
                FROM courtdrive_ingestions
                WHERE
                    (ingestion_type = 'court_mail_trigger' AND status = 'active')
                    OR
                    (ingestion_type = 'pending_acceptance' AND status = 'accepted')
                """
            )
        )
        return {row._mapping["session_id"] for row in result.fetchall() if row._mapping.get("session_id")}


async def _resolve_session_identity_from_db(session_id: str, thread) -> dict[str, Optional[str]]:
    """Resolve debtor name, SSN last4, and case number for a session using DB-backed metadata."""
    title = (getattr(thread, "title", None) or "").strip()
    thread_client_name = "" if title == "Untitled conversation" else strip_case_number_suffix(title)
    thread_case_number = ((getattr(thread, "case_number", None) or "").strip() or None)
    client_name = ""
    case_number = None
    ssn_last4: Optional[str] = None

    ingestions = await get_all_ingestions_for_session(session_id)
    ingestions_sorted = sorted(
        ingestions,
        key=lambda item: (item.get("completed_at") or item.get("started_at") or ""),
        reverse=True,
    )

    for ingestion in ingestions_sorted:
        ingestion_case = (ingestion.get("case_number") or "").strip()
        result_payload = ingestion.get("result")
        if not isinstance(result_payload, dict):
            result_payload = {}

        payload_client = (
            result_payload.get("resolved_client_name")
            or result_payload.get("client_name")
            or result_payload.get("debtor_name")
            or result_payload.get("title")
            or ""
        ).strip()
        payload_case = (
            result_payload.get("resolved_case_number")
            or result_payload.get("case_number")
            or ""
        ).strip()
        payload_ssn = (result_payload.get("ssn_last4") or "").strip()

        if payload_client:
            client_name = strip_case_number_suffix(payload_client)
        if payload_case:
            case_number = payload_case
        if not case_number and ingestion_case:
            case_number = ingestion_case
        if payload_ssn:
            ssn_last4 = payload_ssn

        if client_name and case_number and ssn_last4:
            break

    # Fallbacks from chat thread metadata when ingestion payload does not provide values yet.
    if not client_name and thread_client_name:
        client_name = thread_client_name
    if not case_number and thread_case_number:
        case_number = thread_case_number

    # If DB does not have SSN yet, extract once from the session's stored PDF and persist as DB metadata.
    if not ssn_last4:
        ssn_result = extract_ssn_from_uploaded_petition_pdfs(session_id)
        if ssn_result.get("status") == "completed":
            extracted_ssn = (ssn_result.get("ssn_last4") or "").strip()
            if extracted_ssn:
                ssn_last4 = extracted_ssn
                await create_or_update_ingestion(
                    session_id=session_id,
                    ingestion_type="session_identity",
                    status="completed",
                    case_number=case_number,
                    collection_name=f"session_identity_{session_id}",
                    result={
                        "client_name": client_name or None,
                        "case_number": case_number or None,
                        "ssn_last4": ssn_last4,
                    },
                )

    clean_client_name = strip_case_number_suffix((client_name or "").strip()) or None
    clean_case_number = (case_number or "").strip() or None
    clean_ssn_last4 = (ssn_last4 or "").strip() or None

    return {
        "client_name": clean_client_name,
        "normalized_client_name": normalize_client_name(clean_client_name or ""),
        "case_number": clean_case_number,
        "normalized_case_number": normalize_case_value(clean_case_number or ""),
        "ssn_last4": clean_ssn_last4,
    }


@router.get("/threads")
async def list_all_threads(limit: int = 200, offset: int = 0, current_user: User = Depends(get_current_firm_user)):
    """List all threads for the current firm."""
    try:
        threads = await db_list_all_threads(limit=limit, offset=offset, firm_id=current_user.firm_id)
        normalized_threads = []

        for t in threads:
            resolved_identity = await _resolve_session_identity_from_db(t.session_id, t)
            resolved_client_name = (resolved_identity.get("client_name") or "").strip()
            resolved_case_number = (resolved_identity.get("case_number") or "").strip()

            fallback_title = (t.title or "").strip()
            if fallback_title and fallback_title != "Untitled conversation":
                fallback_title = strip_case_number_suffix(fallback_title)

            normalized_threads.append(
                {
                    "id": t.id,
                    "session_id": t.session_id,
                    "openai_thread_id": t.openai_thread_id,
                    "title": resolved_client_name or fallback_title or t.title,
                    "summary": t.summary,
                    "case_number": resolved_case_number or t.case_number,
                    "district": getattr(t, "district", None),
                    "created_at": t.created_at,
                    "updated_at": t.updated_at,
                    "is_active": t.is_active
                }
            )

        return normalized_threads
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list all threads: {str(e)}")


async def refresh_pending_petitions_for_user(
    user_id: str,
    *,
    initialize_inbox: bool = False,
    firm_id: str | None = None,
) -> list[dict[str, Any]]:
    """Return pending petitions backed by petition-level Inbox state."""
    try:
        sessions = await db_list_sessions(user_id=user_id, firm_id=firm_id)
        pending_states = await list_pending_acceptance_states([session.id for session in sessions])
        session_path_owners = await _load_user_session_path_owners(user_id, firm_id=firm_id)
        active_session_ids = {session.id for session in sessions}
        known_fingerprints = {
            (state.get("result") or {}).get("petition_file_fingerprint")
            for state in pending_states.values()
            if isinstance(state.get("result"), dict)
            and (state.get("result") or {}).get("petition_file_fingerprint")
        }

        all_upload_records = (
            scan_uploaded_petition_identities(include_pdf_text_fallback=False) or {}
        ).get("records", [])
        external_upload_records: list[dict[str, Any]] = []

        for record in all_upload_records:
            filename = (record.get("filename") or "").strip()
            if not _is_pending_inbox_external_upload(filename):
                continue

            normalized_record = {
                "filename": filename or None,
                "path": (record.get("path") or "").strip() or None,
                "client_name": (record.get("client_name") or "").strip() or None,
                "normalized_client_name": normalize_client_name(
                    (record.get("client_name") or "").strip()
                ),
                "case_number": (record.get("case_number") or "").strip() or None,
                "normalized_case_number": normalize_case_value(
                    (record.get("case_number") or "").strip()
                ),
                "ssn_last4": (record.get("ssn_last4") or "").strip() or None,
                "court_region": (record.get("court_region") or "").strip() or None,
                "normalized_court_region": (
                    record.get("normalized_court_region") or ""
                ).strip()
                or None,
                "file_size": int(record.get("file_size") or 0),
                "file_fingerprint": _compute_file_fingerprint((record.get("path") or "").strip()),
            }

            matched_session_ids: set[str] = set()
            record_path = (record.get("path") or "").strip()
            if record_path:
                resolved_record = _resolve_upload_path(record_path)
                resolved_record_path = str(
                    resolved_record if resolved_record else Path(record_path).resolve()
                )
                matched_session_ids = session_path_owners.get(
                    resolved_record_path, set()
                )

            if not matched_session_ids and normalized_record.get("file_fingerprint") in known_fingerprints:
                continue

            if not matched_session_ids:
                legacy_session_id = next(
                    (
                        session_id
                        for session_id in active_session_ids
                        if session_id in filename
                    ),
                    None,
                )
                if legacy_session_id:
                    matched_session_ids = {legacy_session_id}

            if matched_session_ids:
                continue

            external_upload_records.append(normalized_record)
            if normalized_record.get("file_fingerprint"):
                known_fingerprints.add(normalized_record["file_fingerprint"])

        initialized_at = await get_user_inbox_initialized_at(user_id)
        if initialized_at is None:
            if not initialize_inbox:
                return []

            current_time = _utc_now()

            for session in sessions:
                pending_state = pending_states.get(session.id) or {}
                if pending_state.get("status") != "pending_acceptance":
                    continue
                latest_pdf = await get_latest_session_pdf(session.id)
                if not latest_pdf or not _is_uploads_root_pdf(latest_pdf.file_path):
                    continue

                await update_session_petition_inbox_state(
                    session.id,
                    inbox_checked_at=current_time,
                    petition_status="initialized_old",
                )

                pending_result = pending_state.get("result")
                if not isinstance(pending_result, dict):
                    pending_result = {}
                await create_or_update_ingestion(
                    session_id=session.id,
                    ingestion_type="pending_acceptance",
                    status="initialized_old",
                    case_number=pending_state.get("case_number"),
                    collection_name=f"case_candidates_{session.id}",
                    result={
                        **pending_result,
                        "status": "initialized_old",
                        "petition_status": "initialized_old",
                        "inbox_checked_at": current_time.isoformat(),
                    },
                    is_viewed=bool(pending_state.get("is_viewed", False)),
                )

            for upload_record in external_upload_records:
                await _create_external_upload_pending_session(
                    current_user_id=user_id,
                    firm_id=firm_id,
                    upload_record=upload_record,
                    inbox_checked_at=current_time,
                    petition_status="initialized_old",
                    ingestion_status="initialized_old",
                )

            await set_user_inbox_initialized_at(user_id, current_time)

        else:
            for upload_record in external_upload_records:
                await _create_external_upload_pending_session(
                    current_user_id=user_id,
                    firm_id=firm_id,
                    upload_record=upload_record,
                    inbox_checked_at=None,
                    petition_status="pending_acceptance",
                    ingestion_status="pending_acceptance",
                )

        sessions = await db_list_sessions(user_id=user_id, firm_id=firm_id)
        pending_states = await list_pending_acceptance_states([session.id for session in sessions])
        pending_petitions: list[dict[str, Any]] = []
        dedupe_candidates: dict[str, list[tuple[str, str]]] = {}

        for session in sessions:
            if not bool(getattr(session, "is_active", True)):
                continue

            pending_state = pending_states.get(session.id) or {}
            if pending_state.get("status") != "pending_acceptance":
                continue

            latest_pdf = await get_latest_session_pdf(session.id)
            if not latest_pdf or latest_pdf.inbox_checked_at is not None:
                continue

            # Guard: skip entries whose petition file has been swept by the archiver.
            # The reconciliation job will clean up the DB state asynchronously.
            petition_path = _resolve_managed_path(latest_pdf.file_path)
            if not petition_path or not petition_path.exists() or not petition_path.is_file():
                continue

            if not _is_pending_inbox_external_upload(Path(latest_pdf.file_path or "").name):
                continue

            dedupe_key = _pending_inbox_dedupe_key(pending_state, latest_pdf)
            if dedupe_key:
                pending_result = pending_state.get("result")
                if not isinstance(pending_result, dict):
                    pending_result = {}
                received_at = str(
                    pending_result.get("received_at")
                    or getattr(latest_pdf, "uploaded_at", None)
                    or ""
                )
                dedupe_candidates.setdefault(dedupe_key, []).append(
                    (session.id, received_at)
                )

        duplicate_session_ids: set[str] = set()
        for dedupe_key, grouped_sessions in dedupe_candidates.items():
            if len(grouped_sessions) < 2:
                continue

            grouped_sessions.sort(key=lambda item: item[1], reverse=True)
            for duplicate_session_id, _ in grouped_sessions[1:]:
                await _archive_duplicate_pending_session(
                    duplicate_session_id,
                    duplicate_key=dedupe_key,
                )
                duplicate_session_ids.add(duplicate_session_id)

        if duplicate_session_ids:
            sessions = await db_list_sessions(user_id=user_id, firm_id=firm_id)
            pending_states = await list_pending_acceptance_states(
                [session.id for session in sessions]
            )

        for session in sessions:
            if session.id in duplicate_session_ids:
                continue
            if not bool(getattr(session, "is_active", True)):
                continue

            pending_state = pending_states.get(session.id) or {}
            if pending_state.get("status") != "pending_acceptance":
                continue

            latest_pdf = await get_latest_session_pdf(session.id)
            if not latest_pdf or latest_pdf.inbox_checked_at is not None:
                continue

            # Guard: skip entries whose petition file has been swept by the archiver.
            # The reconciliation job will clean up the DB state asynchronously.
            petition_path = _resolve_managed_path(latest_pdf.file_path)
            if not petition_path or not petition_path.exists() or not petition_path.is_file():
                continue

            if not _is_pending_inbox_external_upload(Path(latest_pdf.file_path or "").name):
                continue

            thread = await db_get_session_chat_thread(session.id, include_inactive=True)
            if not thread:
                continue

            pending_petitions.append(
                _build_pending_petition_entry(
                    session,
                    thread,
                    pending_state,
                    _serialize_pdf_document(latest_pdf) if latest_pdf else None,
                )
            )

        pending_petitions.sort(
            key=lambda item: str(item.get("received_at") or ""),
            reverse=True,
        )
        return pending_petitions
    except Exception as e:
        raise RuntimeError(f"Failed to list pending petitions: {str(e)}") from e


@router.get("/threads/pending-petitions")
async def list_pending_petitions(current_user: User = Depends(get_current_firm_user)):
    """List unseen pending petitions whose petition records are still unchecked."""
    try:
        return await refresh_pending_petitions_for_user(
            current_user.id,
            initialize_inbox=True,
            firm_id=current_user.firm_id,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/threads/pending-petitions/{session_id}/viewed")
async def mark_pending_petition_as_viewed(session_id: str, current_user: User = Depends(get_current_firm_user)):
    """Persist that the current user has opened a pending petition candidate."""
    session = await db_get_user_session(session_id, current_user.id)
    if not session:
        raise HTTPException(status_code=404, detail="Pending petition session not found")

    updated = await mark_pending_acceptance_viewed(session_id, True)
    if not updated:
        raise HTTPException(status_code=500, detail="Failed to update pending petition viewed state")

    return {
        "session_id": session_id,
        "is_viewed": True,
    }


@router.post("/threads/pending-petitions/{session_id}/resolve")
async def resolve_pending_petition(
    session_id: str,
    request: PendingPetitionResolveRequest,
    current_user: User = Depends(get_current_firm_user),
):
    """Resolve a pending petition into an accepted, denied, or merged case."""
    pending_session = await db_get_user_session(session_id, current_user.id)
    if not pending_session:
        raise HTTPException(status_code=404, detail="Pending petition session not found")

    if request.target_session_id:
        target_session = await db_get_user_session(request.target_session_id, current_user.id)
        if not target_session:
            raise HTTPException(status_code=404, detail="Target case session not found")

    try:
        return await pending_petition_resolution_service.resolve(
            session_id,
            action=request.action,
            user_id=current_user.id,
            target_session_id=request.target_session_id,
            client_name=request.client_name,
            ssn_last4=request.ssn_last4,
            case_number=request.case_number,
            sender_emails=request.sender_emails,
            max_results=request.max_results,
        )
    except PendingPetitionResolutionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to resolve pending petition: {exc}") from exc

@router.get("/threads/{thread_id}/messages")
async def list_thread_messages(
    thread_id: str,
    limit: int = 200,
    offset: int = 0,
    order: Literal["asc", "desc"] = "asc",
):
    """Get all messages for a specific thread."""
    try:
        messages = await db_list_messages(thread_id, limit=limit, offset=offset, order=order)
        return [
            {
                "id": m.id,
                "thread_id": m.thread_id,
                "role": m.role,
                "content": m.content,
                "created_at": m.created_at
            } for m in messages
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list messages: {str(e)}")


@router.post("/threads/{thread_id}/metadata")
async def update_thread_metadata(thread_id: str, title: Optional[str] = None, summary: Optional[str] = None):
    """Update thread metadata (title, summary)."""
    try:
        updated = await db_update_thread_metadata(thread_id, title=title, summary=summary)
        if not updated:
            raise HTTPException(status_code=404, detail="Thread not found or no updates provided")
        return {
            "id": updated.id,
            "session_id": updated.session_id,
            "openai_thread_id": updated.openai_thread_id,
            "title": updated.title,
            "summary": updated.summary,
            "case_number": updated.case_number,
            "created_at": updated.created_at,
            "updated_at": updated.updated_at,
            "is_active": updated.is_active
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update thread metadata: {str(e)}")


@router.delete("/threads/{thread_id}")
async def delete_thread(thread_id: str):
    """Delete a thread."""
    try:
        async with AsyncSessionLocal() as _db:
            _row = await _db.execute(
                text("SELECT session_id, firm_id FROM chat_threads WHERE id = :tid"),
                {"tid": thread_id},
            )
            _r = _row.fetchone()
            _session_id = _r.session_id if _r else None
            _firm_id = _r.firm_id if _r else None

        ok = await db_delete_thread(thread_id)
        if not ok:
            raise HTTPException(status_code=500, detail="Failed to delete thread")

        if _session_id:
            await log_user_action(action="delete_case", session_id=_session_id, firm_id=_firm_id)

        return {"status": "deleted", "thread_id": thread_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete thread: {str(e)}")
