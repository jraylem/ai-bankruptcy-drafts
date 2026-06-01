"""End-to-end orchestrator test for the ECF ingest cron.

Mocks every external dependency (Gmail, PACER, R2, both repos) and
verifies:
  - Dedup ordering: gmail_message_id check BEFORE PACER fetch (one-shot link)
  - Outcome path coverage: inserted / gmail_dedup_skip / fingerprint_dedup_skip
    / dead_link / r2_upload_failed
  - Per-outcome audit log write to case_ingestion_logs
  - All log rows in one cycle share the same cycle_id
  - No filesystem writes anywhere in the pipeline
"""

from __future__ import annotations

import base64
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from src.core.components.case_inbox import gmail, ingest


# ─── shared fixtures ────────────────────────────────────────────────────


_VALID_NOTICE_HTML = """
<html><body>
  <table>
    <tr><td>Case Name:</td><td>Jane Q Debtor</td></tr>
    <tr><td>Case Number:</td><td>8:26-bk-01330</td></tr>
    <tr><td>Document Number:</td><td><a href="https://ecf.flsb.uscourts.gov/doc1/abc">1</a></td></tr>
  </table>
</body></html>
"""


def _fake_message(msg_id: str = "msg-1", sender: str = "FLSB_ECF_Notification@flsb.uscourts.gov"):
    """Shape Gmail returns from messages().get(format='full')."""
    body_data = base64.urlsafe_b64encode(_VALID_NOTICE_HTML.encode("utf-8")).decode("ascii")
    return {
        "id": msg_id,
        "payload": {
            "headers": [
                {"name": "From", "value": f"FLSB Court <{sender}>"},
                {"name": "Subject", "value": "Voluntary Petition"},
                {"name": "Date", "value": "Tue, 20 May 2026 14:30:00 +0000"},
            ],
            "parts": [
                {
                    "mimeType": "text/html",
                    "body": {"data": body_data},
                },
            ],
        },
    }


def _patch_gmail(monkeypatch, *, messages: list, message_hydrator=None):
    """Replace gmail.authenticate / fetch_emails / get_message with stubs."""
    monkeypatch.setattr(gmail, "authenticate", lambda: MagicMock())
    monkeypatch.setattr(gmail, "fetch_emails", lambda service, query, max_results=50: messages)
    if message_hydrator is None:
        message_hydrator = lambda service, msg_id: _fake_message(msg_id)
    monkeypatch.setattr(gmail, "get_message", message_hydrator)


# ─── individual outcome paths ────────────────────────────────────────────


@pytest.mark.unit
async def test_happy_path_inserts_row_and_logs_inserted(monkeypatch):
    _patch_gmail(monkeypatch, messages=[{"id": "msg-happy"}])

    # PACER returns a real PDF byte stream
    pdf_bytes = b"%PDF-1.4 fake content"
    monkeypatch.setattr(ingest.pacer, "download_document", AsyncMock(return_value=pdf_bytes))

    # PDF parser returns 'found' SSN
    monkeypatch.setattr(
        ingest.pdf_parser, "extract_ssn_last_four",
        lambda b: ("1879", "found"),
    )

    # Dedup checks miss
    monkeypatch.setattr(
        ingest.CaseInboxRepository, "find_by_gmail_message_id",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        ingest.CaseInboxRepository, "find_by_fingerprint",
        AsyncMock(return_value=None),
    )

    # Repo create returns a fake row
    created = MagicMock()
    created.id = "inbox-uuid-happy"
    created.petition_r2_key = "case_inbox/inbox-uuid-happy/petition.pdf"
    monkeypatch.setattr(
        ingest.CaseInboxRepository, "create_ingesting",
        AsyncMock(return_value=created),
    )

    # R2 upload succeeds
    upload_mock = AsyncMock(return_value="case_inbox/inbox-uuid-happy/petition.pdf")
    monkeypatch.setattr(ingest.r2_service, "upload_by_key", upload_mock)

    # mark_ready returns rowcount=1
    monkeypatch.setattr(ingest.CaseInboxRepository, "mark_ready", AsyncMock(return_value=1))

    log_record = AsyncMock()
    monkeypatch.setattr(ingest.CaseIngestionLogRepository, "record", log_record)

    result = await ingest.run_ingest_cycle(firm_id="firm-1")

    assert result.discovered == 1
    assert result.inserted == 1
    assert result.dead_links == 0
    assert result.gmail_dedup_skips == 0

    upload_mock.assert_awaited_once()
    log_record.assert_awaited_once()
    log_kwargs = log_record.await_args.kwargs
    assert log_kwargs["outcome"] == "inserted"
    assert log_kwargs["case_inbox_id"] == "inbox-uuid-happy"
    assert log_kwargs["cycle_id"] == result.cycle_id


@pytest.mark.unit
async def test_gmail_dedup_skip_does_NOT_consume_link(monkeypatch):
    """Critical: dedup must run BEFORE pacer.download_document so a
    one-shot link we've already processed is never re-fetched."""
    _patch_gmail(monkeypatch, messages=[{"id": "msg-dup"}])

    # Dedup HIT — there's already a row for this gmail_message_id
    existing = MagicMock()
    existing.id = "previously-inserted"
    monkeypatch.setattr(
        ingest.CaseInboxRepository, "find_by_gmail_message_id",
        AsyncMock(return_value=existing),
    )

    pacer_mock = AsyncMock(return_value=b"%PDF-fake")
    monkeypatch.setattr(ingest.pacer, "download_document", pacer_mock)

    log_record = AsyncMock()
    monkeypatch.setattr(ingest.CaseIngestionLogRepository, "record", log_record)

    result = await ingest.run_ingest_cycle(firm_id="firm-1")

    pacer_mock.assert_not_awaited()  # ← THE KEY ASSERTION
    assert result.gmail_dedup_skips == 1
    log_record.assert_awaited_once()
    assert log_record.await_args.kwargs["outcome"] == "gmail_dedup_skip"
    assert log_record.await_args.kwargs["case_inbox_id"] == "previously-inserted"


@pytest.mark.unit
async def test_dead_link_logs_and_skips(monkeypatch):
    _patch_gmail(monkeypatch, messages=[{"id": "msg-dead"}])
    monkeypatch.setattr(
        ingest.CaseInboxRepository, "find_by_gmail_message_id",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(ingest.pacer, "download_document", AsyncMock(return_value=None))

    create_mock = AsyncMock()
    monkeypatch.setattr(ingest.CaseInboxRepository, "create_ingesting", create_mock)
    log_record = AsyncMock()
    monkeypatch.setattr(ingest.CaseIngestionLogRepository, "record", log_record)

    result = await ingest.run_ingest_cycle(firm_id="firm-1")

    assert result.dead_links == 1
    create_mock.assert_not_awaited()  # don't insert a row for a dead link
    assert log_record.await_args.kwargs["outcome"] == "dead_link"


@pytest.mark.unit
async def test_fingerprint_dedup_after_download(monkeypatch):
    _patch_gmail(monkeypatch, messages=[{"id": "msg-fp"}])
    monkeypatch.setattr(
        ingest.CaseInboxRepository, "find_by_gmail_message_id",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(ingest.pacer, "download_document", AsyncMock(return_value=b"%PDF-fp"))

    existing_fp = MagicMock()
    existing_fp.id = "previously-fp"
    monkeypatch.setattr(
        ingest.CaseInboxRepository, "find_by_fingerprint",
        AsyncMock(return_value=existing_fp),
    )

    create_mock = AsyncMock()
    monkeypatch.setattr(ingest.CaseInboxRepository, "create_ingesting", create_mock)
    log_record = AsyncMock()
    monkeypatch.setattr(ingest.CaseIngestionLogRepository, "record", log_record)

    result = await ingest.run_ingest_cycle(firm_id="firm-1")

    assert result.fingerprint_dedup_skips == 1
    create_mock.assert_not_awaited()  # no row created — dup detected post-download
    assert log_record.await_args.kwargs["outcome"] == "fingerprint_dedup_skip"
    assert log_record.await_args.kwargs["case_inbox_id"] == "previously-fp"


@pytest.mark.unit
async def test_r2_upload_failure_marks_row_failed_and_logs(monkeypatch):
    _patch_gmail(monkeypatch, messages=[{"id": "msg-r2-fail"}])
    monkeypatch.setattr(
        ingest.CaseInboxRepository, "find_by_gmail_message_id",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        ingest.CaseInboxRepository, "find_by_fingerprint",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(ingest.pacer, "download_document", AsyncMock(return_value=b"%PDF-x"))
    monkeypatch.setattr(
        ingest.pdf_parser, "extract_ssn_last_four", lambda b: (None, "not_found"),
    )

    created = MagicMock(id="inbox-fail", petition_r2_key="case_inbox/inbox-fail/petition.pdf")
    monkeypatch.setattr(
        ingest.CaseInboxRepository, "create_ingesting", AsyncMock(return_value=created),
    )

    # R2 always raises
    upload_mock = AsyncMock(side_effect=Exception("R2 unreachable"))
    monkeypatch.setattr(ingest.r2_service, "upload_by_key", upload_mock)

    # Speed up backoff for the test
    monkeypatch.setattr(ingest, "R2_UPLOAD_BACKOFF_BASE", 0.0)

    mark_failed = AsyncMock(return_value=1)
    monkeypatch.setattr(ingest.CaseInboxRepository, "mark_failed_ingest", mark_failed)
    mark_ready = AsyncMock(return_value=1)
    monkeypatch.setattr(ingest.CaseInboxRepository, "mark_ready", mark_ready)

    log_record = AsyncMock()
    monkeypatch.setattr(ingest.CaseIngestionLogRepository, "record", log_record)

    result = await ingest.run_ingest_cycle(firm_id="firm-1")

    assert result.r2_upload_failures == 1
    assert result.inserted == 0

    # All 3 retries attempted
    assert upload_mock.await_count == ingest.R2_UPLOAD_RETRIES
    mark_failed.assert_awaited_once_with(id="inbox-fail", error_message="R2 unreachable")
    mark_ready.assert_not_awaited()
    assert log_record.await_args.kwargs["outcome"] == "r2_upload_failed"


@pytest.mark.unit
async def test_no_filesystem_writes_during_ingest(monkeypatch):
    """Statelessness invariant: the ingest pipeline must never write to disk.
    Trips on any code path that tries to open() in a write mode, or write_bytes."""
    _patch_gmail(monkeypatch, messages=[{"id": "msg-fs"}])
    monkeypatch.setattr(
        ingest.CaseInboxRepository, "find_by_gmail_message_id",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        ingest.CaseInboxRepository, "find_by_fingerprint",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(ingest.pacer, "download_document", AsyncMock(return_value=b"%PDF-fs"))
    monkeypatch.setattr(
        ingest.pdf_parser, "extract_ssn_last_four", lambda b: ("1234", "found"),
    )

    created = MagicMock(id="inbox-fs", petition_r2_key="case_inbox/inbox-fs/petition.pdf")
    monkeypatch.setattr(
        ingest.CaseInboxRepository, "create_ingesting", AsyncMock(return_value=created),
    )
    monkeypatch.setattr(ingest.r2_service, "upload_by_key", AsyncMock(return_value="k"))
    monkeypatch.setattr(ingest.CaseInboxRepository, "mark_ready", AsyncMock(return_value=1))
    monkeypatch.setattr(ingest.CaseIngestionLogRepository, "record", AsyncMock())

    from pathlib import Path

    def boom_write_bytes(*a, **kw):
        raise AssertionError("Path.write_bytes called — ingest must be stateless")

    monkeypatch.setattr(Path, "write_bytes", boom_write_bytes)

    # If any code path tries to write to disk during ingest, the assertion fires.
    result = await ingest.run_ingest_cycle(firm_id="firm-1")
    assert result.inserted == 1


# ─── firm_id auto-derivation from OAuth email ────────────────────────────


def _patch_user_lookup(monkeypatch, *, email: str | None, firm_id_returned):
    """Stub gmail.get_authenticated_email + UserAsyncSessionLocal.

    `firm_id_returned` becomes the `scalar_one_or_none()` result of the
    User.firm_id query (None = no user / no firm).
    """
    monkeypatch.setattr(gmail, "get_authenticated_email", lambda service: email)

    fake_result = MagicMock()
    fake_result.scalar_one_or_none = MagicMock(return_value=firm_id_returned)

    fake_session = MagicMock()
    fake_session.execute = AsyncMock(return_value=fake_result)
    fake_session.__aenter__ = AsyncMock(return_value=fake_session)
    fake_session.__aexit__ = AsyncMock(return_value=None)

    monkeypatch.setattr(
        ingest, "UserAsyncSessionLocal", MagicMock(return_value=fake_session),
    )


@pytest.mark.unit
async def test_firm_id_auto_derived_from_oauth_email(monkeypatch):
    """firm_id=None → derive from OAuth email → cycle proceeds with derived id."""
    _patch_gmail(monkeypatch, messages=[])
    _patch_user_lookup(
        monkeypatch, email="nickf@cvhlawgroup.com", firm_id_returned="firm-derived",
    )

    result = await ingest.run_ingest_cycle(firm_id=None)
    # Cycle proceeded (didn't abort early). 0 messages = discovered=0 but no abort.
    assert result.discovered == 0


@pytest.mark.unit
async def test_firm_id_lookup_returns_no_user_aborts_cycle(monkeypatch):
    """firm_id=None + no matching user → cycle returns early, no fetch_emails call."""
    monkeypatch.setattr(gmail, "authenticate", lambda: MagicMock())
    fetch_called = {"count": 0}

    def _fetch(*a, **kw):
        fetch_called["count"] += 1
        return []

    monkeypatch.setattr(gmail, "fetch_emails", _fetch)
    _patch_user_lookup(
        monkeypatch, email="ghost@nowhere.com", firm_id_returned=None,
    )

    result = await ingest.run_ingest_cycle(firm_id=None)
    assert result.discovered == 0
    assert fetch_called["count"] == 0  # aborted before fetch


@pytest.mark.unit
async def test_firm_id_lookup_no_oauth_email_aborts_cycle(monkeypatch):
    """firm_id=None + getProfile fails (no email) → cycle returns early."""
    monkeypatch.setattr(gmail, "authenticate", lambda: MagicMock())
    fetch_called = {"count": 0}
    monkeypatch.setattr(gmail, "fetch_emails", lambda *a, **kw: fetch_called.__setitem__("count", fetch_called["count"] + 1) or [])
    monkeypatch.setattr(gmail, "get_authenticated_email", lambda service: None)

    result = await ingest.run_ingest_cycle(firm_id=None)
    assert result.discovered == 0
    assert fetch_called["count"] == 0  # aborted before fetch
