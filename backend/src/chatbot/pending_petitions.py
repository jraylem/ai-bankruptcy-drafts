"""Services for resolving pending petition actions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Optional

from sqlalchemy import text

from ..courtdrive.ingestion_db import get_ingestion_status
from ..courtdrive.service import normalize_client_name, normalize_case_value
from ..gmail.workflow_services import (
    ACTIVE_UPLOADS_ROOT,
    DEFAULT_TRIGGER_SENDERS,
    CaseAcceptanceService,
    CaseMatchingService,
    PDFParsingService,
    _move_petition_file,
)
from .database import (
    AsyncSessionLocal,
    get_latest_session_pdf,
    get_session,
    get_session_chat_thread,
    get_session_pdfs,
)

PendingPetitionAction = Literal["accept", "deny", "merge", "replace", "merge_schedule"]

_DEFAULT_MAX_RESULTS = 25
_REPLACEABLE_STATUS = {
    "merge": "merged",
    "replace": "replaced",
    "merge_schedule": "merged_schedule",
}


def _utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


def _normalize_ssn_last4(value: Optional[str]) -> str:
    """Return a comparable SSN last-4 string."""
    digits = re.sub(r"\D", "", value or "")
    return digits[-4:] if digits else ""


def _normalize_text(value: Optional[str]) -> Optional[str]:
    """Trim text values and convert blanks to None."""
    cleaned = (value or "").strip()
    return cleaned or None


def _resolve_managed_path(path: Optional[str]) -> Optional[Path]:
    """Resolve a stored PDF path into an absolute path when possible."""
    candidate = (path or "").strip()
    if not candidate:
        return None

    parsed = Path(candidate)
    if parsed.is_absolute():
        return parsed.resolve()

    backend_root = Path(__file__).resolve().parent.parent.parent
    if candidate.startswith("/uploads/"):
        return (backend_root / candidate.lstrip("/")).resolve()
    if parsed.parts and parsed.parts[0] == "uploads":
        return (backend_root / parsed).resolve()
    return (backend_root / "uploads" / parsed).resolve()


def _serialize_pdf_document(pdf) -> dict[str, Any]:
    """Serialize a PDF row for action responses."""
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


class PendingPetitionResolutionError(Exception):
    """Structured exception for pending petition resolution failures."""

    def __init__(self, detail: str | dict[str, Any], status_code: int = 400):
        super().__init__(str(detail))
        self.detail = detail
        self.status_code = status_code


@dataclass
class PendingPetitionContext:
    """Resolved metadata for a pending petition session."""

    session_id: str
    thread_id: Optional[str]
    client_name: Optional[str]
    ssn_last4: Optional[str]
    case_number: Optional[str]
    petition_path: Optional[str]
    petition_filename: Optional[str]
    petition_original_filename: Optional[str]
    pdf_bytes: bytes
    is_schedule_only: bool
    pending_result: dict[str, Any]


class PendingPetitionResolutionService:
    """Resolve pending petitions into accepted, denied, or merged cases."""

    def __init__(
        self,
        acceptance_service: Optional[CaseAcceptanceService] = None,
        matcher: Optional[CaseMatchingService] = None,
        parser: Optional[PDFParsingService] = None,
    ):
        self.acceptance_service = acceptance_service or CaseAcceptanceService()
        self.matcher = matcher or CaseMatchingService()
        self.parser = parser or PDFParsingService()

    async def resolve(
        self,
        pending_session_id: str,
        *,
        action: PendingPetitionAction,
        user_id: Optional[str] = None,
        target_session_id: Optional[str] = None,
        client_name: Optional[str] = None,
        ssn_last4: Optional[str] = None,
        case_number: Optional[str] = None,
        sender_emails: Optional[list[str]] = None,
        max_results: int = _DEFAULT_MAX_RESULTS,
    ) -> dict[str, Any]:
        """Resolve a pending petition using the requested action."""
        normalized_action = (action or "").strip().lower()
        if normalized_action not in {
            "accept",
            "deny",
            "merge",
            "replace",
            "merge_schedule",
        }:
            raise PendingPetitionResolutionError(
                f"Unsupported pending petition action: {action}",
                status_code=422,
            )

        if normalized_action == "deny":
            session = await get_session(pending_session_id)
            if not session:
                raise PendingPetitionResolutionError(
                    "Pending petition session not found.",
                    status_code=404,
                )
            return await self._deny_pending_petition(pending_session_id)

        context = await self._load_pending_context(
            pending_session_id,
            client_name=client_name,
            ssn_last4=ssn_last4,
            case_number=case_number,
        )

        if normalized_action == "accept":
            return await self._accept_pending_petition(
                context,
                sender_emails=sender_emails or list(DEFAULT_TRIGGER_SENDERS),
                max_results=max_results,
            )

        self._validate_merge_like_context(context, normalized_action)
        selected_case, candidates = await self._resolve_target_case(
            context,
            user_id=user_id,
            target_session_id=target_session_id,
        )
        return await self._merge_into_existing_case(
            context,
            action=normalized_action,
            selected_case=selected_case,
            candidates=candidates,
        )

    async def auto_merge_pending_on_case_match(
        self,
        active_session_id: str,
        *,
        user_id: str,
        case_number: Optional[str] = None,
        debtor_name: Optional[str] = None,
        ssn_last4: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """
        Find pending sessions that match the active case on at least 2-of-3
        (case_number, debtor_name, ssn_last4) and fully merge them in.

        Called automatically after upload extraction or case acceptance so
        that manually worked cases absorb any matching inbox duplicates.
        """
        import json as _json

        norm_case = normalize_case_value(case_number or "")
        norm_name = normalize_client_name(debtor_name or "")
        norm_ssn = _normalize_ssn_last4(ssn_last4)

        known_fields = sum([bool(norm_case), bool(norm_name), bool(norm_ssn)])
        if known_fields < 2:
            return []

        async with AsyncSessionLocal() as db:
            rows_result = await db.execute(
                text("""
                    SELECT
                        s.id AS session_id,
                        ct.title AS thread_title,
                        ct.case_number AS thread_case_number,
                        ci.case_number AS ingestion_case_number,
                        ci.result AS ingestion_result
                    FROM sessions s
                    INNER JOIN pdf_documents pd
                        ON pd.session_id = s.id
                        AND pd.petition_status = 'pending_acceptance'
                        AND pd.is_active = true
                    LEFT JOIN chat_threads ct
                        ON ct.session_id = s.id AND ct.is_active = true
                    LEFT JOIN courtdrive_ingestions ci
                        ON ci.session_id = s.id
                        AND ci.ingestion_type = 'pending_acceptance'
                    WHERE s.user_id = :user_id
                      AND s.is_active = true
                      AND s.id != :active_session_id
                    GROUP BY s.id, ct.title, ct.case_number,
                             ci.case_number, ci.result
                """),
                {"user_id": user_id, "active_session_id": active_session_id},
            )
            pending_rows = rows_result.fetchall()

        results: list[dict[str, Any]] = []
        for row in pending_rows:
            pending_session_id = row.session_id

            raw_result = row.ingestion_result
            if isinstance(raw_result, str):
                try:
                    raw_result = _json.loads(raw_result)
                except Exception:
                    raw_result = {}
            ingestion_result: dict = raw_result if isinstance(raw_result, dict) else {}

            p_case = normalize_case_value(
                row.ingestion_case_number
                or ingestion_result.get("case_number")
                or row.thread_case_number
                or ""
            )
            p_name = normalize_client_name(
                ingestion_result.get("client_name")
                or ingestion_result.get("title")
                or row.thread_title
                or ""
            )
            p_ssn = _normalize_ssn_last4(ingestion_result.get("ssn_last4"))

            score = 0
            if norm_case and p_case and norm_case == p_case:
                score += 1
            if norm_name and p_name and norm_name == p_name:
                score += 1
            if norm_ssn and p_ssn and norm_ssn == p_ssn:
                score += 1

            if score < 2:
                continue

            try:
                context = await self._load_pending_context(pending_session_id)
            except PendingPetitionResolutionError:
                continue
            except Exception as exc:
                logger.warning(
                    "auto_merge: skipping pending %s — context load failed: %s",
                    pending_session_id, exc,
                )
                continue

            selected_case: dict[str, Any] = {
                "session_id": active_session_id,
                "confidence": "auto_match",
                "score": score * 33,
                "name_match": bool(norm_name and p_name and norm_name == p_name),
                "ssn_match": bool(norm_ssn and p_ssn and norm_ssn == p_ssn),
                "case_match": bool(norm_case and p_case and norm_case == p_case),
            }
            try:
                merge_result = await self._merge_into_existing_case(
                    context,
                    action="merge",
                    selected_case=selected_case,
                    candidates=[selected_case],
                )
                results.append(merge_result)
                logger.info(
                    "auto_merge: merged pending %s into active %s (score=%d)",
                    pending_session_id, active_session_id, score,
                )
            except Exception as exc:
                logger.warning(
                    "auto_merge: failed to merge pending %s into %s: %s",
                    pending_session_id, active_session_id, exc,
                )

        return results

    async def _accept_pending_petition(
        self,
        context: PendingPetitionContext,
        *,
        sender_emails: list[str],
        max_results: int,
    ) -> dict[str, Any]:
        if not context.client_name:
            raise PendingPetitionResolutionError(
                "Client name is required before accepting a pending petition.",
                status_code=400,
            )
        if not context.ssn_last4:
            raise PendingPetitionResolutionError(
                "SSN last4 is required before accepting a pending petition.",
                status_code=400,
            )
        if not context.case_number:
            raise PendingPetitionResolutionError(
                "Case number is required before accepting a pending petition.",
                status_code=400,
            )

        result = await self.acceptance_service.accept_case(
            session_id=context.session_id,
            case_number=context.case_number,
            client_name=context.client_name,
            sender_emails=sender_emails,
            max_results=max_results,
        )
        case_data = await self.serialize_case(context.session_id)
        return {
            **result,
            "action": "accept",
            "case": case_data,
        }

    async def _deny_pending_petition(self, pending_session_id: str) -> dict[str, Any]:
        session_pdfs = await get_session_pdfs(pending_session_id)
        retained_files = [
            (pdf.file_path or "").strip()
            for pdf in session_pdfs
            if (pdf.file_path or "").strip()
        ]

        deny_result = await self.acceptance_service.deny_case(pending_session_id)

        return {
            **deny_result,
            "action": "deny",
            "deleted_files": [],
            "retained_files": retained_files,
            "message": "Pending petition marked unavailable for this user. Files in /uploads were preserved.",
        }

    async def _merge_into_existing_case(
        self,
        context: PendingPetitionContext,
        *,
        action: Literal["merge", "replace", "merge_schedule"],
        selected_case: dict[str, Any],
        candidates: list[dict[str, Any]],
    ) -> dict[str, Any]:
        resolved_at = _utc_now()
        target_session_id = selected_case["session_id"]

        async with AsyncSessionLocal() as db:
            target_thread_result = await db.execute(
                text(
                    """
                    SELECT id, title, case_number
                    FROM chat_threads
                    WHERE session_id = :session_id AND is_active = true
                    ORDER BY updated_at DESC NULLS LAST, created_at DESC
                    LIMIT 1
                    """
                ),
                {"session_id": target_session_id},
            )
            target_thread = target_thread_result.fetchone()
            if not target_thread:
                raise PendingPetitionResolutionError(
                    "Target case thread was not found.",
                    status_code=404,
                )

            pending_pdf_rows = await db.execute(
                text(
                    """
                    SELECT id, filename, original_filename, file_path, file_size, uploaded_at
                    FROM pdf_documents
                    WHERE session_id = :session_id
                    ORDER BY uploaded_at DESC NULLS LAST, id DESC
                    """
                ),
                {"session_id": context.session_id},
            )
            pending_documents = pending_pdf_rows.fetchall()
            if not pending_documents:
                raise PendingPetitionResolutionError(
                    "No petition document was found for the pending session.",
                    status_code=404,
                )

            replaced_paths: list[str] = []
            if action == "replace":
                target_pdf_rows = await db.execute(
                    text(
                        """
                        SELECT id, filename, original_filename, file_path, uploaded_at
                        FROM pdf_documents
                        WHERE session_id = :session_id AND is_active = true
                        ORDER BY uploaded_at DESC NULLS LAST, id DESC
                        """
                    ),
                    {"session_id": target_session_id},
                )
                target_documents = target_pdf_rows.fetchall()
                documents_to_replace = self._select_documents_to_replace(target_documents)
                replaced_paths = [
                    (row._mapping.get("file_path") or "").strip()
                    for row in documents_to_replace
                    if (row._mapping.get("file_path") or "").strip()
                ]
                if documents_to_replace:
                    for row in documents_to_replace:
                        document_id = row._mapping.get("id")
                        if not document_id:
                            continue
                        await db.execute(
                            text("DELETE FROM pdf_documents WHERE id = :document_id"),
                            {"document_id": document_id},
                        )

            try:
                await db.execute(
                    text(
                        """
                        UPDATE pdf_documents
                        SET
                            session_id = :target_session_id,
                            collection_name = :collection_name,
                            inbox_checked_at = :inbox_checked_at,
                            petition_status = :petition_status,
                            is_active = true
                        WHERE session_id = :pending_session_id
                        """
                    ),
                    {
                        "target_session_id": target_session_id,
                        "collection_name": f"case_documents_{target_session_id}",
                        "inbox_checked_at": resolved_at,
                        "petition_status": _REPLACEABLE_STATUS[action],
                        "pending_session_id": context.session_id,
                    },
                )

                title = _normalize_text(target_thread._mapping.get("title"))
                target_case_number = _normalize_text(target_thread._mapping.get("case_number"))
                update_values: list[str] = []
                params: dict[str, Any] = {"thread_id": target_thread._mapping.get("id")}

                if not title and context.client_name:
                    update_values.append("title = :title")
                    params["title"] = context.client_name
                if not target_case_number and context.case_number:
                    update_values.append("case_number = :case_number")
                    params["case_number"] = context.case_number
                if update_values:
                    await db.execute(
                        text(
                            f"""
                            UPDATE chat_threads
                            SET {", ".join(update_values)}, updated_at = now()
                            WHERE id = :thread_id
                            """
                        ),
                        params,
                    )

                await db.execute(
                    text(
                        """
                        DELETE FROM chat_messages
                        WHERE thread_id IN (
                            SELECT id FROM chat_threads WHERE session_id = :session_id
                        )
                        """
                    ),
                    {"session_id": context.session_id},
                )
                await db.execute(
                    text("DELETE FROM review_results WHERE session_id = :session_id"),
                    {"session_id": context.session_id},
                )
                await db.execute(
                    text("DELETE FROM courtdrive_ingestions WHERE session_id = :session_id"),
                    {"session_id": context.session_id},
                )
                await db.execute(
                    text("DELETE FROM chat_threads WHERE session_id = :session_id"),
                    {"session_id": context.session_id},
                )
                await db.execute(
                    text("DELETE FROM sessions WHERE id = :session_id"),
                    {"session_id": context.session_id},
                )
                await db.commit()
            except Exception:
                await db.rollback()
                raise

        # Move the merged petition files into the active directory so the archiver
        # (which only scans the flat uploads/ dir) does not sweep them.
        for doc in pending_documents:
            old_path_str = (doc._mapping.get("file_path") or "").strip()
            if not old_path_str:
                continue
            src = _resolve_managed_path(old_path_str)
            if not src or not src.exists() or not src.is_file():
                continue
            if src.parent.resolve() == ACTIVE_UPLOADS_ROOT.resolve():
                continue
            new_path = _move_petition_file(src, ACTIVE_UPLOADS_ROOT)
            doc_id = doc._mapping.get("id")
            if doc_id:
                async with AsyncSessionLocal() as update_db:
                    await update_db.execute(
                        text("UPDATE pdf_documents SET file_path = :path WHERE id = :id"),
                        {"path": new_path, "id": doc_id},
                    )
                    await update_db.commit()

        removed_files = self._delete_replaced_files(
            replaced_paths,
            keep_paths={context.petition_path or ""},
        )

        case_data = await self.serialize_case(target_session_id)

        return {
            "status": _REPLACEABLE_STATUS[action],
            "action": action,
            "session_id": context.session_id,
            "target_session_id": target_session_id,
            "resolved_at": resolved_at.isoformat(),
            "matched_case": self._serialize_candidate(selected_case),
            "case_candidates": [self._serialize_candidate(candidate) for candidate in candidates[:5]],
            "removed_files": removed_files,
            "case": case_data,
        }

    async def _load_pending_context(
        self,
        pending_session_id: str,
        *,
        client_name: Optional[str] = None,
        ssn_last4: Optional[str] = None,
        case_number: Optional[str] = None,
    ) -> PendingPetitionContext:
        session = await get_session(pending_session_id)
        if not session:
            raise PendingPetitionResolutionError(
                "Pending petition session not found.",
                status_code=404,
            )

        thread = await get_session_chat_thread(pending_session_id, include_inactive=True)
        pending_state = await get_ingestion_status(pending_session_id, "pending_acceptance")
        pending_result = pending_state.get("result") if isinstance(pending_state, dict) else {}
        if not isinstance(pending_result, dict):
            pending_result = {}

        session_pdfs = sorted(
            await get_session_pdfs(pending_session_id),
            key=lambda pdf: getattr(pdf, "uploaded_at", None) or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        latest_pdf = session_pdfs[0] if session_pdfs else await get_latest_session_pdf(
            pending_session_id,
            include_inactive=True,
        )
        if not latest_pdf:
            raise PendingPetitionResolutionError(
                "Pending petition document not found.",
                status_code=404,
            )

        petition_path = _resolve_managed_path(latest_pdf.file_path)
        pdf_bytes = b""
        if petition_path and petition_path.exists() and petition_path.is_file():
            pdf_bytes = petition_path.read_bytes()

        fallback_filename = (
            _normalize_text(latest_pdf.original_filename)
            or _normalize_text(latest_pdf.filename)
            or (petition_path.name if petition_path else "")
        )
        parsed = self.parser.parse_petition_fields(pdf_bytes, fallback_filename=fallback_filename or "")
        parsed_client_name = _normalize_text(parsed.client_name)
        parsed_ssn_last4 = _normalize_text(parsed.ssn_last4)
        parsed_case_number = _normalize_text(parsed.case_number)

        resolved_client_name = (
            _normalize_text(client_name)
            or _normalize_text(pending_result.get("client_name"))
            or _normalize_text(pending_result.get("title"))
            or parsed_client_name
            or (
                None
                if not thread
                else _normalize_text(thread.title if thread.title != "Untitled conversation" else None)
            )
        )
        resolved_ssn_last4 = (
            _normalize_ssn_last4(ssn_last4)
            or _normalize_ssn_last4(pending_result.get("ssn_last4"))
            or _normalize_ssn_last4(parsed_ssn_last4)
        )
        resolved_case_number = (
            _normalize_text(case_number)
            or _normalize_text(pending_result.get("case_number"))
            or _normalize_text(
                pending_state.get("case_number") if isinstance(pending_state, dict) else None
            )
            or parsed_case_number
            or (None if not thread else _normalize_text(thread.case_number))
        )

        is_schedule_only = bool(
            pdf_bytes and self.parser.is_schedule_only_document(pdf_bytes, fallback_filename=fallback_filename or "")
        )

        return PendingPetitionContext(
            session_id=pending_session_id,
            thread_id=(thread.id if thread else None),
            client_name=resolved_client_name,
            ssn_last4=resolved_ssn_last4 or None,
            case_number=resolved_case_number,
            petition_path=str(petition_path) if petition_path else _normalize_text(latest_pdf.file_path),
            petition_filename=_normalize_text(latest_pdf.filename),
            petition_original_filename=_normalize_text(latest_pdf.original_filename),
            pdf_bytes=pdf_bytes,
            is_schedule_only=is_schedule_only,
            pending_result=pending_result,
        )

    async def _resolve_target_case(
        self,
        context: PendingPetitionContext,
        *,
        user_id: Optional[str],
        target_session_id: Optional[str],
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        if target_session_id:
            if target_session_id == context.session_id:
                raise PendingPetitionResolutionError(
                    "A pending petition cannot be merged into itself.",
                    status_code=400,
                )
            explicit_candidates = await self.matcher.find_case_candidates(
                context.client_name or "",
                context.ssn_last4 or "",
                context.case_number or "",
                user_id=user_id,
                exclude_session_ids={context.session_id},
                allow_name_only=True,
            )
            selected = next(
                (candidate for candidate in explicit_candidates if candidate.get("session_id") == target_session_id),
                None,
            )
            if selected:
                return selected, explicit_candidates

            target_session = await get_session(target_session_id)
            target_thread = await get_session_chat_thread(target_session_id)
            if not target_session or not target_thread or not target_thread.is_active:
                raise PendingPetitionResolutionError(
                    "Target case session was not found or is inactive.",
                    status_code=404,
                )
            return (
                {
                    "session_id": target_session_id,
                    "thread_id": target_thread.id,
                    "title": target_thread.title,
                    "case_number": target_thread.case_number,
                    "confidence": "manual_target",
                },
                explicit_candidates,
            )

        candidates = await self.matcher.find_case_candidates(
            context.client_name or "",
            context.ssn_last4 or "",
            context.case_number or "",
            user_id=user_id,
            exclude_session_ids={context.session_id},
            allow_name_only=True,
        )
        if not candidates:
            raise PendingPetitionResolutionError(
                {
                    "message": "No matching active case was found for this pending petition.",
                    "case_candidates": [],
                },
                status_code=404,
            )

        selected = self._select_auto_target_candidate(candidates)
        if selected:
            return selected, candidates

        raise PendingPetitionResolutionError(
            {
                "message": "Multiple possible case matches were found. Pass target_session_id to continue.",
                "case_candidates": [self._serialize_candidate(candidate) for candidate in candidates[:5]],
            },
            status_code=409,
        )

    def _validate_merge_like_context(
        self,
        context: PendingPetitionContext,
        action: Literal["merge", "replace", "merge_schedule"],
    ) -> None:
        if not context.client_name:
            raise PendingPetitionResolutionError(
                "Client name is required before merging a pending petition.",
                status_code=400,
            )
        if not context.ssn_last4:
            raise PendingPetitionResolutionError(
                "SSN last4 is required before merging a pending petition.",
                status_code=400,
            )
        if not context.petition_path:
            raise PendingPetitionResolutionError(
                "Pending petition file is missing.",
                status_code=404,
            )
        if action == "merge_schedule" and not context.is_schedule_only:
            raise PendingPetitionResolutionError(
                "Merge_schedule can only be used for schedule-only documents.",
                status_code=400,
            )
        if action in {"merge", "replace"} and context.is_schedule_only:
            raise PendingPetitionResolutionError(
                "This document appears to contain schedules only. Use merge_schedule instead.",
                status_code=400,
            )

    @staticmethod
    def _select_auto_target_candidate(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
        if not candidates:
            return None

        top_candidate = candidates[0]
        second_candidate = candidates[1] if len(candidates) > 1 else None
        score_gap = int(top_candidate.get("score") or 0) - int(second_candidate.get("score") or 0)

        if top_candidate.get("is_strong_match"):
            if not second_candidate or not second_candidate.get("is_strong_match") or score_gap >= 20:
                return top_candidate
            return None

        if top_candidate.get("confidence") in {"exact_name_case", "exact_ssn", "exact_case"}:
            if not second_candidate or score_gap >= 25:
                return top_candidate
            return None

        exact_name_candidates = [
            candidate
            for candidate in candidates
            if candidate.get("confidence") == "exact_name"
        ]
        if len(exact_name_candidates) == 1 and top_candidate.get("confidence") == "exact_name":
            if not second_candidate or score_gap >= 20:
                return top_candidate

        return None

    @staticmethod
    def _select_documents_to_replace(target_documents: list[Any]) -> list[Any]:
        if not target_documents:
            return []

        petition_like_documents = [
            row
            for row in target_documents
            if "petition" in (
                " ".join(
                    filter(
                        None,
                        [
                            (row._mapping.get("filename") or "").lower(),
                            (row._mapping.get("original_filename") or "").lower(),
                            (row._mapping.get("file_path") or "").lower(),
                        ],
                    )
                )
            )
        ]
        if petition_like_documents:
            return petition_like_documents
        return [target_documents[0]]

    @staticmethod
    def _delete_replaced_files(paths: list[str], *, keep_paths: set[str]) -> list[str]:
        removed_files: list[str] = []
        normalized_keep_paths = {path for path in keep_paths if path}

        for stored_path in paths:
            if not stored_path or stored_path in normalized_keep_paths:
                continue

            resolved = _resolve_managed_path(stored_path)
            if not resolved or not resolved.exists() or not resolved.is_file():
                continue

            try:
                resolved.unlink()
                removed_files.append(str(resolved))
            except OSError:
                continue

        return removed_files

    @staticmethod
    def _serialize_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
        return {
            "session_id": candidate.get("session_id"),
            "thread_id": candidate.get("thread_id"),
            "title": candidate.get("title"),
            "case_number": candidate.get("case_number"),
            "confidence": candidate.get("confidence"),
            "score": candidate.get("score"),
            "name_match": bool(candidate.get("name_match", False)),
            "ssn_match": bool(candidate.get("ssn_match", False)),
            "case_match": bool(candidate.get("case_match", False)),
        }

    async def serialize_case(self, session_id: str) -> dict[str, Any]:
        """Serialize the updated case for frontend refreshes."""
        session = await get_session(session_id)
        thread = await get_session_chat_thread(session_id, include_inactive=True)
        pdfs = sorted(
            await get_session_pdfs(session_id),
            key=lambda pdf: getattr(pdf, "uploaded_at", None) or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )

        return {
            "session_id": session_id,
            "user_id": getattr(session, "user_id", None) if session else None,
            "thread": {
                "id": getattr(thread, "id", None),
                "title": getattr(thread, "title", None),
                "summary": getattr(thread, "summary", None),
                "case_number": getattr(thread, "case_number", None),
                "is_active": bool(getattr(thread, "is_active", False)),
            }
            if thread
            else None,
            "petition_documents": [_serialize_pdf_document(pdf) for pdf in pdfs],
            "latest_petition_document": _serialize_pdf_document(pdfs[0]) if pdfs else None,
        }
