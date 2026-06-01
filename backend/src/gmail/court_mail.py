"""Court mail Gmail PDF extraction utilities."""

from __future__ import annotations

import base64
import hashlib
import re
from io import BytesIO
from pathlib import Path
from typing import Any, Iterable, Optional

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

from .auth import get_gmail_service
from .extractor import _extract_plain_text

DEFAULT_COURT_MAIL_SENDERS = [
    "BKECF@flnb.uscourts.gov",
    "FLSB_ECF_Notification@flsb.uscourts.gov",
    "bnc@flmb.uscourts.gov",
    "Courtmail@pawb.uscourts.gov",
]

COURT_MAIL_UPLOADS_DIR = Path(__file__).resolve().parent.parent.parent / "uploads" / "court_mail"


def normalize_case_value(value: str) -> str:
    """Normalize case numbers for forgiving comparisons."""
    return "".join(ch.lower() for ch in value if ch.isalnum())


def normalize_client_name(value: str) -> str:
    """Normalize client names for case-insensitive comparisons."""
    return re.sub(r"\s+", " ", value.strip().lower())


def build_court_mail_query(
    senders: Optional[list[str]] = None,
    case_number: Optional[str] = None,
    client_name: Optional[str] = None,
) -> str:
    """Build a Gmail query limited to court-mail senders and PDF-bearing messages."""
    sender_list = [sender.strip() for sender in (senders or DEFAULT_COURT_MAIL_SENDERS) if sender.strip()]
    if not sender_list:
        raise ValueError("At least one sender email is required")

    # only when available so the same helper can support partial matching too.
    sender_clause = " OR ".join(f"from:{sender}" for sender in sender_list)
    query_parts = [f"({sender_clause})", "has:attachment", "filename:pdf"]

    if case_number:
        case_variants = _build_case_query_variants(case_number)
        if case_variants:
            quoted_variants = " OR ".join(f'"{value}"' for value in case_variants)
            query_parts.append(f"({quoted_variants})")
    elif client_name:
        name_tokens = [token for token in re.split(r"\s+", client_name) if token][:4]
        query_parts.extend(f'"{token}"' for token in name_tokens)

    return " ".join(query_parts)


def fetch_court_mail_pdfs_for_session(
    session_id: str,
    case_number: Optional[str] = None,
    client_name: Optional[str] = None,
    senders: Optional[list[str]] = None,
    max_results: int = 50,
) -> dict[str, Any]:
    """Fetch matching court-mail PDFs from Gmail and save them for the session."""
    if not case_number and not client_name:
        raise ValueError("At least one of case_number or client_name is required")

    gmail_service = get_gmail_service()
    sender_list = [sender.strip() for sender in (senders or DEFAULT_COURT_MAIL_SENDERS) if sender.strip()]
    query = build_court_mail_query(sender_list, case_number=case_number, client_name=client_name)
    message_refs = _list_messages(gmail_service, query=query, max_results=max_results)

    output_dir = COURT_MAIL_UPLOADS_DIR / session_id
    output_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    emails_scanned = 0
    matched_messages = 0

    for msg_ref in message_refs:
        message_id = msg_ref.get("id")
        if not message_id:
            continue

        emails_scanned += 1
        msg = (
            gmail_service.users()
            .messages()
            .get(userId="me", id=message_id, format="full")
            .execute()
        )

        payload = msg.get("payload", {}) or {}
        headers = payload.get("headers", []) or []
        subject = _get_header(headers, "Subject")
        sender = _get_header(headers, "From")
        sent_at = _get_header(headers, "Date")
        snippet = msg.get("snippet", "") or ""
        email_body = _extract_plain_text(payload)
        message_text = "\n".join([subject, sender, sent_at, snippet, email_body])
        message_matches = _matches_filters(message_text, case_number=case_number, client_name=client_name)

        pdf_parts = list(_iter_pdf_parts(payload))
        if not pdf_parts:
            continue

        matched_in_message = False

        for index, part in enumerate(pdf_parts, start=1):
            filename = (part.get("filename") or "").strip() or f"courtmail_{message_id}_{index}.pdf"
            attachment_bytes = _get_attachment_bytes(gmail_service, message_id, part)
            if not attachment_bytes:
                continue

            attachment_text = _extract_pdf_text(attachment_bytes)
            searchable_text = "\n".join([message_text, filename, attachment_text])
            attachment_matches = _matches_filters(
                searchable_text,
                case_number=case_number,
                client_name=client_name,
            )

            if not attachment_matches and not (message_matches and not attachment_text.strip()):
                continue

            matched_in_message = True
            safe_name = _build_saved_filename(message_id, index, filename, attachment_bytes)
            saved_path = output_dir / safe_name
            saved_path.write_bytes(attachment_bytes)

            results.append(
                {
                    "message_id": message_id,
                    "thread_id": msg.get("threadId"),
                    "subject": subject,
                    "from": sender,
                    "date": sent_at,
                    "attachment_filename": filename,
                    "saved_filename": safe_name,
                    "saved_path": str(saved_path),
                    "size_bytes": len(attachment_bytes),
                    "case_number": case_number,
                    "client_name": client_name,
                }
            )

        if matched_in_message:
            matched_messages += 1

    return {
        "status": "completed",
        "session_id": session_id,
        "query": query,
        "senders": sender_list,
        "case_number": case_number,
        "client_name": client_name,
        "emails_scanned": emails_scanned,
        "emails_matched": matched_messages,
        "pdfs_saved": len(results),
        "output_dir": str(output_dir),
        "results": results,
    }


def _list_messages(service: Any, query: str, max_results: int) -> list[dict[str, Any]]:
    """List Gmail messages with basic pagination support."""
    messages: list[dict[str, Any]] = []
    page_token: Optional[str] = None

    while len(messages) < max_results:
        page_size = min(100, max_results - len(messages))
        response = (
            service.users()
            .messages()
            .list(
                userId="me",
                q=query,
                maxResults=page_size,
                pageToken=page_token,
            )
            .execute()
        )

        messages.extend(response.get("messages", []) or [])
        page_token = response.get("nextPageToken")
        if not page_token:
            break

    return messages[:max_results]


def _get_header(headers: Iterable[dict[str, Any]], name: str) -> str:
    """Fetch a Gmail header value by name."""
    for header in headers:
        if header.get("name", "").lower() == name.lower():
            return header.get("value", "")
    return ""


def _iter_pdf_parts(payload: dict[str, Any]) -> Iterable[dict[str, Any]]:
    """Yield PDF-bearing parts from a Gmail payload recursively."""
    for part in payload.get("parts", []) or []:
        mime_type = (part.get("mimeType") or "").lower()
        filename = (part.get("filename") or "").lower()

        if mime_type == "application/pdf" or filename.endswith(".pdf"):
            yield part

        # Gmail payloads can nest attachments several levels deep inside multipart sections.
        nested_parts = part.get("parts") or []
        if nested_parts:
            yield from _iter_pdf_parts(part)


def _get_attachment_bytes(service: Any, message_id: str, part: dict[str, Any]) -> bytes:
    """Read PDF attachment bytes from a Gmail message part."""
    body = part.get("body", {}) or {}
    data = body.get("data")
    if data:
        return _decode_urlsafe_base64(data)

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
    return _decode_urlsafe_base64(response.get("data", ""))


def _decode_urlsafe_base64(value: str) -> bytes:
    """Decode Gmail URL-safe base64 content safely."""
    if not value:
        return b""
    padding = (-len(value)) % 4
    return base64.urlsafe_b64decode(value + ("=" * padding))


def _extract_pdf_text(pdf_bytes: bytes) -> str:
    """Extract text from a PDF attachment when possible."""
    if not pdf_bytes or PdfReader is None:
        return ""

    try:
        reader = PdfReader(BytesIO(pdf_bytes))
        pages = []
        for page in reader.pages:
            text = page.extract_text() or ""
            if text:
                pages.append(text)
        return "\n".join(pages)
    except Exception as exc:
        print(f"[warn] Failed to extract attachment PDF text: {exc}")
        return ""


def _matches_filters(
    value: str,
    case_number: Optional[str] = None,
    client_name: Optional[str] = None,
) -> bool:
    """Return True when the searchable text satisfies the provided filters."""
    if not value.strip():
        
        return False

    if case_number:
        normalized_case = normalize_case_value(case_number)
        if normalized_case and normalized_case not in normalize_case_value(value):
            return False
        # If case number matches, don't require strict full-name substring matching.
        return True

    if client_name:
        normalized_value = normalize_client_name(value)
        name_tokens = [token for token in normalize_client_name(client_name).split(" ") if token]
        if name_tokens and not all(token in normalized_value for token in name_tokens[:3]):
            return False

    return True


def _build_case_query_variants(case_number: str) -> list[str]:
    """Build query variants so Gmail search matches common case-number shapes."""
    raw = (case_number or "").strip()
    if not raw:
        return []

    variants: list[str] = [raw]

    # X:YY-bk-ZZZZZ -> YY-ZZZZZ
    match = re.fullmatch(r"\d:([0-9]{2})-bk-([0-9]{5})", raw, flags=re.IGNORECASE)
    if match:
        yy, serial = match.groups()
        variants.append(f"{yy}-{serial}")

    # YY-ZZZZZ(-AAA) -> 0:YY-bk-ZZZZZ
    match = re.fullmatch(r"([0-9]{2})-([0-9]{5})(?:-[A-Za-z]{3})?", raw)
    if match:
        yy, serial = match.groups()
        variants.append(f"{yy}-{serial}")
        variants.append(f"0:{yy}-bk-{serial}")

    # Deduplicate while preserving order.
    seen: set[str] = set()
    deduped: list[str] = []
    for value in variants:
        normalized = value.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(value)
    return deduped


def _build_saved_filename(message_id: str, index: int, filename: str, payload: bytes) -> str:
    """Create a stable, collision-resistant output filename."""
    stem = Path(filename).stem or f"courtmail_{message_id}_{index}"
    safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._") or f"courtmail_{message_id}_{index}"
    digest = hashlib.sha1(payload).hexdigest()[:10]
    return f"{safe_stem}_{message_id}_{index}_{digest}.pdf"
