"""
Email Query Service.

Provides unified interface to search emails from Gmail and CourtDrive sources.
"""

import base64
import logging
import re
from enum import Enum
from typing import Any

from pydantic import BaseModel

from src.gmail.auth import get_gmail_service

logger = logging.getLogger(__name__)


class EmailType(str, Enum):
    """Supported email source types for querying."""
    GMAIL = "gmail"
    COURT_DRIVE = "court_drive"


class Email(BaseModel):
    """
    Email data extracted from Gmail API.

    Attributes:
        id: Gmail message ID (unique identifier).
        subject: Email subject line.
        body: Plain text content of the email body.
        sender: From header (e.g., "John Doe <john@example.com>").
        date: Date header string (e.g., "Mon, 1 Jan 2024 10:00:00 -0500").
    """
    id: str
    subject: str
    body: str
    sender: str | None = None
    date: str | None = None


class EmailSearchResult(BaseModel):
    """
    Result container for email search operations.

    Attributes:
        emails: List of Email objects matching the search query.
        total: Number of emails returned.
        source: The EmailType indicating which source was queried.
    """
    emails: list[Email]
    total: int
    source: EmailType


DEFAULT_COURT_MAIL_SENDERS = [
    "BKECF@flnb.uscourts.gov",
    "FLSB_ECF_Notification@flsb.uscourts.gov",
    "bnc@flmb.uscourts.gov",
    "Courtmail@pawb.uscourts.gov",
]
"""Default list of court ECF notification email addresses used for CourtDrive queries."""


def _decode_base64(data: str) -> str:
    """
    Decode base64 URL-safe encoded data from Gmail API.

    Gmail API returns message body content as URL-safe base64 encoded strings.
    This function handles the decoding with UTF-8 error tolerance.

    Args:
        data: Base64 URL-safe encoded string from Gmail API.

    Returns:
        Decoded UTF-8 string content.
    """
    return base64.urlsafe_b64decode(data.encode("utf-8")).decode("utf-8", errors="ignore")


def _extract_plain_text(payload: dict[str, Any]) -> str:
    """
    Extract plain-text body from Gmail message payload.

    Handles multiple email formats:
    1. Simple messages with body.data directly in payload
    2. Multipart messages with text/plain parts
    3. Nested multipart structures (recursive extraction)
    4. HTML-only emails (strips tags as fallback)

    Args:
        payload: Gmail message payload dict from API response.

    Returns:
        Plain text content of the email body, or empty string if not found.
    """
    body_data = payload.get("body", {}).get("data")
    if body_data:
        return _decode_base64(body_data)

    parts = payload.get("parts", [])
    for part in parts:
        mime_type = part.get("mimeType", "")
        if mime_type == "text/plain":
            part_data = part.get("body", {}).get("data")
            if part_data:
                return _decode_base64(part_data)
        if part.get("parts"):
            nested_text = _extract_plain_text(part)
            if nested_text:
                return nested_text

    for part in parts:
        mime_type = part.get("mimeType", "")
        if mime_type == "text/html":
            part_data = part.get("body", {}).get("data")
            if part_data:
                html_content = _decode_base64(part_data)
                text = re.sub(r"<br\s*/?>", "\n", html_content, flags=re.IGNORECASE)
                text = re.sub(r"<[^>]+>", "", text)
                return text.strip()

    return ""


def _get_header(headers: list[dict], name: str) -> str:
    """
    Get header value by name from Gmail message headers.

    Args:
        headers: List of header dicts from Gmail API (each has 'name' and 'value').
        name: Header name to find (case-insensitive).

    Returns:
        Header value if found, empty string otherwise.
    """
    for header in headers:
        if header.get("name", "").lower() == name.lower():
            return header.get("value", "")
    return ""


def _build_case_number_variants(case_number: str) -> list[str]:
    """
    Generate phrase-quotable variants of a bankruptcy case number.

    Bankruptcy case numbers appear in multiple formats across emails:
      - 'short':        26-10700          (attorney-facing correspondence)
      - 'bk':           26-bk-10700       (court ECF notification subjects)
      - 'chapter-bk':   1:26-bk-10700     (formal federal header)

    Gmail's phrase-quoted search ("26-bk-10700") requires the token sequence
    to appear adjacent in the indexed text, which is fine as long as the
    query's token sequence matches what's actually in the subject/body. A
    court ECF subject like '1:26-bk-10700-PGH Order Setting ...' tokenizes
    to [1, 26, bk, 10700, PGH, ...] and WILL match "26-bk-10700" (adjacent
    3-token run present) but will NOT match "26-10700" (the bk token is
    between the other two).

    So we emit both variants and let the caller OR them together. Mirrors
    the legacy technique at src/gmail/extractor.py:34-43.

    Examples:
        '26-10700'       -> ['26-10700', '26-bk-10700']
        '26-bk-10700'    -> ['26-bk-10700', '26-10700']
        '1:26-bk-10700'  -> ['1:26-bk-10700', '26-bk-10700', '26-10700']
    """
    raw = (case_number or "").strip()
    if not raw:
        return []

    variants: list[str] = [raw]

    chapter_bk = re.fullmatch(r"\d:(\d{2})-bk-(\d{4,7})", raw, flags=re.IGNORECASE)
    if chapter_bk:
        yy, serial = chapter_bk.groups()
        variants.append(f"{yy}-bk-{serial}")
        variants.append(f"{yy}-{serial}")

    bk_only = re.fullmatch(r"(\d{2})-bk-(\d{4,7})", raw, flags=re.IGNORECASE)
    if bk_only:
        yy, serial = bk_only.groups()
        variants.append(f"{yy}-{serial}")

    short_only = re.fullmatch(r"(\d{2})-(\d{4,7})", raw)
    if short_only:
        yy, serial = short_only.groups()
        variants.append(f"{yy}-bk-{serial}")

    seen: set[str] = set()
    deduped: list[str] = []
    for v in variants:
        if v and v not in seen:
            seen.add(v)
            deduped.append(v)
    return deduped


def _case_number_clause(
    case_number: str | None,
    *,
    in_subject: bool = False,
) -> str | None:
    """Build a Gmail OR-clause of phrase-quoted case number variants.

    Returns `("26-10700" OR "26-bk-10700")` or `None` if no case_number was
    provided.

    `in_subject=False` (default) is a full-text clause (not wrapped in
    `subject:`) so it matches the variant anywhere in the indexed
    content — matches the legacy pattern in src/gmail/extractor.py and
    keeps existing callers stable.

    `in_subject=True` wraps the OR-clause in `subject:(…)` so the case
    number must appear in the subject line specifically. Used by the
    `case_emails_search` chat tool, where matching forwarded bodies that
    mention an unrelated case number produces too many false positives —
    court correspondence reliably puts the case number in the subject.
    """
    if not case_number:
        return None
    variants = _build_case_number_variants(case_number)
    if not variants:
        return None
    quoted = [f'"{v}"' for v in variants]
    clause = quoted[0] if len(quoted) == 1 else "(" + " OR ".join(quoted) + ")"
    if in_subject:
        return f"subject:{clause}"
    return clause


def _build_gmail_query(
    subject_query: str | None,
    body_query: str | None,
    case_number: str | None = None,
    case_number_in_subject: bool = False,
) -> str:
    """
    Build Gmail search query string for general inbox search.

    Constructs Gmail query syntax:
      - subject_query -> subject:(query)  (word-AND match within subject,
                         stemming-aware — tolerates token-boundary quirks
                         like 'ClaimCh-13' that break phrase search)
      - body_query    -> "query" (full-text search)
      - case_number   -> by default a full-text OR-clause that matches
                         anywhere; when `case_number_in_subject=True` it
                         is wrapped in `subject:(…)` so the case number
                         must appear in the subject line.
    """
    parts = []
    if subject_query:
        parts.append(f'subject:({subject_query})')
    if body_query:
        parts.append(f'"{body_query}"')
    case_clause = _case_number_clause(case_number, in_subject=case_number_in_subject)
    if case_clause:
        parts.append(case_clause)
    return " ".join(parts) if parts else ""


def _build_court_drive_query(
    subject_query: str | None,
    body_query: str | None,
    case_number: str | None = None,
    case_number_in_subject: bool = False,
) -> str:
    """
    Build Gmail search query for CourtDrive (court ECF notification) emails.

    Filters to the hardcoded DEFAULT_COURT_MAIL_SENDERS plus optional
    subject / body / case_number clauses. The case_number clause emits
    both the short ('26-10700') and bk ('26-bk-10700') phrase-quoted forms
    OR'd together, so the query catches court ECF subjects regardless of
    which format the notification uses. When `case_number_in_subject=True`
    the OR-clause is wrapped in `subject:(…)`.
    """
    sender_clause = " OR ".join(f"from:{sender}" for sender in DEFAULT_COURT_MAIL_SENDERS)
    parts = [f"({sender_clause})"]

    if subject_query:
        parts.append(f'subject:"{subject_query}"')
    if body_query:
        parts.append(f'"{body_query}"')
    case_clause = _case_number_clause(case_number, in_subject=case_number_in_subject)
    if case_clause:
        parts.append(case_clause)

    return " ".join(parts)


class EmailQueryService:
    """
    Internal implementation for Gmail / CourtDrive email search.

    Do NOT import or instantiate this class directly from application code.
    The canonical entry point is `ToolBox.query_email(...)` in
    `src.core.common.toolbox` — going through the toolbox keeps the tool
    surface in one place so cross-cutting concerns (case-number scoping,
    observability, future fallbacks) apply uniformly.

    Uses the Gmail API under the hood for both source types, with
    CourtDrive filtering to specific court ECF notification senders.

    Attributes:
        email_type: The source type (GMAIL or COURT_DRIVE).

    Example (canonical call path):
        from src.core.common.toolbox import ToolBox
        from src.core.common.services.email import EmailType

        result = await ToolBox.query_email(
            email_type=EmailType.GMAIL,
            subject_query="Motion to Extend",
            body_query="case number",
            max_results=5,
        )
        for email in result.emails:
            print(f"{email.subject}: {email.body[:100]}")
    """

    def __init__(self, email_type: EmailType):
        """
        Initialize the email query service.

        Args:
            email_type: The source type to query (GMAIL or COURT_DRIVE).
        """
        self.email_type = email_type
        self._service = None

    def _get_gmail_service(self):
        """
        Get Gmail API service, initializing on first call.

        Caches the service instance to avoid repeated authentication.

        Returns:
            Authenticated Gmail API service object.

        Raises:
            ImportError: If Gmail API libraries are not installed.
            FileNotFoundError: If credentials.json is not found.
        """
        if self._service is None:
            self._service = get_gmail_service()
        return self._service

    async def search(
        self,
        subject_query: str | None = None,
        body_query: str | None = None,
        max_results: int = 10,
        case_number: str | None = None,
        case_number_in_subject: bool = False,
    ) -> EmailSearchResult:
        """
        Search emails by subject, body, and/or case number.

        Routes to the appropriate search method based on email_type.

        Args:
            subject_query: Text to search in email subjects.
            body_query: Text to search in email body content.
            max_results: Maximum number of emails to return (default 10).
            case_number: Bankruptcy case number to match across short and bk
                variants. When provided, appends a phrase-quoted OR clause of
                all variants to the query so subjects like '1:26-bk-10700-PGH'
                and '26-10700 Notice' both match.
            case_number_in_subject: When True, the case-number clause is
                wrapped in `subject:(…)` so it matches only when the case
                number appears in the subject line. Used by the
                `case_emails_search` chat tool to avoid false positives
                from forwarded-body case-number mentions.

        Returns:
            EmailSearchResult containing matching emails and metadata.
        """
        if self.email_type == EmailType.GMAIL:
            return await self._search_gmail(
                subject_query, body_query, max_results, case_number,
                case_number_in_subject,
            )
        elif self.email_type == EmailType.COURT_DRIVE:
            return await self._search_court_drive(
                subject_query, body_query, max_results, case_number,
                case_number_in_subject,
            )

        return EmailSearchResult(emails=[], total=0, source=self.email_type)

    async def _search_gmail(
        self,
        subject_query: str | None,
        body_query: str | None,
        max_results: int = 10,
        case_number: str | None = None,
        case_number_in_subject: bool = False,
    ) -> EmailSearchResult:
        """Search general Gmail inbox for emails matching the query."""
        query = _build_gmail_query(
            subject_query, body_query, case_number, case_number_in_subject,
        )
        if not query:
            return EmailSearchResult(emails=[], total=0, source=EmailType.GMAIL)

        gmail_service = self._get_gmail_service()
        emails = self._execute_search(gmail_service, query, max_results)

        return EmailSearchResult(
            emails=emails,
            total=len(emails),
            source=EmailType.GMAIL
        )

    async def _search_court_drive(
        self,
        subject_query: str | None,
        body_query: str | None,
        max_results: int = 10,
        case_number: str | None = None,
        case_number_in_subject: bool = False,
    ) -> EmailSearchResult:
        """Search CourtDrive emails from court ECF notification senders."""
        query = _build_court_drive_query(
            subject_query, body_query, case_number, case_number_in_subject,
        )

        gmail_service = self._get_gmail_service()
        emails = self._execute_search(gmail_service, query, max_results)

        return EmailSearchResult(
            emails=emails,
            total=len(emails),
            source=EmailType.COURT_DRIVE
        )

    def _execute_search(
        self,
        gmail_service: Any,
        query: str,
        max_results: int
    ) -> list[Email]:
        """
        Execute Gmail API search and extract email content.

        Performs two API calls per message:
        1. messages.list() to get matching message IDs
        2. messages.get() for each ID to fetch full content

        Args:
            gmail_service: Authenticated Gmail API service.
            query: Gmail query string.
            max_results: Maximum number of messages to fetch.

        Returns:
            List of Email objects with extracted content.
            Returns empty list on API errors.
        """
        try:
            response = gmail_service.users().messages().list(
                userId="me",
                q=query,
                maxResults=max_results
            ).execute()

            message_refs = response.get("messages", []) or []
            emails: list[Email] = []

            for msg_ref in message_refs:
                msg_id = msg_ref.get("id")
                if not msg_id:
                    continue

                msg = gmail_service.users().messages().get(
                    userId="me",
                    id=msg_id,
                    format="full"
                ).execute()

                payload = msg.get("payload", {})
                headers = payload.get("headers", [])

                subject = _get_header(headers, "Subject")
                sender = _get_header(headers, "From")
                date = _get_header(headers, "Date")
                body = _extract_plain_text(payload)

                emails.append(Email(
                    id=msg_id,
                    subject=subject,
                    body=body,
                    sender=sender,
                    date=date
                ))

            return emails

        except Exception as e:
            logger.error(f"Gmail search failed: {e}")
            return []
