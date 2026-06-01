"""Gmail OAuth2 client + query/fetch helpers for the v2 ECF inbox.

Ported from `ecf-petition-downloader/src/gmail_client.py`. Token file still
lives on disk (`token.json`, `credentials.json` at the repo root) —
moving these to Postgres/secrets is acknowledged debt for a future PR.

This module is pure I/O — no DB writes, no R2 writes. Used by
`ingest.py` to (a) pull message IDs matching the senders + subject +
lookback filter, (b) hydrate each message's payload, (c) decode the
base64url HTML body.
"""

from __future__ import annotations

import base64
import logging
import os
import time
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

# Court sender → district code. Kept here as a module constant rather than
# config so v2 changes go through code review (sender list is stable; the
# legacy config.yaml was a footgun for typos).
SENDER_TO_COURT: dict[str, str] = {
    "BKECF@flnb.uscourts.gov": "FLNB",
    "FLSB_ECF_Notification@flsb.uscourts.gov": "FLSB",
    "bnc@flmb.uscourts.gov": "FLMB",
    "Courtmail@pawb.uscourts.gov": "PAWB",
}
SUBJECT_FILTER = "Voluntary Petition"

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# Resolve credentials/token files relative to the BE repo root. These paths
# match the legacy locations under `src/gmail/` so the existing OAuth
# bootstrapping (already-authorized token) keeps working.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../.."))
_CREDENTIALS_PATH = os.path.join(_REPO_ROOT, "src", "gmail", "credentials.json")
_TOKEN_PATH = os.path.join(_REPO_ROOT, "src", "gmail", "token.json")


def authenticate():
    """Return an authenticated Gmail API service client.

    Reads `token.json` (refreshing if expired); falls back to a browser
    OAuth flow only on first-run / missing-token. The browser flow can
    NOT run inside a container — first-run auth is done locally and the
    resulting token.json is mounted into the container.

    Logs the resolved account at INFO so ops can confirm which mailbox
    the cron is actually reading. This catches the common "wrong-inbox"
    failure mode where token.json belongs to a different Google account
    than the one receiving ECF notices.
    """
    creds = None
    if os.path.exists(_TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(_TOKEN_PATH, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(_CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(_TOKEN_PATH, "w") as token:
            token.write(creds.to_json())
    service = build("gmail", "v1", credentials=creds)
    try:
        profile = service.users().getProfile(userId="me").execute()
        logger.info(
            "gmail OAuth: authenticated as %s (mailbox has %d total messages)",
            profile.get("emailAddress"), profile.get("messagesTotal", 0),
        )
    except Exception as e:
        logger.warning("gmail OAuth: getProfile failed (auth may still work): %s", e)
    return service


def get_authenticated_email(service) -> Optional[str]:
    """Return the email address bound to the current OAuth token, or None on failure.

    Used by `ingest.py` to derive `firm_id` at runtime from the OAuth account
    (lookup against the users table), avoiding env-var drift between the
    token and `DEFAULT_INTAKE_FIRM_ID`.
    """
    try:
        profile = service.users().getProfile(userId="me").execute()
        return profile.get("emailAddress")
    except Exception as e:
        logger.warning("get_authenticated_email: getProfile failed: %s", e)
        return None


def build_query(
    *,
    senders: list[str],
    subject: str = SUBJECT_FILTER,
    lookback_value: int = 30,
    lookback_unit: str = "minutes",
) -> str:
    """Build a Gmail search query.

    Gmail's `after:` clause takes a Unix timestamp in seconds (not
    RFC date strings). We OR the senders into one query so the API call
    is a single round-trip.
    """
    unit_to_seconds = {"minutes": 60, "hours": 3600, "days": 86400}
    seconds = unit_to_seconds.get(lookback_unit, 60) * lookback_value
    since = int(time.time()) - seconds
    from_parts = " OR ".join(f"from:{s}" for s in senders)
    query = f"({from_parts}) after:{since}"
    if subject:
        query += f' subject:"{subject}"'
    return query


def fetch_emails(service, query: str, max_results: int = 50) -> list:
    """Return a list of `{id, threadId}` dicts. Each id needs a separate
    `get_message` call to hydrate the full payload."""
    results = (
        service.users()
        .messages()
        .list(userId="me", maxResults=max_results, q=query)
        .execute()
    )
    return results.get("messages", [])


def get_message(service, message_id: str) -> dict:
    """Full Gmail message including headers + body parts.

    `format='full'` returns base64url-encoded body bytes — caller decodes
    via `get_email_body`."""
    return (
        service.users()
        .messages()
        .get(userId="me", id=message_id, format="full")
        .execute()
    )


def get_email_body(payload: dict) -> str:
    """Decode the message body. Prefers HTML over plain-text; handles
    both multipart and single-part payloads. Returns "" on failure."""
    body = ""
    if "parts" in payload:
        for part in payload["parts"]:
            if part.get("mimeType") == "text/html" and "data" in part.get("body", {}):
                body = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8")
                break
            if part.get("mimeType") == "text/plain" and not body and "data" in part.get("body", {}):
                body = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8")
    elif "body" in payload and "data" in payload["body"]:
        body = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8")
    return body
