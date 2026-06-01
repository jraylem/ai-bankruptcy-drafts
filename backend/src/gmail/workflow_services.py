"""Workflow services for petition ingestion, case matching, acceptance, and court-mail triggers."""

from __future__ import annotations

import base64
import hashlib
import os
import json
import re
import shutil
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from typing import Any, Iterable, Optional

from sqlalchemy import text, select

try:
    from pypdf import PdfReader
except Exception:  # pragma: no cover
    PdfReader = None

from ..chatbot.database import (
    AsyncSessionLocal,
    create_session,
    create_or_update_chat_thread,
    deactivate_session,
    get_session,
    get_session_chat_thread,
    get_session_pdfs,
    list_sessions,
    save_pdf_metadata,
    create_or_update_session_pdf_metadata,
    update_session_petition_inbox_state,
    update_thread_metadata,
)
from ..chatbot.models import CourtdriveIngestion, PDFDocument
from ..courtdrive.ingestion_db import create_or_update_ingestion, get_ingestion_status
from ..courtdrive.service import (
    CASE_NUMBER_REGEX,
    _extract_debtor_name_from_text,
    extract_case_number_from_filename,
    extract_district_from_sender_emails,
    extract_district_from_pdf_path,
    extract_petition_metadata_from_filename,
    extract_ssn_from_uploaded_petition_pdfs,
    normalize_case_value,
    normalize_client_name,
    normalize_to_short_case_number,
    scan_uploaded_petition_identities,
    strip_case_number_suffix,
)
from .auth import get_gmail_service
from .extractor import _extract_plain_text

DEFAULT_TRIGGER_SENDERS = [
    "BKECF@flnb.uscourts.gov",
    "FLSB_ECF_Notification@flsb.uscourts.gov",
    "bnc@flmb.uscourts.gov",
    "Courtmail@pawb.uscourts.gov",
]

UPLOADS_ROOT = Path(__file__).resolve().parent.parent.parent / "uploads"
ACTIVE_UPLOADS_ROOT = UPLOADS_ROOT / "active"
CASE_STORAGE_ROOT = UPLOADS_ROOT / "case_documents"
ARCHIVE_STORAGE_ROOT = UPLOADS_ROOT / "archived_petitions"  # synced to GDrive by shell script

_SCHEDULE_ONLY_MARKERS = (
    "schedule a/b",
    "schedule c",
    "schedule d",
    "schedule e/f",
    "schedule g",
    "schedule h",
    "schedule i",
    "schedule j",
    "statement of financial affairs",
    "summary of your assets and liabilities",
    "declaration about an individual's schedules",
)
_PETITION_MARKERS = (
    "voluntary petition",
    "official form 101",
    "the debtor requests relief",
    "all prior bankruptcy cases",
    "your current monthly income",
)
_VOLUNTARY_PETITION_SUBJECT_RE = re.compile(
    r"\b(?:chapter\s+\d+\s+)?voluntary\s+petition\b",
    re.IGNORECASE,
)

# Matches "Initial Schedules Filed:" with optional trailing text (case-insensitive)
_INITIAL_SCHEDULES_RE = re.compile(r"initial\s+schedules\s+filed\s*:", re.IGNORECASE)


def is_initial_schedules_subject(subject: str) -> bool:
    """Return True when an email subject signals an Initial Schedules Filed event."""
    return bool(_INITIAL_SCHEDULES_RE.search(subject or ""))


def _normalize_ssn_last4(value: Optional[str]) -> str:
    """Return a comparable SSN-last4 string."""
    digits = re.sub(r"\D", "", value or "")
    return digits[-4:] if digits else ""


def _compute_payload_fingerprint(payload: bytes) -> str | None:
    """Return a stable fingerprint for a document payload."""
    if not payload:
        return None
    return hashlib.sha256(payload).hexdigest()


def _resolve_managed_file_path(path: Optional[str]) -> Path:
    """Resolve file paths relative to the backend uploads root when needed."""
    candidate = (path or "").strip()
    if not candidate:
        return Path()
    parsed = Path(candidate)
    if candidate.startswith("/uploads/"):
        return (UPLOADS_ROOT.parent / candidate.lstrip("/")).resolve()
    if parsed.is_absolute():
        return parsed.resolve()
    if parsed.parts and parsed.parts[0] == "uploads":
        return (UPLOADS_ROOT.parent / parsed).resolve()
    return (UPLOADS_ROOT / parsed).resolve()


def _move_petition_file(src: Path, dest_dir: Path) -> str:
    """Move a petition file to dest_dir and return the new absolute path string."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    if dest.resolve() == src.resolve():
        return str(src)

    if dest.exists():
        stem = dest.stem
        suffix = dest.suffix
        counter = 1
        while True:
            candidate = dest_dir / f"{stem}_{counter}{suffix}"
            if candidate.resolve() == src.resolve():
                return str(src)
            if not candidate.exists():
                dest = candidate
                break
            counter += 1

    shutil.move(str(src), str(dest))
    return str(dest)


async def _move_session_pdfs_to_dir(
    session_id: str,
    dest_dir: Path,
    *,
    only_from: Optional[Path] = None,
) -> None:
    """Move all PDF files for a session to dest_dir, updating file_path in DB.

    only_from: if provided, only move files currently in that exact directory.
    """
    async with AsyncSessionLocal() as db:
        rows = await db.execute(
            text("SELECT id, file_path FROM pdf_documents WHERE session_id = :sid"),
            {"sid": session_id},
        )
        records = rows.fetchall()

    updates: list[tuple[str, str]] = []
    for row in records:
        old_path_str = (row.file_path or "").strip()
        if not old_path_str:
            continue
        src = _resolve_managed_file_path(old_path_str)
        if not src.exists() or not src.is_file():
            continue
        if only_from is not None and src.parent.resolve() != only_from.resolve():
            continue
        if src.parent.resolve() == dest_dir.resolve():
            continue
        new_path = _move_petition_file(src, dest_dir)
        updates.append((str(row.id), new_path))

    if not updates:
        return

    async with AsyncSessionLocal() as db:
        for doc_id, new_path in updates:
            await db.execute(
                text("UPDATE pdf_documents SET file_path = :path WHERE id = :id"),
                {"path": new_path, "id": doc_id},
            )
        await db.commit()


class PetitionMatchType:
    UPDATED = "UPDATED"
    UNFILED = "UNFILED"
    REFILED = "REFILED"
    NO_MATCH = "NO_MATCH"


@dataclass
class ParsedPetition:
    client_name: str
    ssn_last4: str
    case_number: str
    raw_text: str


class DocumentStorageService:
    """Stores and archives case documents in a case-scoped storage directory."""

    def __init__(
        self,
        root_dir: Path = CASE_STORAGE_ROOT,
        archive_root: Path = ARCHIVE_STORAGE_ROOT,
    ):
        self.root_dir = root_dir
        self.archive_root = archive_root
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self.archive_root.mkdir(parents=True, exist_ok=True)

    def store_document(
        self,
        session_id: str,
        case_number: str,
        filename: str,
        payload: bytes,
        document_type: str,
        source: str,
    ) -> dict[str, Any]:
        safe_filename = self._safe_filename(filename)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        session_key = self._safe_token(session_id, max_len=24) or "session"
        case_key = normalize_case_value(case_number or "") or "nocase"
        case_key = self._safe_token(case_key, max_len=24) or "nocase"

        # Store directly in /uploads/case_documents to avoid deep path nesting.
        stored_name = f"{timestamp}__sid_{session_key}__case_{case_key}__{safe_filename}"
        stored_path = self.root_dir / stored_name
        stored_path.write_bytes(payload)

        return {
            "session_id": session_id,
            "case_number": case_number,
            "document_type": document_type,
            "source": source,
            "filename": stored_name,
            "path": str(stored_path),
            "size_bytes": len(payload),
            "stored_at": datetime.now(timezone.utc).isoformat(),
        }

    async def archive_case_documents(self, session_id: str, reason: str) -> dict[str, Any]:
        from ..utils.sftp import sftp_client

        source_dir = self.root_dir / session_id

        moved_files: list[str] = []
        moved_sources: set[str] = set()

        def _push_and_delete(file_path: Path) -> str:
            """SFTP file directly to host synced folder, then delete local copy."""
            dest_filename = self._safe_filename(file_path.name)
            ok = sftp_client.push_file(str(file_path), dest_filename)
            if ok:
                file_path.unlink(missing_ok=True)
                return dest_filename
            else:
                raise RuntimeError(f"SFTP push failed for {file_path.name}")

        if source_dir.exists():
            for file_path in source_dir.rglob("*"):
                if not file_path.is_file():
                    continue
                dest_filename = _push_and_delete(file_path)
                moved_files.append(dest_filename)
                moved_sources.add(str(file_path.resolve()))

        # New flat storage format: files are stored directly under case_documents
        # and encoded with __sid_<session>__ prefix.
        session_key = self._safe_token(session_id, max_len=24)
        if session_key:
            for file_path in self.root_dir.glob(f"*__sid_{session_key}__*"):
                if not file_path.is_file():
                    continue
                resolved_source = str(file_path.resolve())
                if resolved_source in moved_sources:
                    continue
                dest_filename = _push_and_delete(file_path)
                moved_files.append(dest_filename)
                moved_sources.add(resolved_source)

        session_pdfs = await get_session_pdfs(session_id)
        for pdf in session_pdfs:
            file_path = _resolve_managed_file_path(pdf.file_path)
            if not file_path.exists():
                continue
            resolved_source = str(file_path.resolve())
            if resolved_source in moved_sources:
                continue
            dest_filename = _push_and_delete(file_path)
            moved_files.append(dest_filename)
            moved_sources.add(resolved_source)

        return {
            "session_id": session_id,
            "archived_files": moved_files,
            "reason": reason,
        }

    def _build_unique_archive_destination(self, filename: str) -> Path:
        """Return a flat archive destination that never overwrites an existing file."""
        safe_filename = self._safe_filename(filename)
        candidate = self.archive_root / safe_filename
        if not candidate.exists():
            return candidate

        stem = candidate.stem
        suffix = candidate.suffix
        counter = 1
        while True:
            deduped = self.archive_root / f"{stem}_{counter}{suffix}"
            if not deduped.exists():
                return deduped
            counter += 1

    @staticmethod
    def _safe_filename(filename: str) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", filename).strip("._")
        return cleaned or "document.pdf"

    @staticmethod
    def _safe_token(value: str, max_len: int = 24) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", (value or "")).strip("._-")
        if max_len > 0:
            return cleaned[:max_len]
        return cleaned


class PDFParsingService:
    """Parses petition PDFs to extract client name, SSN last4, and case number."""

    SSN_PATTERNS = [
        re.compile(r"[xX*]{3}-[xX*]{2}-(\d{4})"),
        re.compile(r"[xX*]{3}\s*[\-–]\s*[xX*]{2}\s*[\-–]\s*(\d\s?\d\s?\d\s?\d)"),
        # Unmasked full SSN (e.g. 123-45-6789) — extract last 4
        re.compile(r"\b\d{3}\s*[-–]\s*\d{2}\s*[-–]\s*(\d{4})\b"),
    ]

    def parse_petition_fields(self, pdf_bytes: bytes, fallback_filename: str = "") -> ParsedPetition:
        text = self._extract_text(pdf_bytes)
        case_number = self._extract_case_number(text, fallback_filename)
        ssn_last4 = self._extract_ssn_last4(text)
        client_name = self._extract_client_name(text, fallback_filename)

        return ParsedPetition(
            client_name=client_name,
            ssn_last4=ssn_last4,
            case_number=case_number,
            raw_text=text,
        )

    def is_voluntary_petition_content(self, pdf_bytes: bytes, fallback_filename: str = "") -> bool:
        """Return True only when the PDF content looks like a Voluntary Petition.

        Checks for _PETITION_MARKERS in the extracted text so that court orders,
        agreed orders, schedules, and other non-petition documents are rejected.
        """
        text = self._extract_text(pdf_bytes).lower()
        if not text:
            return False
        return any(marker in text for marker in _PETITION_MARKERS)

    def is_schedule_only_document(self, pdf_bytes: bytes, fallback_filename: str = "") -> bool:
        """Best-effort detection for schedule-only uploads."""
        filename = (fallback_filename or "").lower()
        if "schedule" in filename and "petition" not in filename:
            return True

        text = self._extract_text(pdf_bytes).lower()
        if not text:
            return False

        has_schedule_markers = any(marker in text for marker in _SCHEDULE_ONLY_MARKERS)
        has_petition_markers = any(marker in text for marker in _PETITION_MARKERS)
        return has_schedule_markers and not has_petition_markers

    def _extract_text(self, pdf_bytes: bytes) -> str:
        if not pdf_bytes or PdfReader is None:
            return ""
        try:
            reader = PdfReader(BytesIO(pdf_bytes))
            pages = [(page.extract_text() or "") for page in reader.pages]
            return "\n".join(part for part in pages if part)
        except Exception:
            return ""

    def _extract_case_number(self, text: str, fallback_filename: str) -> str:
        filename_metadata = extract_petition_metadata_from_filename(fallback_filename)
        parsed_case_number = (filename_metadata.get("case_number") or "").strip()
        if parsed_case_number:
            return normalize_to_short_case_number(parsed_case_number)

        filename_case_number = extract_case_number_from_filename(fallback_filename)
        if filename_case_number:
            return normalize_to_short_case_number(filename_case_number)

        if not text:
            return ""

        # Use the authoritative CASE_NUMBER_REGEX (handles chapter:YY-bk-N, YY-bk-N, YY-NNNNN).
        match = CASE_NUMBER_REGEX.search(text)
        if match:
            return normalize_to_short_case_number(match.group(0))

        return ""

    def _extract_ssn_last4(self, text: str) -> str:
        if not text:
            return ""

        for pattern in self.SSN_PATTERNS:
            match = pattern.search(text)
            if match:
                return match.group(1).replace(" ", "")
        return ""

    def _extract_client_name(self, text: str, fallback_filename: str) -> str:
        filename_metadata = extract_petition_metadata_from_filename(fallback_filename)
        parsed_name = (filename_metadata.get("client_name") or "").strip()
        if parsed_name:
            return strip_case_number_suffix(parsed_name)[:80]

        if text:
            parsed_text_name = (_extract_debtor_name_from_text(text) or "").strip()
            if parsed_text_name:
                return strip_case_number_suffix(parsed_text_name)[:80]

        stem = Path(fallback_filename).stem
        stem = re.sub(r"(?i)bankruptcy|petition|voluntary|pdf|_", " ", stem)
        stem = re.sub(r"\s+", " ", stem).strip()
        return strip_case_number_suffix(stem)[:80]


class CaseMatchingService:
    """Matches parsed petition data against existing case/session records."""

    async def list_active_case_identities(
        self,
        *,
        user_id: Optional[str] = None,
        exclude_session_ids: Optional[set[str]] = None,
    ) -> list[dict[str, Any]]:
        """Return normalized active-case identities for matching."""
        sessions = await list_sessions(user_id=user_id)
        excluded = exclude_session_ids or set()
        identities: list[dict[str, Any]] = []

        for session in sessions:
            if session.id in excluded:
                continue

            thread = await get_session_chat_thread(session.id)
            if not thread or not thread.is_active:
                continue

            thread_name = (thread.title or "").strip()
            if not thread_name or thread_name == "Untitled conversation":
                continue

            ssn_result = extract_ssn_from_uploaded_petition_pdfs(session.id)
            existing_ssn = ""
            if ssn_result.get("status") == "completed":
                existing_ssn = _normalize_ssn_last4(ssn_result.get("ssn_last4"))

            identities.append(
                {
                    "session_id": session.id,
                    "thread_id": thread.id,
                    "title": thread_name,
                    "normalized_name": normalize_client_name(thread_name),
                    "ssn_last4": existing_ssn,
                    "case_number": (thread.case_number or "").strip() or None,
                    "normalized_case": normalize_case_value((thread.case_number or "").strip()),
                    "updated_at": thread.updated_at or thread.created_at,
                    "user_id": session.user_id,
                }
            )

        identities.sort(
            key=lambda item: str(item.get("updated_at") or ""),
            reverse=True,
        )
        return identities

    def _match_candidate(
        self,
        identity: dict[str, Any],
        *,
        normalized_name: str,
        normalized_ssn: str,
        normalized_case: str,
        allow_name_only: bool,
    ) -> dict[str, Any] | None:
        candidate_name = (identity.get("normalized_name") or "").strip()
        candidate_ssn = _normalize_ssn_last4(identity.get("ssn_last4"))
        candidate_case = (identity.get("normalized_case") or "").strip()

        name_match = bool(normalized_name and candidate_name and candidate_name == normalized_name)
        candidate_tokens = {token for token in candidate_name.split(" ") if token}
        target_tokens = [token for token in normalized_name.split(" ") if token]
        token_overlap = sum(1 for token in target_tokens if token in candidate_tokens)
        partial_name_match = bool(
            normalized_name
            and candidate_name
            and not name_match
            and token_overlap >= min(2, len(target_tokens))
            and token_overlap > 0
        )
        ssn_match = bool(normalized_ssn and candidate_ssn and candidate_ssn == normalized_ssn)
        case_match = bool(normalized_case and candidate_case and candidate_case == normalized_case)

        if not (name_match or partial_name_match or ssn_match or case_match):
            return None
        if not allow_name_only and not (ssn_match or case_match):
            return None

        score = 0
        if name_match:
            score += 100
        elif partial_name_match:
            score += 55
        if ssn_match:
            score += 90
        if case_match:
            score += 50
        if name_match and ssn_match:
            score += 35
        elif partial_name_match and ssn_match:
            score += 20

        confidence = "weak"
        if name_match and ssn_match and case_match:
            confidence = "exact_name_ssn_case"
        elif name_match and ssn_match:
            confidence = "exact_name_ssn"
        elif partial_name_match and ssn_match:
            confidence = "partial_name_ssn"
        elif name_match and case_match:
            confidence = "exact_name_case"
        elif name_match:
            confidence = "exact_name"
        elif ssn_match:
            confidence = "exact_ssn"
        elif case_match:
            confidence = "exact_case"
        elif partial_name_match:
            confidence = "partial_name"

        return {
            **identity,
            "score": score,
            "confidence": confidence,
            "is_strong_match": name_match and ssn_match,
            "name_match": name_match or partial_name_match,
            "ssn_match": ssn_match,
            "case_match": case_match,
            "case_conflict": bool(normalized_case and candidate_case and candidate_case != normalized_case),
        }

    async def find_case_candidates(
        self,
        client_name: str,
        ssn_last4: str,
        case_number: str,
        *,
        user_id: Optional[str] = None,
        exclude_session_ids: Optional[set[str]] = None,
        allow_name_only: bool = True,
    ) -> list[dict[str, Any]]:
        """Find candidate active cases ordered by match quality."""
        normalized_name = normalize_client_name(client_name or "")
        normalized_case = normalize_case_value(case_number or "")
        normalized_ssn = _normalize_ssn_last4(ssn_last4)

        identities = await self.list_active_case_identities(
            user_id=user_id,
            exclude_session_ids=exclude_session_ids,
        )
        candidates: list[dict[str, Any]] = []

        for identity in identities:
            candidate = self._match_candidate(
                identity,
                normalized_name=normalized_name,
                normalized_ssn=normalized_ssn,
                normalized_case=normalized_case,
                allow_name_only=allow_name_only,
            )
            if candidate:
                candidates.append(candidate)

        candidates.sort(
            key=lambda item: (int(item.get("score") or 0), str(item.get("updated_at") or "")),
            reverse=True,
        )
        return candidates

    async def match_case(self, client_name: str, ssn_last4: str, case_number: str) -> dict[str, Any]:
        normalized_case = normalize_case_value(case_number or "")
        candidates = await self.find_case_candidates(
            client_name,
            ssn_last4,
            case_number,
            allow_name_only=False,
        )
        strong_candidates = [item for item in candidates if item.get("is_strong_match")]

        if normalized_case:
            for item in strong_candidates:
                if not (item.get("normalized_case") or "").strip():
                    return {
                        "match_type": PetitionMatchType.UNFILED,
                        "session_id": item["session_id"],
                        "thread_id": item["thread_id"],
                    }

        if normalized_case:
            for item in strong_candidates:
                if (item.get("normalized_case") or "").strip() == normalized_case:
                    return {
                        "match_type": PetitionMatchType.UPDATED,
                        "session_id": item["session_id"],
                        "thread_id": item["thread_id"],
                    }

        if normalized_case:
            for item in strong_candidates:
                if (item.get("normalized_case") or "").strip() and item.get("case_conflict"):
                    return {
                        "match_type": PetitionMatchType.REFILED,
                        "session_id": item["session_id"],
                        "thread_id": item["thread_id"],
                    }

        return {"match_type": PetitionMatchType.NO_MATCH, "session_id": None, "thread_id": None}


class CourtMailTriggerService:
    """Registers and manages case-specific court-mail monitoring triggers."""

    async def register_trigger(
        self,
        session_id: str,
        case_number: str,
        sender_emails: Optional[list[str]] = None,
        initial_epoch: Optional[int] = None,
    ) -> dict[str, Any]:
        """Register (or re-register) a court-mail polling trigger for a session.

        initial_epoch controls how far back the poll worker scans on its first run:
          - None / unset  → defaults to 0 (scan all history; safe default for any
                            path that did not perform its own upfront Gmail scan).
          - int(time.time()) → callers that already ran ingest_gmail_emails_for_session
                            can pass the current epoch so the poll only watches for
                            NEW emails going forward.
        """
        sender_list = [sender.strip() for sender in (sender_emails or DEFAULT_TRIGGER_SENDERS) if sender.strip()]
        payload = {
            "sender_emails": sender_list,
            "case_number": case_number,
            "last_checked_epoch": initial_epoch if initial_epoch is not None else 0,
            "registered_at": datetime.now(timezone.utc).isoformat(),
        }

        await create_or_update_ingestion(
            session_id=session_id,
            ingestion_type="court_mail_trigger",
            status="active",
            case_number=case_number,
            collection_name=f"court_mail_trigger_{session_id}",
            result=payload,
        )

        # Only store district when all sender emails agree on a single district code.
        # If DEFAULT_TRIGGER_SENDERS (all 4 districts) are used, we can't determine district.
        district_codes = {
            code
            for email in sender_list
            for code in [extract_district_from_sender_emails([email])]
            if code
        }
        if len(district_codes) == 1:
            thread = await get_session_chat_thread(session_id, include_inactive=True)
            if thread:
                await update_thread_metadata(thread.id, district=district_codes.pop())

        return {
            "session_id": session_id,
            "case_number": case_number,
            "sender_emails": sender_list,
            "status": "active",
        }

    async def list_active_triggers(self) -> list[dict[str, Any]]:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(CourtdriveIngestion).where(
                    CourtdriveIngestion.ingestion_type == "court_mail_trigger",
                    CourtdriveIngestion.status == "active",
                )
            )
            rows = result.scalars().all()

        triggers: list[dict[str, Any]] = []
        for row in rows:
            parsed_result = json.loads(row.result) if row.result else {}
            triggers.append(
                {
                    "session_id": row.session_id,
                    "case_number": row.case_number,
                    "sender_emails": parsed_result.get("sender_emails") or list(DEFAULT_TRIGGER_SENDERS),
                    "last_checked_epoch": parsed_result.get("last_checked_epoch", 0),
                }
            )

        return triggers

    async def update_last_checked(self, session_id: str, epoch: int) -> None:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(CourtdriveIngestion).where(
                    CourtdriveIngestion.session_id == session_id,
                    CourtdriveIngestion.ingestion_type == "court_mail_trigger",
                )
            )
            row = result.scalar_one_or_none()
            if not row:
                return

            payload = json.loads(row.result) if row.result else {}
            payload["last_checked_epoch"] = epoch
            row.result = json.dumps(payload)
            await db.commit()


class PetitionService:
    """Finds and attaches petitions with fallback priority: uploads -> court mail."""

    MANUAL_UPLOAD_REQUIRED_MESSAGE = "Petition not found. Please upload the petition manually."

    def __init__(
        self,
        storage_service: Optional[DocumentStorageService] = None,
        parser: Optional[PDFParsingService] = None,
        email_ingestion_service: Optional["EmailIngestionService"] = None,
    ):
        self.storage_service = storage_service or DocumentStorageService()
        self.parser = parser or PDFParsingService()
        self.email_ingestion_service = email_ingestion_service

    async def searchUploadsForPetition(
        self,
        caseNumber: Optional[str],
        debtorName: Optional[str],
        ssnLast4: Optional[str],
    ) -> Optional[dict[str, Any]]:
        return await self.search_uploads_for_petition(caseNumber, debtorName, ssnLast4)

    async def fetchPetitionFromCourtMail(
        self,
        caseNumber: str,
        senderEmails: Optional[list[str]] = None,
        maxResults: int = 25,
    ) -> Optional[dict[str, Any]]:
        return await self.fetch_petition_from_court_mail(caseNumber, senderEmails, maxResults)

    async def attachPetitionToCase(
        self,
        caseId: str,
        petitionFile: dict[str, Any],
        *,
        replaceExisting: bool = True,
        forceStoreCopy: bool = False,
        documentType: str = "petition",
        petitionStatus: Optional[str] = None,
        preserveExistingMetadata: bool = False,
    ) -> dict[str, Any]:
        return await self.attach_petition_to_case(
            caseId,
            petitionFile,
            replace_existing=replaceExisting,
            force_store_copy=forceStoreCopy,
            document_type=documentType,
            petition_status=petitionStatus,
            preserve_existing_metadata=preserveExistingMetadata,
        )

    async def search_uploads_for_petition(
        self,
        case_number: Optional[str],
        debtor_name: Optional[str],
        ssn_last4: Optional[str],
    ) -> Optional[dict[str, Any]]:
        normalized_case = normalize_case_value(case_number or "")
        normalized_name = normalize_client_name(debtor_name or "")
        normalized_ssn = (ssn_last4 or "").strip()

        # 1) Direct lookup in /uploads/case_documents (flat storage).
        direct_candidates: list[tuple[int, float, Path, bytes, ParsedPetition]] = []
        direct_files = sorted(
            [path for path in self.storage_service.root_dir.glob("*.pdf") if path.is_file()],
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        if not direct_files:
            # Backward-compatible fallback for legacy nested paths.
            direct_files = sorted(
                [path for path in self.storage_service.root_dir.rglob("*.pdf") if path.is_file()],
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )
        for pdf_path in direct_files[:300]:
            filename_score = self._score_identity_match(
                candidate_case=pdf_path.name,
                candidate_name=pdf_path.name,
                candidate_ssn=pdf_path.name,
                normalized_case=normalized_case,
                normalized_name=normalized_name,
                normalized_ssn=normalized_ssn,
            )
            if filename_score <= 0:
                continue

            payload = pdf_path.read_bytes()
            if not self.parser.is_voluntary_petition_content(payload, pdf_path.name):
                print(f"[search_uploads] Skipping non-petition file in case_documents: {pdf_path.name}")
                continue
            parsed = self.parser.parse_petition_fields(payload, fallback_filename=pdf_path.name)
            parsed_score = self._score_identity_match(
                candidate_case=parsed.case_number,
                candidate_name=parsed.client_name,
                candidate_ssn=parsed.ssn_last4,
                normalized_case=normalized_case,
                normalized_name=normalized_name,
                normalized_ssn=normalized_ssn,
            )
            score = filename_score + parsed_score
            if score <= 0:
                continue
            direct_candidates.append((score, pdf_path.stat().st_mtime, pdf_path, payload, parsed))

        if direct_candidates:
            direct_candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
            best_score, _, best_path, payload, parsed = direct_candidates[0]
            return {
                "source": "case_documents",
                "filename": best_path.name,
                "path": str(best_path),
                "bytes": payload,
                "match_score": best_score,
                "parsed": {
                    "client_name": parsed.client_name or "",
                    "ssn_last4": parsed.ssn_last4 or "",
                    "case_number": parsed.case_number or case_number or "",
                },
            }

        # 2) Fallback lookup in John's downloader /uploads root files.
        identity_scan = scan_uploaded_petition_identities(include_pdf_text_fallback=False)
        if identity_scan.get("status") != "completed":
            return None

        candidates: list[tuple[int, float, dict[str, Any]]] = []
        for record in identity_scan.get("records", []):
            record_path = Path(record.get("path") or "")
            if not record_path.exists() or not record_path.is_file():
                continue

            if any(part in {"case_documents", "archive", "court_mail"} for part in record_path.parts):
                continue

            record_case = normalize_case_value(record.get("case_number") or "")
            record_name = normalize_client_name(record.get("client_name") or "")
            record_ssn = (record.get("ssn_last4") or "").strip()

            score = 0
            if normalized_case and record_case and record_case == normalized_case:
                score += 100
            elif normalized_case and normalized_case in normalize_case_value(record_path.name):
                score += 60

            if normalized_ssn and record_ssn and record_ssn == normalized_ssn:
                score += 40

            if normalized_name and record_name:
                if record_name == normalized_name:
                    score += 30
                else:
                    target_tokens = [token for token in normalized_name.split(" ") if token]
                    matched_tokens = sum(1 for token in target_tokens[:4] if token in record_name)
                    score += matched_tokens * 5

            if score <= 0:
                continue

            candidates.append((score, record_path.stat().st_mtime, record))

        if not candidates:
            return None

        candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
        best_score, _, best_record = candidates[0]
        best_path = Path(best_record.get("path") or "")
        payload = best_path.read_bytes()
        parsed = self.parser.parse_petition_fields(payload, fallback_filename=best_path.name)

        return {
            "source": "uploads",
            "filename": best_path.name,
            "path": str(best_path),
            "bytes": payload,
            "match_score": best_score,
            "parsed": {
                "client_name": parsed.client_name or (best_record.get("client_name") or ""),
                "ssn_last4": parsed.ssn_last4 or (best_record.get("ssn_last4") or ""),
                "case_number": parsed.case_number or (best_record.get("case_number") or ""),
                "court_region": best_record.get("court_region") or "",
                "normalized_court_region": best_record.get("normalized_court_region") or "",
            },
        }

    @staticmethod
    def _score_identity_match(
        candidate_case: str,
        candidate_name: str,
        candidate_ssn: str,
        normalized_case: str,
        normalized_name: str,
        normalized_ssn: str,
    ) -> int:
        score = 0
        normalized_candidate_case = normalize_case_value(candidate_case or "")
        normalized_candidate_name = normalize_client_name(candidate_name or "")
        normalized_candidate_ssn = re.sub(r"\D", "", candidate_ssn or "")

        if normalized_case and normalized_case in normalized_candidate_case:
            score += 100

        if normalized_ssn and normalized_candidate_ssn.endswith(normalized_ssn):
            score += 40

        if normalized_name and normalized_candidate_name:
            if normalized_candidate_name == normalized_name:
                score += 30
            else:
                target_tokens = [token for token in normalized_name.split(" ") if token]
                matched_tokens = sum(1 for token in target_tokens[:4] if token in normalized_candidate_name)
                score += matched_tokens * 5

        return score

    async def fetch_petition_from_court_mail(
        self,
        case_number: str,
        sender_emails: Optional[list[str]] = None,
        max_results: int = 25,
    ) -> Optional[dict[str, Any]]:
        if not self.email_ingestion_service:
            raise ValueError("Email ingestion service is not configured for court mail fallback.")

        attachment = await self.email_ingestion_service.fetch_petition_attachment_for_case(
            case_number=case_number,
            sender_emails=sender_emails,
            max_results=max_results,
        )
        if not attachment:
            return None

        payload = attachment["bytes"]
        filename = attachment["filename"]
        parsed = self.parser.parse_petition_fields(payload, fallback_filename=filename)
        return {
            **attachment,
            "source": "court_mail_fallback",
            "parsed": {
                "client_name": parsed.client_name or "",
                "ssn_last4": parsed.ssn_last4 or "",
                "case_number": parsed.case_number or case_number,
            },
        }

    async def attach_petition_to_case(
        self,
        case_id: str,
        petition_file: dict[str, Any],
        *,
        replace_existing: bool = True,
        force_store_copy: bool = False,
        document_type: str = "petition",
        petition_status: Optional[str] = None,
        preserve_existing_metadata: bool = False,
    ) -> dict[str, Any]:
        payload = petition_file.get("bytes") or b""
        if not payload:
            raise ValueError(self.MANUAL_UPLOAD_REQUIRED_MESSAGE)

        filename = (petition_file.get("filename") or "").strip() or "petition.pdf"
        parsed = petition_file.get("parsed") or {}
        parsed_case_number = (parsed.get("case_number") or "").strip()
        source = (petition_file.get("source") or "").strip()

        # Store into case_documents only when the petition came from court email ingestion.
        is_court_mail_source = any(
            token in source.lower()
            for token in ("court_mail", "gmail_trigger", "accept_existing")
        )
        should_store_copy = force_store_copy or is_court_mail_source

        if should_store_copy:
            stored_document = self.storage_service.store_document(
                session_id=case_id,
                case_number=parsed_case_number,
                filename=filename,
                payload=payload,
                document_type=document_type,
                source=source or "petition_service",
            )
            persisted_path = stored_document["path"]
            persisted_filename = Path(stored_document["path"]).name
            persisted_size = stored_document["size_bytes"]
        else:
            existing_path = Path((petition_file.get("path") or "").strip())
            if not existing_path.exists() or not existing_path.is_file():
                raise ValueError("Petition file reference is missing. Please upload the petition manually.")

            persisted_path = str(existing_path)
            persisted_filename = existing_path.name
            persisted_size = int(existing_path.stat().st_size or len(payload))
            stored_document = {
                "session_id": case_id,
                "case_number": parsed_case_number,
                "document_type": document_type,
                "source": source or "uploads",
                "filename": persisted_filename,
                "path": persisted_path,
                "size_bytes": persisted_size,
                "linked_only": True,
            }

        if replace_existing:
            async with AsyncSessionLocal() as db:
                await db.execute(
                    text(
                        """
                        UPDATE pdf_documents
                        SET is_active = false
                        WHERE session_id = :session_id
                          AND is_active = true
                          AND (
                            collection_name LIKE 'case_documents_%'
                            OR LOWER(filename) LIKE '%petition%'
                            OR LOWER(original_filename) LIKE '%petition%'
                            OR LOWER(file_path) LIKE '%case_documents%'
                          )
                        """
                    ),
                    {"session_id": case_id},
                )
                await db.commit()

        await create_or_update_session_pdf_metadata(
            session_id=case_id,
            filename=persisted_filename,
            original_filename=filename,
            file_path=persisted_path,
            file_size=persisted_size,
            collection_name=f"case_documents_{case_id}",
            petition_status=petition_status,
            source="ecf",
        )

        thread = await get_session_chat_thread(case_id, include_inactive=True)
        if not thread:
            thread = await create_or_update_chat_thread(case_id)
        title = (parsed.get("client_name") or "").strip()
        case_number = parsed_case_number or None
        if title or case_number:
            next_title = title if title else None
            next_case_number = case_number
            if preserve_existing_metadata:
                if getattr(thread, "title", None):
                    next_title = None
                if getattr(thread, "case_number", None):
                    next_case_number = None
            await update_thread_metadata(
                thread.id,
                title=next_title,
                case_number=next_case_number,
            )

        # If parser couldn't extract client name, fall back to AI extraction
        # (same path as manual upload in routes_pdf.py)
        thread_title = (getattr(thread, "title", None) or "").strip()
        needs_title = not title and (not thread_title or thread_title == "Untitled conversation")
        if needs_title:
            try:
                from ..courtdrive.service import extract_debtor_name_for_session
                import asyncio
                loop = asyncio.get_event_loop()
                debtor_result = await loop.run_in_executor(
                    None, extract_debtor_name_for_session, case_id
                )
                if debtor_result.get("status") == "completed" and debtor_result.get("debtor_name"):
                    debtor_name = debtor_result["debtor_name"].strip()
                    clean_name = debtor_name.splitlines()[0].strip()[:60]
                    if clean_name and clean_name != "N/A":
                        await update_thread_metadata(thread.id, title=clean_name)
                        logger.info(f"[court_mail] Extracted debtor name via AI fallback: '{clean_name}' for session {case_id}")
                    else:
                        logger.warning(f"[court_mail] AI debtor extraction returned empty/invalid name for session {case_id}")
                else:
                    logger.warning(f"[court_mail] AI debtor extraction failed for session {case_id}: {debtor_result}")
            except Exception as e:
                logger.warning(f"[court_mail] Debtor name AI fallback failed for session {case_id}: {e}")

        return {
            "status": "attached",
            "session_id": case_id,
            "document": stored_document,
            "parsed": parsed,
        }

    async def retrieve_petition_for_case(
        self,
        case_number: str,
        debtor_name: Optional[str],
        ssn_last4: Optional[str],
        sender_emails: Optional[list[str]],
        max_results: int,
    ) -> dict[str, Any]:
        petition_file = await self.search_uploads_for_petition(case_number, debtor_name, ssn_last4)
        if petition_file:
            return petition_file

        petition_file = await self.fetch_petition_from_court_mail(
            case_number=case_number,
            sender_emails=sender_emails,
            max_results=max_results,
        )
        if petition_file:
            return petition_file

        raise ValueError(self.MANUAL_UPLOAD_REQUIRED_MESSAGE)


class CourtMailService:
    """Fetches existing case emails and starts case-specific listener triggers."""

    def __init__(
        self,
        trigger_service: Optional[CourtMailTriggerService] = None,
        email_ingestion_service: Optional["EmailIngestionService"] = None,
    ):
        self.trigger_service = trigger_service or CourtMailTriggerService()
        self.email_ingestion_service = email_ingestion_service or EmailIngestionService(
            trigger_service=self.trigger_service
        )

    async def fetchExistingCourtEmails(
        self,
        session_id: str,
        case_number: str,
        sender_emails: Optional[list[str]] = None,
        max_results: int = 25,
    ) -> dict[str, Any]:
        return await self.fetch_existing_court_emails(session_id, case_number, sender_emails, max_results)

    async def startCourtMailListener(
        self,
        session_id: str,
        case_number: str,
        sender_emails: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        return await self.start_court_mail_listener(session_id, case_number, sender_emails)

    async def ingestCourtEmail(
        self,
        session_id: str,
        case_number: str,
        message_id: str,
    ) -> dict[str, Any]:
        return await self.ingest_court_email(session_id, case_number, message_id)

    async def fetch_existing_court_emails(
        self,
        session_id: str,
        case_number: str,
        sender_emails: Optional[list[str]] = None,
        max_results: int = 25,
    ) -> dict[str, Any]:
        result = await self.email_ingestion_service.fetch_and_ingest_case_messages(
            session_id=session_id,
            case_number=case_number,
            sender_emails=sender_emails,
            max_results=max_results,
            include_petition=False,
            source="accept_existing",
        )
        return {**result, "mode": "existing_case_emails"}

    async def start_court_mail_listener(
        self,
        session_id: str,
        case_number: str,
        sender_emails: Optional[list[str]] = None,
        initial_epoch: Optional[int] = None,
    ) -> dict[str, Any]:
        return await self.trigger_service.register_trigger(
            session_id=session_id,
            case_number=case_number,
            sender_emails=sender_emails or list(DEFAULT_TRIGGER_SENDERS),
            initial_epoch=initial_epoch,
        )

    async def ingest_court_email(self, session_id: str, case_number: str, message_id: str) -> dict[str, Any]:
        return await self.email_ingestion_service.ingest_specific_message(
            session_id=session_id,
            message_id=message_id,
            case_number=case_number,
            include_petition=True,
            source="gmail_trigger",
        )


class CaseAcceptanceService:
    """Handles accept/deny/archive transitions for pending petition candidates."""

    def __init__(
        self,
        trigger_service: Optional[CourtMailTriggerService] = None,
        storage_service: Optional[DocumentStorageService] = None,
        petition_service: Optional[PetitionService] = None,
        court_mail_service: Optional[CourtMailService] = None,
        email_ingestion_service: Optional["EmailIngestionService"] = None,
    ):
        self.trigger_service = trigger_service or CourtMailTriggerService()
        self.storage_service = storage_service or DocumentStorageService()
        self.email_ingestion_service = email_ingestion_service or EmailIngestionService(
            trigger_service=self.trigger_service,
            storage_service=self.storage_service,
        )
        self.petition_service = petition_service or PetitionService(
            storage_service=self.storage_service,
            email_ingestion_service=self.email_ingestion_service,
        )
        self.court_mail_service = court_mail_service or CourtMailService(
            trigger_service=self.trigger_service,
            email_ingestion_service=self.email_ingestion_service,
        )

    async def accept_case(
        self,
        session_id: str,
        case_number: Optional[str],
        client_name: Optional[str],
        sender_emails: Optional[list[str]] = None,
        max_results: int = 25,
    ) -> dict[str, Any]:
        session = await get_session(session_id)
        if not session:
            raise ValueError("Session not found or inactive")

        # Reuse the existing session thread (including inactive) so message history
        # stays under the same thread ID after acceptance.
        thread = await get_session_chat_thread(session_id, include_inactive=True)
        if thread:
            await self._set_thread_active(thread.id, True)
        else:
            thread = await create_or_update_chat_thread(session_id)
            await self._set_thread_active(thread.id, True)

        if client_name and client_name.strip() and client_name != "N/A":
            await update_thread_metadata(thread.id, title=client_name.strip())

        resolved_case_number = (case_number or "").strip() or (thread.case_number or "").strip()
        if not resolved_case_number:
            raise ValueError("Case number is required to register a court-mail trigger.")
        await update_thread_metadata(thread.id, case_number=resolved_case_number)

        # Try PDF-based district extraction first (AI-powered, most accurate).
        # Fall back to sender email only if no PDF is available.
        district: Optional[str] = None
        try:
            session_pdfs_for_district = await get_session_pdfs(session_id)
            for pdf in session_pdfs_for_district:
                pdf_path_str = (getattr(pdf, "file_path", None) or "").strip()
                if pdf_path_str and Path(pdf_path_str).exists():
                    district = extract_district_from_pdf_path(pdf_path_str)
                    if district:
                        break
        except Exception as e:
            print(f"DEBUG accept_case district PDF error: {e}")
        if not district:
            # Only assign district when all provided senders agree on a single district.
            # If DEFAULT_TRIGGER_SENDERS (all 4 courts) are passed, this is ambiguous.
            sender_district_codes = {
                code
                for email in (sender_emails or [])
                for code in [extract_district_from_sender_emails([email])]
                if code
            }
            if len(sender_district_codes) == 1:
                district = sender_district_codes.pop()
        if district:
            await update_thread_metadata(thread.id, district=district)

        ssn_result = extract_ssn_from_uploaded_petition_pdfs(session_id)
        resolved_ssn_last4 = ""
        if ssn_result.get("status") == "completed":
            resolved_ssn_last4 = (ssn_result.get("ssn_last4") or "").strip()

        petition_file = None
        session_pdfs = sorted(
            await get_session_pdfs(session_id),
            key=lambda pdf: getattr(pdf, "uploaded_at", None) or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        for pdf in session_pdfs:
            pdf_path = Path((pdf.file_path or "").strip())
            if not pdf_path.exists() or not pdf_path.is_file():
                continue
            payload = pdf_path.read_bytes()
            fallback_name = pdf.original_filename or pdf.filename or pdf_path.name
            if not self.petition_service.parser.is_voluntary_petition_content(payload, fallback_name):
                print(
                    f"[accept_case] Skipping non-petition PDF in session {session_id}: {fallback_name}"
                )
                continue
            parsed = self.petition_service.parser.parse_petition_fields(
                payload,
                fallback_filename=fallback_name,
            )
            petition_file = {
                "source": "uploads_pending_session",
                "filename": pdf_path.name,
                "path": str(pdf_path),
                "bytes": payload,
                "parsed": {
                    "client_name": parsed.client_name or (client_name or ""),
                    "ssn_last4": parsed.ssn_last4 or resolved_ssn_last4,
                    "case_number": parsed.case_number or resolved_case_number,
                },
            }
            break

        if not petition_file:
            petition_file = await self.petition_service.retrieve_petition_for_case(
                case_number=resolved_case_number,
                debtor_name=client_name or thread.title,
                ssn_last4=resolved_ssn_last4,
                sender_emails=sender_emails or list(DEFAULT_TRIGGER_SENDERS),
                max_results=max_results,
            )
        petition_result = await self.petition_service.attach_petition_to_case(
            case_id=session_id,
            petition_file=petition_file,
        )

        try:
            from ..chatbot.vectorestore import process_uploaded_file, clear_collection

            stored_document = (petition_result or {}).get("document") or {}
            petition_path = stored_document.get("path")
            if petition_path:
                session_collection = f"bankruptcy_knowledge_{session_id}"
                clear_collection(session_collection)
                ingest_result = process_uploaded_file(
                    petition_path,
                    file_type="pdf",
                    collection_name=session_collection,
                )
                if ingest_result.get("success"):
                    print(f"✅ Indexed accepted-case petition for session {session_id}: {ingest_result.get('stored_count')} chunks")
                else:
                    print(f"⚠️ Failed to index accepted-case petition: {ingest_result.get('error')}")
        except Exception as e:
            print(f"⚠️ Failed to index accepted-case petition for session {session_id}: {e}")

        existing_emails_result = await self.court_mail_service.fetch_existing_court_emails(
            session_id=session_id,
            case_number=resolved_case_number,
            sender_emails=sender_emails or list(DEFAULT_TRIGGER_SENDERS),
            max_results=max_results,
        )

        # Upfront email scan was already done above; poll worker should only
        # watch for NEW emails from this moment onward.
        trigger_result = await self.court_mail_service.start_court_mail_listener(
            session_id=session_id,
            case_number=resolved_case_number,
            sender_emails=sender_emails or list(DEFAULT_TRIGGER_SENDERS),
            initial_epoch=int(time.time()),
        )

        accepted_at = datetime.now(timezone.utc)
        existing_pending_state = await get_ingestion_status(session_id, "pending_acceptance")
        existing_pending_result = (
            existing_pending_state.get("result")
            if isinstance(existing_pending_state, dict)
            else {}
        )
        if not isinstance(existing_pending_result, dict):
            existing_pending_result = {}
        await create_or_update_ingestion(
            session_id=session_id,
            ingestion_type="pending_acceptance",
            status="accepted",
            case_number=resolved_case_number or None,
            collection_name=f"case_state_{session_id}",
            result={
                **existing_pending_result,
                "status": "accepted",
                "accepted_at": accepted_at.isoformat(),
                "petition_status": "accepted",
                "inbox_checked_at": accepted_at.isoformat(),
                "petition_source": petition_file.get("source"),
                "petition_document": petition_result.get("document"),
                "existing_court_mail": {
                    "emails_scanned": existing_emails_result.get("emails_scanned", 0),
                    "documents_stored": existing_emails_result.get("documents_stored", 0),
                },
            },
        )
        await update_session_petition_inbox_state(
            session_id,
            petition_status="accepted",
            inbox_checked_at=accepted_at,
        )
        await _move_session_pdfs_to_dir(session_id, ACTIVE_UPLOADS_ROOT, only_from=UPLOADS_ROOT)

        # Auto-merge any pending inbox entries that match this newly accepted case (2-of-3)
        try:
            from ..chatbot.pending_petitions import PendingPetitionResolutionService
            _merge_svc = PendingPetitionResolutionService()
            _merged = await _merge_svc.auto_merge_pending_on_case_match(
                session_id,
                user_id=session.user_id,
                case_number=resolved_case_number or None,
                debtor_name=client_name or None,
                ssn_last4=resolved_ssn_last4 or None,
            )
            if _merged:
                print(f"[accept_case] auto_merge absorbed {len(_merged)} pending session(s) into {session_id}")
        except Exception as _merge_exc:
            print(f"[accept_case] auto_merge_pending_on_case_match failed: {_merge_exc}")

        async with AsyncSessionLocal() as _db:
            await _db.execute(
                text("DELETE FROM pending_session_file_locks WHERE session_id = :session_id"),
                {"session_id": session_id},
            )
            await _db.commit()

        return {
            "status": "accepted",
            "session_id": session_id,
            "case_number": resolved_case_number or None,
            "client_name": client_name,
            "petition": petition_result,
            "existing_court_mail": existing_emails_result,
            "trigger": trigger_result,
            "message": "Case accepted, petition attached, court-mail listener started.",
        }

    async def deny_case(self, session_id: str) -> dict[str, Any]:
        denied_at = datetime.now(timezone.utc)
        await deactivate_session(session_id)
        async with AsyncSessionLocal() as _db:
            await _db.execute(
                text("DELETE FROM pending_session_file_locks WHERE session_id = :session_id"),
                {"session_id": session_id},
            )
            await _db.commit()
        await create_or_update_ingestion(
            session_id=session_id,
            ingestion_type="pending_acceptance",
            status="denied",
            collection_name=f"case_state_{session_id}",
            result={
                "status": "denied",
                "denied_at": denied_at.isoformat(),
                "petition_status": "denied",
                "inbox_checked_at": denied_at.isoformat(),
            },
        )
        await update_session_petition_inbox_state(
            session_id,
            petition_status="denied",
            inbox_checked_at=denied_at,
        )
        await _move_session_pdfs_to_dir(session_id, UPLOADS_ROOT, only_from=ACTIVE_UPLOADS_ROOT)
        return {"status": "denied", "session_id": session_id}

    async def archive_case(self, session_id: str, reason: str = "manual") -> dict[str, Any]:
        archived_at = datetime.now(timezone.utc)
        archive_result = await self.storage_service.archive_case_documents(session_id, reason=reason)
        await deactivate_session(session_id)
        async with AsyncSessionLocal() as _db:
            await _db.execute(
                text("DELETE FROM pending_session_file_locks WHERE session_id = :session_id"),
                {"session_id": session_id},
            )
            await _db.commit()
        await create_or_update_ingestion(
            session_id=session_id,
            ingestion_type="pending_acceptance",
            status="archived",
            collection_name=f"case_state_{session_id}",
            result={
                "status": "archived",
                "archived_at": archived_at.isoformat(),
                "petition_status": "archived",
                "inbox_checked_at": archived_at.isoformat(),
                "reason": reason,
                "files": archive_result.get("archived_files", []),
            },
        )
        await update_session_petition_inbox_state(
            session_id,
            petition_status="archived",
            inbox_checked_at=archived_at,
        )
        return {"status": "archived", "session_id": session_id, **archive_result}

    async def auto_archive_stale_pending_cases(self, max_age_hours: int = 48) -> dict[str, Any]:
        """Mark pending petition sessions as auto_archived when their file no longer exists on disk.

        Runs as a reconciliation job: any pending session whose petition file has been
        swept by the archiver service (file missing from disk) is deactivated with
        petition_status='auto_archived' so it disappears from the inbox.
        """
        archived_at = datetime.now(timezone.utc)

        async with AsyncSessionLocal() as db:
            rows = await db.execute(
                text(
                    """
                    SELECT DISTINCT ON (p.session_id)
                        p.session_id, p.id AS pdf_id, p.file_path
                    FROM pdf_documents p
                    INNER JOIN sessions s ON s.id = p.session_id
                    WHERE p.petition_status = 'pending_acceptance'
                      AND p.is_active = true
                      AND s.is_active = true
                    ORDER BY p.session_id, p.uploaded_at DESC
                    """
                )
            )
            pending_records = rows.fetchall()

        archived_sessions: list[str] = []
        errors: list[str] = []

        for row in pending_records:
            session_id = str(row.session_id)
            file_path_str = (row.file_path or "").strip()
            if not file_path_str:
                continue

            file_path = _resolve_managed_file_path(file_path_str)
            if file_path.exists() and file_path.is_file():
                continue

            try:
                await create_or_update_ingestion(
                    session_id=session_id,
                    ingestion_type="pending_acceptance",
                    status="auto_archived",
                    collection_name=f"case_state_{session_id}",
                    result={
                        "status": "auto_archived",
                        "auto_archived_at": archived_at.isoformat(),
                        "petition_status": "auto_archived",
                        "reason": "petition_file_missing",
                    },
                )
                await update_session_petition_inbox_state(
                    session_id,
                    petition_status="auto_archived",
                    inbox_checked_at=archived_at,
                )
                await deactivate_session(session_id)
                archived_sessions.append(session_id)
                print(f"[auto_archive] Session {session_id} marked auto_archived (file missing: {file_path_str})")
            except Exception as e:
                errors.append(session_id)
                print(f"[auto_archive] Failed to auto-archive session {session_id}: {e}")

        return {
            "status": "completed",
            "archived_count": len(archived_sessions),
            "sessions": archived_sessions,
            "errors": errors,
        }

    async def _set_thread_active(self, thread_id: str, is_active: bool) -> None:
        async with AsyncSessionLocal() as db:
            await db.execute(
                text("UPDATE chat_threads SET is_active = :is_active, updated_at = now() WHERE id = :thread_id"),
                {"thread_id": thread_id, "is_active": is_active},
            )
            await db.commit()


class PetitionExtractionService:
    """Extracts petition data from email attachments and executes case-matching actions."""

    def __init__(
        self,
        parser: Optional[PDFParsingService] = None,
        matcher: Optional[CaseMatchingService] = None,
        storage: Optional[DocumentStorageService] = None,
    ):
        self.parser = parser or PDFParsingService()
        self.matcher = matcher or CaseMatchingService()
        self.storage = storage or DocumentStorageService()

    async def ingest_petition_attachment(
        self,
        trigger_session_id: str,
        email_metadata: dict[str, Any],
        attachment_filename: str,
        attachment_bytes: bytes,
    ) -> dict[str, Any]:
        parsed = self.parser.parse_petition_fields(attachment_bytes, fallback_filename=attachment_filename)

        # Require at least a name plus either SSN or case number for meaningful matching.
        # A name alone cannot uniquely identify a case and would produce false matches.
        if not parsed.client_name or (not parsed.ssn_last4 and not parsed.case_number):
            return {
                "status": "skipped",
                "reason": "missing_required_fields",
                "parsed": {
                    "client_name": parsed.client_name,
                    "ssn_last4": parsed.ssn_last4,
                    "case_number": parsed.case_number,
                },
            }

        match_result = await self.matcher.match_case(parsed.client_name, parsed.ssn_last4, parsed.case_number)
        match_type = match_result["match_type"]

        if match_type in {PetitionMatchType.UPDATED, PetitionMatchType.UNFILED}:
            session_id = match_result["session_id"]
            thread_id = match_result["thread_id"]

            stored_document = self.storage.store_document(
                session_id=session_id,
                case_number=parsed.case_number,
                filename=attachment_filename,
                payload=attachment_bytes,
                document_type="petition",
                source="gmail_trigger",
            )

            await self._replace_active_session_petition(
                session_id=session_id,
                original_filename=attachment_filename,
                stored_path=stored_document["path"],
                file_size=stored_document["size_bytes"],
            )

            # Index updated petition into vectorstore for AI agent context
            try:
                from ..chatbot.vectorestore import process_uploaded_file, clear_collection

                session_collection = f"bankruptcy_knowledge_{session_id}"
                clear_collection(session_collection)
                ingest_result = process_uploaded_file(
                    stored_document["path"],
                    file_type="pdf",
                    collection_name=session_collection
                )
                if ingest_result.get("success"):
                    print(f"✅ Re-indexed petition for session {session_id}: {ingest_result.get('stored_count')} chunks")
                else:
                    print(f"⚠️ Failed to re-index petition: {ingest_result.get('error')}")
            except Exception as e:
                print(f"⚠️ Failed to re-index petition for session {session_id}: {e}")

            if match_type == PetitionMatchType.UNFILED and parsed.case_number:
                await update_thread_metadata(thread_id, case_number=parsed.case_number)
                await create_or_update_ingestion(
                    session_id=session_id,
                    ingestion_type="case_status",
                    status="completed",
                    case_number=parsed.case_number,
                    collection_name=f"case_state_{session_id}",
                    result={
                        "status": "FILED",
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    },
                )

            return {
                "status": "completed",
                "match_type": match_type,
                "session_id": session_id,
                "case_number": parsed.case_number,
                "document": stored_document,
            }

        # REFILED / NO_MATCH -> create pending acceptance candidate (inactive until user accepts)
        base_session = await get_session(trigger_session_id)
        new_session = await create_session(
            user_id=base_session.user_id if base_session else None,
            firm_id=base_session.firm_id if base_session else None,
        )
        new_thread = await create_or_update_chat_thread(new_session.id)
        await self._set_thread_active(new_thread.id, False)
        await update_thread_metadata(
            new_thread.id,
            title=parsed.client_name,
            case_number=parsed.case_number or None,
            summary="Pending acceptance candidate generated from Gmail petition trigger.",
        )

        stored_document = self.storage.store_document(
            session_id=new_session.id,
            case_number=parsed.case_number,
            filename=attachment_filename,
            payload=attachment_bytes,
            document_type="petition",
            source="gmail_trigger",
        )

        await save_pdf_metadata(
            session_id=new_session.id,
            filename=Path(stored_document["path"]).name,
            original_filename=attachment_filename,
            file_path=stored_document["path"],
            file_size=stored_document["size_bytes"],
            collection_name=f"case_documents_{new_session.id}",
            petition_status="pending_acceptance",
            source="ecf",
        )

        expires_at = datetime.now(timezone.utc) + timedelta(hours=48)
        case_status = "REFILED" if match_type == PetitionMatchType.REFILED else "PENDING_ACCEPTANCE"

        await create_or_update_ingestion(
            session_id=new_session.id,
            ingestion_type="pending_acceptance",
            status="pending_acceptance",
            case_number=parsed.case_number or None,
            collection_name=f"case_candidates_{new_session.id}",
            result={
                "status": case_status,
                "match_type": match_type,
                "trigger_session_id": trigger_session_id,
                "source_email": email_metadata,
                "client_name": parsed.client_name,
                "ssn_last4": parsed.ssn_last4,
                "case_number": parsed.case_number,
                "expires_at": expires_at.isoformat(),
                "petition_file_fingerprint": _compute_payload_fingerprint(attachment_bytes),
            },
        )

        return {
            "status": "completed",
            "match_type": match_type,
            "session_id": new_session.id,
            "case_number": parsed.case_number,
            "pending_acceptance": True,
            "document": stored_document,
        }

    async def _replace_active_session_petition(
        self,
        session_id: str,
        original_filename: str,
        stored_path: str,
        file_size: int,
    ) -> None:
        async with AsyncSessionLocal() as db:
            try:
                await db.execute(
                    text(
                        "UPDATE pdf_documents SET is_active = false "
                        "WHERE session_id = :session_id AND is_active = true"
                    ),
                    {"session_id": session_id},
                )
                db.add(
                    PDFDocument(
                        session_id=session_id,
                        filename=Path(stored_path).name,
                        original_filename=original_filename,
                        file_path=stored_path,
                        file_size=file_size,
                        collection_name=f"case_documents_{session_id}",
                        is_active=True,
                    )
                )
                await db.commit()
            except Exception:
                await db.rollback()
                raise

    async def _set_thread_active(self, thread_id: str, is_active: bool) -> None:
        async with AsyncSessionLocal() as db:
            await db.execute(
                text("UPDATE chat_threads SET is_active = :is_active, updated_at = now() WHERE id = :thread_id"),
                {"thread_id": thread_id, "is_active": is_active},
            )
            await db.commit()


class ScheduleMergeService:
    """Stages schedule filings and resolves them into an existing accepted case."""

    def __init__(
        self,
        storage_service: Optional[DocumentStorageService] = None,
        parser: Optional[PDFParsingService] = None,
    ):
        self.storage_service = storage_service or DocumentStorageService()
        self.parser = parser or PDFParsingService()

    async def merge_initial_schedules(
        self,
        *,
        target_session_id: str,
        case_number: str,
        email_metadata: dict[str, Any],
        attachments: list[dict[str, Any]],
        source: str = "gmail_trigger",
    ) -> dict[str, Any]:
        if not attachments:
            return {
                "status": "skipped",
                "reason": "no_schedule_attachments",
                "stored_documents": [],
            }

        target_session = await get_session(target_session_id)
        if not target_session:
            raise ValueError("Target session not found or inactive")

        target_thread = await get_session_chat_thread(target_session_id, include_inactive=True)
        target_identity = self._resolve_target_identity(
            target_session_id=target_session_id,
            target_thread=target_thread,
        )
        first_attachment_identity = self._parse_attachment_identity(attachments[0])

        resolved_case_number = (
            (case_number or "").strip()
            or target_identity.get("case_number")
            or first_attachment_identity.get("case_number")
            or ""
        )
        resolved_client_name = (
            target_identity.get("client_name")
            or first_attachment_identity.get("client_name")
            or ""
        )
        resolved_ssn_last4 = (
            target_identity.get("ssn_last4")
            or first_attachment_identity.get("ssn_last4")
            or ""
        )

        pending_session = await create_session(user_id=target_session.user_id, firm_id=target_session.firm_id)
        pending_thread = await create_or_update_chat_thread(pending_session.id)
        await self._set_thread_active(pending_thread.id, False)
        await update_thread_metadata(
            pending_thread.id,
            title=resolved_client_name or None,
            case_number=resolved_case_number or None,
            summary="Pending schedule filing generated from court-mail trigger.",
        )

        stored_documents: list[dict[str, Any]] = []
        for attachment in attachments:
            filename = (attachment.get("filename") or "").strip() or "schedule_filed.pdf"
            payload = attachment.get("bytes") or b""
            if not payload:
                continue

            stored_document = self.storage_service.store_document(
                session_id=pending_session.id,
                case_number=resolved_case_number,
                filename=filename,
                payload=payload,
                document_type="schedule_filed",
                source=source,
            )
            stored_documents.append(stored_document)

            await save_pdf_metadata(
                session_id=pending_session.id,
                filename=Path(stored_document["path"]).name,
                original_filename=filename,
                file_path=stored_document["path"],
                file_size=stored_document["size_bytes"],
                collection_name=f"case_documents_{pending_session.id}",
                petition_status="pending_acceptance",
                source="ecf",
            )

        if not stored_documents:
            raise ValueError("Initial schedules email did not contain any readable PDF attachments.")

        received_at = (
            (email_metadata.get("date") or "").strip()
            or datetime.now(timezone.utc).isoformat()
        )
        await create_or_update_ingestion(
            session_id=pending_session.id,
            ingestion_type="pending_acceptance",
            status="pending_acceptance",
            case_number=resolved_case_number or None,
            collection_name=f"case_candidates_{pending_session.id}",
            result={
                "status": "PENDING_ACCEPTANCE",
                "source": "court_mail_initial_schedules",
                "source_label": "Court mail schedule filing",
                "trigger_session_id": target_session_id,
                "client_name": resolved_client_name or None,
                "title": resolved_client_name or None,
                "ssn_last4": resolved_ssn_last4 or None,
                "case_number": resolved_case_number or None,
                "received_at": received_at,
                "source_email": email_metadata,
                "petition_file_fingerprint": _compute_payload_fingerprint(
                    attachments[0].get("bytes") or b""
                ),
            },
            is_viewed=True,
        )

        from ..chatbot.pending_petitions import PendingPetitionResolutionService

        resolution_service = PendingPetitionResolutionService()
        merge_result = await resolution_service.resolve(
            pending_session.id,
            action="merge_schedule",
            user_id=target_session.user_id,
            target_session_id=target_session_id,
            client_name=resolved_client_name or None,
            ssn_last4=resolved_ssn_last4 or None,
            case_number=resolved_case_number or None,
        )

        return {
            **merge_result,
            "stored_documents": stored_documents,
            "pending_session_id": pending_session.id,
        }

    def _resolve_target_identity(
        self,
        *,
        target_session_id: str,
        target_thread: Any,
    ) -> dict[str, str]:
        client_name = strip_case_number_suffix(
            ((getattr(target_thread, "title", None) or "").strip())
        )[:80]
        case_number = ((getattr(target_thread, "case_number", None) or "").strip())

        ssn_last4 = ""
        try:
            ssn_result = extract_ssn_from_uploaded_petition_pdfs(target_session_id)
            if ssn_result.get("status") == "completed":
                ssn_last4 = (ssn_result.get("ssn_last4") or "").strip()
        except Exception:
            ssn_last4 = ""

        return {
            "client_name": client_name,
            "case_number": case_number,
            "ssn_last4": ssn_last4,
        }

    def _parse_attachment_identity(self, attachment: dict[str, Any]) -> dict[str, str]:
        payload = attachment.get("bytes") or b""
        filename = (attachment.get("filename") or "").strip()
        parsed = self.parser.parse_petition_fields(payload, fallback_filename=filename)
        return {
            "client_name": (parsed.client_name or "").strip(),
            "case_number": (parsed.case_number or "").strip(),
            "ssn_last4": (parsed.ssn_last4 or "").strip(),
        }

    async def _set_thread_active(self, thread_id: str, is_active: bool) -> None:
        async with AsyncSessionLocal() as db:
            await db.execute(
                text("UPDATE chat_threads SET is_active = :is_active, updated_at = now() WHERE id = :thread_id"),
                {"thread_id": thread_id, "is_active": is_active},
            )
            await db.commit()


class EmailIngestionService:
    """Centralized Gmail API ingestion for case triggers and petition extraction."""

    def __init__(
        self,
        trigger_service: Optional[CourtMailTriggerService] = None,
        storage_service: Optional[DocumentStorageService] = None,
        petition_service: Optional[PetitionExtractionService] = None,
        schedule_merge_service: Optional[ScheduleMergeService] = None,
    ):
        self.trigger_service = trigger_service or CourtMailTriggerService()
        self.storage_service = storage_service or DocumentStorageService()
        self.petition_service = petition_service or PetitionExtractionService(storage=self.storage_service)
        self.schedule_merge_service = schedule_merge_service or ScheduleMergeService(
            storage_service=self.storage_service
        )

    async def poll_triggered_cases(self, max_results_per_trigger: int = 25) -> dict[str, Any]:
        triggers = await self.trigger_service.list_active_triggers()
        if not triggers:
            return {
                "status": "completed",
                "message": "No active court-mail triggers.",
                "triggers_polled": 0,
                "emails_scanned": 0,
                "documents_stored": 0,
            }

        total_scanned = 0
        total_stored = 0
        petition_events = 0
        schedule_merge_events = 0

        for trigger in triggers:
            session_id = trigger["session_id"]
            case_number = trigger.get("case_number") or ""
            senders = trigger.get("sender_emails") or list(DEFAULT_TRIGGER_SENDERS)
            after_epoch = int(trigger.get("last_checked_epoch") or 0)

            result = await self.fetch_and_ingest_case_messages(
                session_id=session_id,
                case_number=case_number,
                sender_emails=senders,
                max_results=max_results_per_trigger,
                include_petition=True,
                after_epoch=after_epoch,
                source="gmail_trigger",
            )
            total_scanned += result.get("emails_scanned", 0)
            total_stored += result.get("documents_stored", 0)
            petition_events += result.get("petition_events", 0)
            schedule_merge_events += result.get("schedule_merge_events", 0)

            await self.trigger_service.update_last_checked(session_id, int(time.time()))

        return {
            "status": "completed",
            "triggers_polled": len(triggers),
            "emails_scanned": total_scanned,
            "documents_stored": total_stored,
            "petition_events": petition_events,
            "schedule_merge_events": schedule_merge_events,
        }

    async def fetch_and_ingest_case_messages(
        self,
        session_id: str,
        case_number: str,
        sender_emails: Optional[list[str]] = None,
        max_results: int = 25,
        include_petition: bool = True,
        after_epoch: int = 0,
        source: str = "gmail_trigger",
    ) -> dict[str, Any]:
        gmail_service = get_gmail_service()
        query = self._build_trigger_query(
            sender_emails or list(DEFAULT_TRIGGER_SENDERS),
            case_number,
            after_epoch,
            has_attachment=False,
        )
        message_refs = self._list_messages(gmail_service, query=query, max_results=max_results)

        total_scanned = 0
        total_stored = 0
        petition_events = 0
        schedule_merge_events = 0

        for msg_ref in message_refs:
            message_id = msg_ref.get("id")
            if not message_id:
                continue
            processed = await self._ingest_message_for_trigger(
                gmail_service=gmail_service,
                session_id=session_id,
                case_number=case_number,
                message_id=message_id,
                include_petition=include_petition,
                source=source,
            )
            total_scanned += processed["scanned"]
            total_stored += processed["stored_docs"]
            petition_events += processed["petition_events"]
            schedule_merge_events += processed.get("schedule_merge_events", 0)

        return {
            "status": "completed",
            "session_id": session_id,
            "case_number": case_number,
            "query": query,
            "emails_scanned": total_scanned,
            "documents_stored": total_stored,
            "petition_events": petition_events,
            "schedule_merge_events": schedule_merge_events,
            "messages_found": len(message_refs),
            "source": source,
        }

    async def fetch_petition_attachment_for_case(
        self,
        case_number: str,
        sender_emails: Optional[list[str]] = None,
        max_results: int = 25,
    ) -> Optional[dict[str, Any]]:
        gmail_service = get_gmail_service()
        query = self._build_trigger_query(
            sender_emails or list(DEFAULT_TRIGGER_SENDERS),
            case_number,
            after_epoch=0,
            has_attachment=True,
        )
        message_refs = self._list_messages(gmail_service, query=query, max_results=max_results)

        for msg_ref in message_refs:
            message_id = msg_ref.get("id")
            if not message_id:
                continue

            msg = (
                gmail_service.users()
                .messages()
                .get(userId="me", id=message_id, format="full")
                .execute()
            )
            payload = msg.get("payload", {}) or {}
            headers = payload.get("headers", []) or []
            subject = self._get_header(headers, "Subject")
            sender = self._get_header(headers, "From")
            sent_at = self._get_header(headers, "Date")
            snippet = msg.get("snippet", "") or ""
            body_text = _extract_plain_text(payload)
            message_text = "\n".join([subject, sender, sent_at, snippet, body_text])

            _norm_text = normalize_case_value(message_text)
            _norm_cn = normalize_case_value(case_number)
            _bk2 = re.match(r"^(\d{2})-(\d+)$", (case_number or "").strip())
            _bk2_norm = normalize_case_value(f"{_bk2.group(1)}bk{_bk2.group(2)}") if _bk2 else None
            if _norm_cn not in _norm_text and (not _bk2_norm or _bk2_norm not in _norm_text):
                continue

            pdf_parts = list(self._iter_pdf_parts(payload))
            for index, part in enumerate(pdf_parts, start=1):
                filename = (part.get("filename") or "").strip() or f"courtmail_{message_id}_{index}.pdf"
                is_petition_marker = self._is_petition_attachment(
                    filename=filename,
                    subject=subject,
                    body_text=body_text,
                )
                if not is_petition_marker:
                    continue

                attachment_bytes = self._get_attachment_bytes(gmail_service, message_id, part)
                if not attachment_bytes:
                    continue

                return {
                    "message_id": message_id,
                    "thread_id": msg.get("threadId"),
                    "subject": subject,
                    "from": sender,
                    "date": sent_at,
                    "filename": filename,
                    "bytes": attachment_bytes,
                }

        return None

    async def ingest_specific_message(
        self,
        session_id: str,
        message_id: str,
        case_number: str,
        include_petition: bool = True,
        source: str = "gmail_trigger",
    ) -> dict[str, Any]:
        gmail_service = get_gmail_service()
        return await self._ingest_message_for_trigger(
            gmail_service=gmail_service,
            session_id=session_id,
            case_number=case_number,
            message_id=message_id,
            include_petition=include_petition,
            source=source,
        )

    async def _ingest_message_for_trigger(
        self,
        gmail_service: Any,
        session_id: str,
        case_number: str,
        message_id: str,
        include_petition: bool = True,
        source: str = "gmail_trigger",
    ) -> dict[str, int]:
        # Idempotency: skip messages already fully processed for this session
        ingestion_type_key = f"court_mail_event_{message_id[-18:]}"
        existing = await get_ingestion_status(session_id, ingestion_type_key)
        if existing and existing.get("status") == "completed":
            print(f"[court_mail] Skipping already-processed message {message_id} for session {session_id}")
            return {"scanned": 0, "stored_docs": 0, "petition_events": 0, "schedule_merge_events": 0}

        msg = (
            gmail_service.users()
            .messages()
            .get(userId="me", id=message_id, format="full")
            .execute()
        )

        payload = msg.get("payload", {}) or {}
        headers = payload.get("headers", []) or []
        subject = self._get_header(headers, "Subject")
        sender = self._get_header(headers, "From")
        sent_at = self._get_header(headers, "Date")
        snippet = msg.get("snippet", "") or ""
        email_body = _extract_plain_text(payload)
        message_text = "\n".join([subject, sender, sent_at, snippet, email_body])

        normalized_text = normalize_case_value(message_text)
        normalized_cn = normalize_case_value(case_number)
        # Also accept bk-variant: "26-01938" normalizes to "2601938",
        # but emails often contain "26-bk-01938" which normalizes to "26bk01938".
        _bk_m = re.match(r"^(\d{2})-(\d+)$", (case_number or "").strip())
        bk_normalized = normalize_case_value(f"{_bk_m.group(1)}bk{_bk_m.group(2)}") if _bk_m else None
        if normalized_cn not in normalized_text and (not bk_normalized or bk_normalized not in normalized_text):
            return {"scanned": 0, "stored_docs": 0, "petition_events": 0, "schedule_merge_events": 0}

        # Detect "Initial Schedules Filed:" in subject
        is_initial_schedules = self._is_initial_schedules_subject(subject)
        if is_initial_schedules:
            print(
                f"[court_mail] TRIGGER HIT: 'Initial Schedules Filed' subject detected — "
                f"session={session_id}, case={case_number!r}, subject={subject!r}"
            )

        scanned = 1
        stored_docs = 0
        petition_events = 0
        schedule_merge_events = 0

        pdf_parts = list(self._iter_pdf_parts(payload))
        stored_attachments: list[dict[str, Any]] = []
        schedule_attachments: list[dict[str, Any]] = []
        for index, part in enumerate(pdf_parts, start=1):
            filename = (part.get("filename") or "").strip() or f"courtmail_{message_id}_{index}.pdf"
            attachment_bytes = self._get_attachment_bytes(gmail_service, message_id, part)
            if not attachment_bytes:
                continue

            is_petition = self._is_petition_attachment(filename=filename, subject=subject, body_text=email_body)
            if is_petition and not include_petition:
                continue

            if is_petition:
                document = self.storage_service.store_document(
                    session_id=session_id,
                    case_number=case_number,
                    filename=filename,
                    payload=attachment_bytes,
                    document_type="petition",
                    source=source,
                )
                stored_docs += 1
                stored_attachments.append(
                    {
                        "filename": filename,
                        "document": document,
                        "is_petition": True,
                        "document_type": "petition",
                    }
                )
                petition_events += 1
                await self.petition_service.ingest_petition_attachment(
                    trigger_session_id=session_id,
                    email_metadata={
                        "message_id": message_id,
                        "thread_id": msg.get("threadId"),
                        "subject": subject,
                        "from": sender,
                        "date": sent_at,
                    },
                    attachment_filename=filename,
                    attachment_bytes=attachment_bytes,
                )
            elif is_initial_schedules:
                schedule_attachments.append(
                    {
                        "filename": filename,
                        "bytes": attachment_bytes,
                    }
                )
            else:
                document = self.storage_service.store_document(
                    session_id=session_id,
                    case_number=case_number,
                    filename=filename,
                    payload=attachment_bytes,
                    document_type="court_mail_attachment",
                    source=source,
                )
                stored_docs += 1
                stored_attachments.append(
                    {
                        "filename": filename,
                        "document": document,
                        "is_petition": False,
                        "document_type": "court_mail_attachment",
                    }
                )

        if schedule_attachments:
            schedule_merge_result = await self.schedule_merge_service.merge_initial_schedules(
                target_session_id=session_id,
                case_number=case_number,
                email_metadata={
                    "message_id": message_id,
                    "thread_id": msg.get("threadId"),
                    "subject": subject,
                    "from": sender,
                    "date": sent_at,
                },
                attachments=schedule_attachments,
                source=source,
            )
            stored_schedule_documents = schedule_merge_result.get("stored_documents", [])
            schedule_merge_events += len(stored_schedule_documents)
            stored_docs += len(stored_schedule_documents)
            for attachment, stored_document in zip(
                schedule_attachments,
                stored_schedule_documents,
            ):
                stored_attachments.append(
                    {
                        "filename": attachment.get("filename"),
                        "document": stored_document,
                        "is_petition": False,
                        "document_type": "schedule_filed",
                    }
                )
            print(
                f"[court_mail] Schedule merge completed for session={session_id}, "
                f"case={case_number!r}, attachments={len(stored_schedule_documents)}"
            )

        print(
            f"[court_mail] Message {message_id} processed — "
            f"stored_docs={stored_docs}, petition_events={petition_events}, "
            f"schedule_merge_events={schedule_merge_events}"
        )

        await create_or_update_ingestion(
            session_id=session_id,
            ingestion_type=ingestion_type_key,
            status="completed",
            case_number=case_number,
            collection_name=f"court_mail_events_{session_id}",
            result={
                "message_id": message_id,
                "thread_id": msg.get("threadId"),
                "subject": subject,
                "sender": sender,
                "received_at": sent_at,
                "snippet": snippet,
                "attachments": stored_attachments,
                "attachment_count": len(stored_attachments),
                "petition_events": petition_events,
                "schedule_merge_events": schedule_merge_events,
                "is_initial_schedules": is_initial_schedules,
                "source": source,
            },
        )

        return {
            "scanned": scanned,
            "stored_docs": stored_docs,
            "petition_events": petition_events,
            "schedule_merge_events": schedule_merge_events,
        }

    @staticmethod
    def _build_trigger_query(
        senders: list[str],
        case_number: str,
        after_epoch: int,
        has_attachment: bool = True,
    ) -> str:
        sender_list = [sender.strip() for sender in senders if sender.strip()]
        query_parts: list[str] = []
        if sender_list:
            sender_clause = " OR ".join(f"from:{sender}" for sender in sender_list)
            query_parts.append(f"({sender_clause})")

        # Search both short (26-01938) and full bk-variant (26-bk-01938) formats.
        # Court notification emails use the full format; short format is used internally.
        _m = re.match(r"^(\d{2})-(\d+)$", (case_number or "").strip())
        if _m:
            year, num = _m.groups()
            bk_variant = f"{year}-bk-{num}"
            query_parts.append(f'("{case_number}" OR "{bk_variant}")')
        else:
            query_parts.append(f'"{case_number}"')

        if has_attachment:
            query_parts.append("has:attachment")
        if after_epoch > 0:
            query_parts.append(f"after:{after_epoch}")
        return " ".join(query_parts)

    @staticmethod
    def _is_petition_attachment(filename: str, subject: str, body_text: str = "") -> bool:
        normalized_subject = (subject or "").strip()

        # Align petition detection with the downloader's Gmail filter and avoid
        # classifying motions/orders as petitions just because the email body
        # mentions petition-related text.
        return bool(_VOLUNTARY_PETITION_SUBJECT_RE.search(normalized_subject))

    @staticmethod
    def _is_initial_schedules_subject(subject: str) -> bool:
        """Return True when the email subject matches the Initial Schedules Filed pattern."""
        return is_initial_schedules_subject(subject)

    @staticmethod
    def _list_messages(service: Any, query: str, max_results: int) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        page_token: Optional[str] = None

        while len(messages) < max_results:
            page_size = min(100, max_results - len(messages))
            response = (
                service.users()
                .messages()
                .list(userId="me", q=query, maxResults=page_size, pageToken=page_token)
                .execute()
            )
            messages.extend(response.get("messages", []) or [])
            page_token = response.get("nextPageToken")
            if not page_token:
                break

        return messages[:max_results]

    @staticmethod
    def _get_header(headers: Iterable[dict[str, Any]], name: str) -> str:
        for header in headers:
            if header.get("name", "").lower() == name.lower():
                return header.get("value", "")
        return ""

    def _iter_pdf_parts(self, payload: dict[str, Any]) -> Iterable[dict[str, Any]]:
        for part in payload.get("parts", []) or []:
            mime_type = (part.get("mimeType") or "").lower()
            filename = (part.get("filename") or "").lower()

            if mime_type == "application/pdf" or filename.endswith(".pdf"):
                yield part

            nested_parts = part.get("parts") or []
            if nested_parts:
                yield from self._iter_pdf_parts(part)

    @staticmethod
    def _get_attachment_bytes(service: Any, message_id: str, part: dict[str, Any]) -> bytes:
        body = part.get("body", {}) or {}
        data = body.get("data")
        if data:
            return EmailIngestionService._decode_urlsafe_base64(data)

        attachment_id = body.get("attachmentId")
        if not attachment_id:
            return b""

        response = (
            service.users()
            .messages()
            .attachments()
            .get(userId="me", messageId=message_id, id=attachment_id)
            .execute()
        )
        return EmailIngestionService._decode_urlsafe_base64(response.get("data", ""))

    @staticmethod
    def _decode_urlsafe_base64(value: str) -> bytes:
        if not value:
            return b""
        padding = (-len(value)) % 4
        return base64.urlsafe_b64decode(value + ("=" * padding))
