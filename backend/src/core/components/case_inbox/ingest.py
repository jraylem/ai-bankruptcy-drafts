"""ECF petition ingest cron orchestrator.

Wires together gmail.py + email_parser.py + pacer.py + pdf_parser.py
into a single in-memory pipeline that:
  1. Queries Gmail for new ECF notices
  2. Per message: extracts case_number/name + court + doc links
  3. Per link: dedups → fetches PACER PDF → fingerprints → uploads to R2
     → INSERTs case_inbox row → marks 'ready'
  4. Writes ONE audit row per attempted link (case_ingestion_logs)

Statelessness invariants:
  - Bytes never touch disk. pdfplumber reads BytesIO, R2 client uploads bytes.
  - No filesystem caches, no temp files.
  - The Gmail OAuth token still lives on disk (acknowledged debt).

One-shot PACER link handling:
  - find_by_gmail_message_id check happens BEFORE pacer.download_document
    so a re-run of the same cron tick doesn't burn a link that's already
    been processed.
  - On R2 upload failure, the row is marked 'failed_ingest' (no recovery
    — the link is dead either way).
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Optional

from sqlalchemy import select

from src.auth.database import UserAsyncSessionLocal
from src.auth.models import User
from src.core.common.storage.database import (
    CaseInboxRepository,
    CaseIngestionLogRepository,
    CaseRepository,
)
from src.core.common.storage.r2 import r2_service

from . import email_parser, gmail, pacer, pdf_parser

logger = logging.getLogger(__name__)

# Defaults can be overridden via env-driven settings in tasks.py.
DEFAULT_LOOKBACK_MINUTES = 30
DEFAULT_MAX_RESULTS = 50
R2_UPLOAD_RETRIES = 3
R2_UPLOAD_BACKOFF_BASE = 0.5  # seconds; doubles each retry


@dataclass
class IngestCycleResult:
    cycle_id: str
    discovered: int = 0
    inserted: int = 0
    gmail_dedup_skips: int = 0
    fingerprint_dedup_skips: int = 0
    dead_links: int = 0
    r2_upload_failures: int = 0
    db_insert_failures: int = 0
    parse_errors: int = 0


async def run_ingest_cycle(
    *,
    firm_id: Optional[str],
    lookback_minutes: int = DEFAULT_LOOKBACK_MINUTES,
    max_results: int = DEFAULT_MAX_RESULTS,
) -> IngestCycleResult:
    """One cron pass. Returns counters + cycle_id."""
    cycle_id = str(uuid.uuid4())
    result = IngestCycleResult(cycle_id=cycle_id)

    try:
        service = gmail.authenticate()
    except Exception as e:
        logger.error("Gmail auth failed; skipping cycle %s: %s", cycle_id, e)
        return result

    if firm_id is None:
        firm_id = await _resolve_firm_id_from_oauth(service, cycle_id=cycle_id)
        if firm_id is None:
            return result

    query = gmail.build_query(
        senders=list(gmail.SENDER_TO_COURT.keys()),
        subject=gmail.SUBJECT_FILTER,
        lookback_value=lookback_minutes,
        lookback_unit="minutes",
    )
    logger.info(
        "ingest cycle %s starting: query=%r lookback=%dmin",
        cycle_id, query, lookback_minutes,
    )
    messages = gmail.fetch_emails(service, query, max_results=max_results)
    result.discovered = len(messages)
    logger.info(
        "ingest cycle %s: gmail returned %d message id(s)",
        cycle_id, result.discovered,
    )

    for message_summary in messages:
        try:
            await _process_message(
                service=service,
                message_summary=message_summary,
                firm_id=firm_id,
                cycle_id=cycle_id,
                result=result,
            )
        except Exception as e:
            # Catch-all parse_error so one bad email doesn't abort the cycle.
            logger.exception("Unhandled error processing gmail message")
            result.parse_errors += 1
            await CaseIngestionLogRepository.record(
                firm_id=firm_id,
                cycle_id=cycle_id,
                gmail_message_id=message_summary.get("id"),
                outcome="parse_error",
                error_message=str(e),
            )

    logger.info(
        "ingest cycle %s done: discovered=%d inserted=%d gmail_dedup=%d "
        "fp_dedup=%d dead_links=%d r2_fail=%d db_fail=%d parse_err=%d",
        cycle_id, result.discovered, result.inserted,
        result.gmail_dedup_skips, result.fingerprint_dedup_skips,
        result.dead_links, result.r2_upload_failures, result.db_insert_failures,
        result.parse_errors,
    )
    return result


async def _process_message(
    *,
    service: Any,
    message_summary: dict,
    firm_id: Optional[str],
    cycle_id: str,
    result: IngestCycleResult,
) -> None:
    """Fetch + parse one Gmail message; dispatch each found link."""
    msg = gmail.get_message(service, message_summary["id"])
    headers = msg.get("payload", {}).get("headers", [])
    from_value = _header(headers, "From")
    subject_value = _header(headers, "Subject")
    sender_email = email_parser.extract_sender_email(from_value)
    court_district = gmail.SENDER_TO_COURT.get(sender_email)
    received_at = _parse_date_header(_header(headers, "Date"))

    logger.info(
        "ingest cycle %s msg=%s from=%r subject=%r",
        cycle_id, message_summary["id"], sender_email, subject_value,
    )
    if court_district is None and sender_email:
        # Email passed the Gmail-query allowlist but our SENDER_TO_COURT
        # mapping doesn't know this sender — likely a forwarded relay
        # rewrote the From header, or a new court that hasn't been added.
        logger.warning(
            "ingest cycle %s msg=%s: sender %r not in SENDER_TO_COURT mapping",
            cycle_id, message_summary["id"], sender_email,
        )

    body = gmail.get_email_body(msg.get("payload", {}))
    case_name = email_parser.extract_case_name(body) or None
    case_number = email_parser.extract_case_number(body) or None
    links = email_parser.extract_ecf_links(body)

    if not links:
        # No actionable petition link in this email.
        await CaseIngestionLogRepository.record(
            firm_id=firm_id,
            cycle_id=cycle_id,
            gmail_message_id=message_summary["id"],
            case_number=case_number,
            case_name=case_name,
            court_district=court_district,
            outcome="parse_error",
            error_message="no document links found in email body",
        )
        result.parse_errors += 1
        return

    for link in links:
        await _process_link(
            link=link,
            gmail_message_id=message_summary["id"],
            case_number=case_number,
            case_name=case_name,
            court_district=court_district,
            received_at=received_at,
            firm_id=firm_id,
            cycle_id=cycle_id,
            result=result,
        )


async def _process_link(
    *,
    link: str,
    gmail_message_id: str,
    case_number: Optional[str],
    case_name: Optional[str],
    court_district: Optional[str],
    received_at: Optional[datetime],
    firm_id: Optional[str],
    cycle_id: str,
    result: IngestCycleResult,
) -> None:
    """Process a single PACER doc link end-to-end."""
    start = time.monotonic()
    base_log_kwargs = {
        "firm_id": firm_id,
        "cycle_id": cycle_id,
        "gmail_message_id": gmail_message_id,
        "case_number": case_number,
        "case_name": case_name,
        "court_district": court_district,
    }

    # ① Gmail-message dedup BEFORE consuming the one-shot link.
    existing = await CaseInboxRepository.find_by_gmail_message_id(
        message_id=gmail_message_id,
    )
    if existing is not None:
        result.gmail_dedup_skips += 1
        await CaseIngestionLogRepository.record(
            **base_log_kwargs,
            outcome="gmail_dedup_skip",
            case_inbox_id=existing.id,
            elapsed_ms=int((time.monotonic() - start) * 1000),
        )
        return

    # ② Download (link is consumed here)
    pdf_bytes = await pacer.download_document(link)
    if pdf_bytes is None:
        result.dead_links += 1
        await CaseIngestionLogRepository.record(
            **base_log_kwargs,
            outcome="dead_link",
            elapsed_ms=int((time.monotonic() - start) * 1000),
        )
        return

    fingerprint = hashlib.sha256(pdf_bytes).hexdigest()

    # ③ Fingerprint dedup (same PDF arriving via different emails).
    if firm_id is not None:
        existing_fp = await CaseInboxRepository.find_by_fingerprint(
            firm_id=firm_id, sha256=fingerprint,
        )
        if existing_fp is not None:
            result.fingerprint_dedup_skips += 1
            await CaseIngestionLogRepository.record(
                **base_log_kwargs,
                outcome="fingerprint_dedup_skip",
                case_inbox_id=existing_fp.id,
                pdf_size_bytes=len(pdf_bytes),
                elapsed_ms=int((time.monotonic() - start) * 1000),
            )
            return

    # ④ Parse SSN from PDF bytes (BytesIO; no temp file).
    ssn_last4, ssn_status = pdf_parser.extract_ssn_last_four(pdf_bytes)

    # ④.5 — Unfiled-petition match probe. Hints the modal at accept/reject
    # time; the action-time matcher re-run is the source of truth for the
    # actual merge routing. Only scans status='unfiled' rows (partial index
    # idx_cases_ssn_match) — same client can legitimately have multiple
    # bankruptcies across years, so filed rows are never matched against.
    matches_unfiled_case_id: Optional[str] = None
    if ssn_last4 is not None and firm_id is not None and case_name:
        try:
            matches_unfiled_case_id = await CaseRepository.find_unfiled_match(
                firm_id=firm_id,
                ssn_last4=ssn_last4,
                case_name=case_name,
            )
        except Exception as e:
            # Matcher failure must not block ingest — the inbox row still
            # gets created, just without the match hint. Paralegal can
            # still Accept/Reject normally.
            logger.warning(
                "Unfiled-match probe failed for firm=%s ssn=%s: %s",
                firm_id, ssn_last4, e,
            )

    # ⑤ INSERT row (status='ingesting').
    try:
        row = await CaseInboxRepository.create_ingesting(
            firm_id=firm_id,
            case_number=case_number,
            case_name=case_name,
            ssn_last4=ssn_last4,
            ssn_extraction_status=ssn_status,
            court_district=court_district,
            gmail_message_id=gmail_message_id,
            fingerprint_sha256=fingerprint,
            received_at=received_at,
            matches_unfiled_case_id=matches_unfiled_case_id,
        )
    except Exception as e:
        result.db_insert_failures += 1
        await CaseIngestionLogRepository.record(
            **base_log_kwargs,
            outcome="db_insert_failed",
            error_message=str(e),
            pdf_size_bytes=len(pdf_bytes),
            elapsed_ms=int((time.monotonic() - start) * 1000),
        )
        return

    # The DB-level partial UNIQUE on gmail_message_id (and on
    # firm_id+fingerprint_sha256) raises IntegrityError if a sibling
    # worker already inserted the same key while this one was downloading
    # the PDF. The repository catches it and returns None; we treat
    # the loss identically to a gmail_dedup_skip so the cron doesn't
    # double-count and counters stay consistent.
    if row is None:
        result.gmail_dedup_skips += 1
        winner = await CaseInboxRepository.find_by_gmail_message_id(
            message_id=gmail_message_id,
        )
        await CaseIngestionLogRepository.record(
            **base_log_kwargs,
            outcome="gmail_dedup_skip",
            case_inbox_id=winner.id if winner else None,
            pdf_size_bytes=len(pdf_bytes),
            elapsed_ms=int((time.monotonic() - start) * 1000),
        )
        return

    # ⑥ R2 upload with retries.
    upload_error: Optional[str] = None
    for attempt in range(R2_UPLOAD_RETRIES):
        try:
            await r2_service.upload_by_key(
                key=row.petition_r2_key,
                file_content=pdf_bytes,
                content_type="application/pdf",
            )
            upload_error = None
            break
        except Exception as e:
            upload_error = str(e)
            if attempt + 1 < R2_UPLOAD_RETRIES:
                backoff = R2_UPLOAD_BACKOFF_BASE * (2 ** attempt)
                logger.warning(
                    "R2 upload attempt %d/%d failed for %s; retrying in %.1fs: %s",
                    attempt + 1, R2_UPLOAD_RETRIES, row.id, backoff, e,
                )
                await asyncio.sleep(backoff)

    if upload_error is not None:
        # Flip row to failed_ingest, log the failure.
        await CaseInboxRepository.mark_failed_ingest(
            id=row.id, error_message=upload_error,
        )
        result.r2_upload_failures += 1
        await CaseIngestionLogRepository.record(
            **base_log_kwargs,
            outcome="r2_upload_failed",
            case_inbox_id=row.id,
            error_message=upload_error,
            pdf_size_bytes=len(pdf_bytes),
            elapsed_ms=int((time.monotonic() - start) * 1000),
        )
        return

    # ⑦ Flip to ready (UI now sees it).
    rowcount = await CaseInboxRepository.mark_ready(id=row.id)
    if rowcount == 0:
        logger.warning(
            "mark_ready returned rowcount=0 for %s — row state changed mid-flight", row.id,
        )
    result.inserted += 1
    await CaseIngestionLogRepository.record(
        **base_log_kwargs,
        outcome="inserted",
        case_inbox_id=row.id,
        pdf_size_bytes=len(pdf_bytes),
        elapsed_ms=int((time.monotonic() - start) * 1000),
    )


async def _resolve_firm_id_from_oauth(
    service: Any, *, cycle_id: str,
) -> Optional[str]:
    """Look up the firm_id of the user whose email matches the OAuth token.

    Returns None (and logs ERROR) on any failure: OAuth has no email,
    no user with that email, or the user has no firm_id. The caller
    treats None as "abort this cycle" — no rows are written.
    """
    email = gmail.get_authenticated_email(service)
    if not email:
        logger.error(
            "cycle %s: cannot derive firm_id — OAuth getProfile returned no email",
            cycle_id,
        )
        return None

    async with UserAsyncSessionLocal() as session:
        result = await session.execute(
            select(User.firm_id).where(User.email == email)
        )
        firm_id = result.scalar_one_or_none()

    if firm_id is None:
        logger.error(
            "cycle %s: no user/firm match for OAuth email %r — aborting cycle. "
            "Ensure a user row exists for this email with firm_id populated.",
            cycle_id, email,
        )
        return None

    logger.info(
        "cycle %s: resolved firm_id=%s from OAuth email %r",
        cycle_id, firm_id, email,
    )
    return firm_id


def _header(headers: list, name: str) -> str:
    """Case-insensitive header lookup. Returns "" on miss."""
    lower = name.lower()
    for h in headers:
        if isinstance(h, dict) and h.get("name", "").lower() == lower:
            return h.get("value", "") or ""
    return ""


def _parse_date_header(raw: str) -> Optional[datetime]:
    """RFC-2822 Gmail `Date:` header → tz-aware datetime; None on parse error."""
    if not raw:
        return None
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None
