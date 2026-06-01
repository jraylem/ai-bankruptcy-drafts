"""Routes for case acceptance and court-mail trigger ingestion workflows."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..chatbot.database import get_session, get_session_chat_thread, log_user_action
from ..chatbot.pending_petitions import (
    PendingPetitionResolutionError,
    PendingPetitionResolutionService,
)
from ..courtdrive.service import extract_case_number_for_session, extract_debtor_name_for_session
from .workflow_services import (
    DEFAULT_TRIGGER_SENDERS,
    CaseAcceptanceService,
    EmailIngestionService,
)

router = APIRouter(tags=["Gmail - Court Mail"])

case_acceptance_service = CaseAcceptanceService()
email_ingestion_service = EmailIngestionService()
pending_petition_resolution_service = PendingPetitionResolutionService(
    acceptance_service=case_acceptance_service,
)


class CourtMailFetchRequest(BaseModel):
    session_id: str
    case_number: Optional[str] = None
    matched_external_case_number: Optional[str] = None
    client_name: Optional[str] = None
    sender_emails: list[str] = Field(default_factory=lambda: list(DEFAULT_TRIGGER_SENDERS))
    max_results: int = Field(default=25, ge=1, le=200)


class CaseActionRequest(BaseModel):
    session_id: str


class TriggerPollRequest(BaseModel):
    max_results_per_trigger: int = Field(default=25, ge=1, le=200)


class TriggerMessageIngestRequest(BaseModel):
    session_id: str
    message_id: str
    case_number: str


async def _resolve_case_identity(request: CourtMailFetchRequest) -> tuple[str, str]:
    chat_thread = await get_session_chat_thread(request.session_id)

    # Prefer matched external case number from pending inbox flow.
    resolved_case_number = (request.matched_external_case_number or "").strip()
    if not resolved_case_number:
        resolved_case_number = (request.case_number or "").strip()

    resolved_client_name = (request.client_name or "").strip()

    if not resolved_case_number and chat_thread and chat_thread.case_number:
        candidate = (chat_thread.case_number or "").strip()
        if candidate and candidate != "N/A":
            resolved_case_number = candidate

    if not resolved_client_name and chat_thread and chat_thread.title:
        candidate = (chat_thread.title or "").strip()
        if candidate and candidate not in {"N/A", "Untitled conversation"}:
            resolved_client_name = candidate

    if not resolved_case_number:
        case_result = extract_case_number_for_session(request.session_id)
        if case_result.get("status") == "completed":
            candidate = (case_result.get("case_number") or "").strip()
            if candidate and candidate != "N/A":
                resolved_case_number = candidate

    if not resolved_client_name:
        debtor_result = extract_debtor_name_for_session(request.session_id)
        if debtor_result.get("status") == "completed":
            candidate = (debtor_result.get("debtor_name") or "").strip()
            if candidate and candidate != "N/A":
                resolved_client_name = candidate.splitlines()[0].strip()

    return resolved_case_number, resolved_client_name


@router.post("/court-mail/fetch")
async def accept_case_and_register_trigger(request: CourtMailFetchRequest):
    """
    Accept case candidate, attach petition with fallback chain, and register trigger.
    """
    session = await get_session(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or inactive")

    resolved_case_number, resolved_client_name = await _resolve_case_identity(request)

    if not resolved_case_number:
        raise HTTPException(
            status_code=400,
            detail="Could not resolve case_number from the session. Pass it explicitly before accepting.",
        )

    try:
        result = await case_acceptance_service.accept_case(
            session_id=request.session_id,
            case_number=resolved_case_number or None,
            client_name=resolved_client_name or None,
            sender_emails=request.sender_emails,
            max_results=request.max_results,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        print(f"Error accepting case/registering trigger: {exc}")
        raise HTTPException(status_code=500, detail=f"Failed to accept case: {exc}") from exc

    await log_user_action(
        action="accept_case",
        session_id=request.session_id,
        firm_id=session.firm_id if session else None,
        metadata={"case_number": resolved_case_number, "client_name": resolved_client_name},
    )

    return {
        **result,
        "resolved_case_number": resolved_case_number or None,
        "resolved_client_name": resolved_client_name or None,
    }


@router.post("/court-mail/deny")
async def deny_case_candidate(request: CaseActionRequest):
    """Deny a pending case candidate and make it unavailable without deleting uploads."""
    session = await get_session(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or inactive")

    try:
        result = await pending_petition_resolution_service.resolve(
            request.session_id,
            action="deny",
        )
    except PendingPetitionResolutionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to deny case: {exc}") from exc

    await log_user_action(
        action="deny_case",
        session_id=request.session_id,
        firm_id=session.firm_id if session else None,
    )
    return result


@router.post("/court-mail/archive")
async def archive_case_candidate(request: CaseActionRequest):
    """Archive a pending case candidate and associated files/metadata."""
    session = await get_session(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or inactive")

    try:
        result = await case_acceptance_service.archive_case(request.session_id, reason="manual")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to archive case: {exc}") from exc

    await log_user_action(
        action="archive_case",
        session_id=request.session_id,
        firm_id=session.firm_id if session else None,
        metadata={"reason": "manual"},
    )
    return result


@router.post("/court-mail/candidates/auto-archive")
async def auto_archive_stale_candidates():
    """Archive pending candidates with no user action for 48h."""
    try:
        return await case_acceptance_service.auto_archive_stale_pending_cases(max_age_hours=48)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to auto-archive stale candidates: {exc}") from exc


@router.post("/court-mail/triggers/poll")
async def poll_court_mail_triggers(request: TriggerPollRequest):
    """
    Poll active court-mail triggers and ingest matching Gmail messages.

    This endpoint is intended for scheduler/webhook workers, not UI accept actions.
    """
    try:
        return await email_ingestion_service.poll_triggered_cases(
            max_results_per_trigger=request.max_results_per_trigger
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ImportError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        print(f"Error polling court-mail triggers: {exc}")
        raise HTTPException(status_code=500, detail=f"Failed to poll court-mail triggers: {exc}") from exc


@router.post("/court-mail/triggers/ingest-message")
async def ingest_specific_court_mail_message(request: TriggerMessageIngestRequest):
    """Ingest a specific Gmail message for a case trigger (worker/debug endpoint)."""
    session = await get_session(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or inactive")

    try:
        return await email_ingestion_service.ingest_specific_message(
            session_id=request.session_id,
            message_id=request.message_id,
            case_number=request.case_number,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to ingest specific message: {exc}") from exc
