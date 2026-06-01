"""accept / dismiss / list flows for the v2 ECF inbox service."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from src.core.components.case_inbox import service


def _row(
    *,
    id: str = "inbox-1",
    firm_id: str = "firm-1",
    status: str = "ready",
    petition_r2_key: str = "case_inbox/inbox-1/petition.pdf",
    matches_unfiled_case_id: str | None = None,
):
    """Build a fake CaseInbox ORM row with sensible defaults."""
    row = MagicMock()
    row.id = id
    row.firm_id = firm_id
    row.status = status
    row.petition_r2_key = petition_r2_key
    row.case_number = "8:26-bk-01330"
    row.case_name = "Jane Q Debtor"
    row.ssn_last4 = "1879"
    row.ssn_extraction_status = "found"
    row.court_district = "FLSB"
    row.source = "gmail_ecf"
    row.received_at = datetime(2026, 5, 20, 14, 30, tzinfo=timezone.utc)
    row.created_at = datetime(2026, 5, 20, 14, 35, tzinfo=timezone.utc)
    row.archived_at = None
    row.dismissed_by_user_id = None
    row.matches_unfiled_case_id = matches_unfiled_case_id
    return row


def _patch_matcher_returns_none(monkeypatch):
    """Convenience: stub find_unfiled_match + update_matches_unfiled_case_id
    so accept/dismiss tests that don't care about the merge path can
    exercise the create-new path without hitting the real DB session."""
    monkeypatch.setattr(
        service.CaseRepository, "find_unfiled_match",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        service.CaseInboxRepository, "update_matches_unfiled_case_id",
        AsyncMock(return_value=1),
    )


# ─── accept (Accept + Summon are the same path) ────────────────────────────


@pytest.mark.unit
async def test_accept_happy_path_delegates_to_create_case_from_petition(monkeypatch):
    row = _row(status="ready")
    monkeypatch.setattr(
        service.CaseInboxRepository, "get", AsyncMock(return_value=row),
    )
    _patch_matcher_returns_none(monkeypatch)

    monkeypatch.setattr(
        service.r2_service, "download_by_key", AsyncMock(return_value=b"%PDF-bytes"),
    )

    fake_case = MagicMock()
    fake_case.id = "case-new-uuid"
    fake_response = MagicMock(case=fake_case)
    create_mock = AsyncMock(return_value=fake_response)
    monkeypatch.setattr(service, "create_case_from_petition", create_mock)

    mark_accept = AsyncMock(return_value=1)
    monkeypatch.setattr(service.CaseInboxRepository, "mark_accepted", mark_accept)
    delete_mock = AsyncMock()
    monkeypatch.setattr(service.r2_service, "delete_object", delete_mock)

    result = await service.accept(
        inbox_id="inbox-1", firm_id="firm-1", user_id="user-1",
    )

    assert result is fake_response
    create_mock.assert_awaited_once()
    # Atomic claim uses the new case_id from create_case_from_petition
    mark_accept.assert_awaited_once_with(
        id="inbox-1", case_id="case-new-uuid", user_id="user-1",
    )
    # Inbox R2 key is cleaned up after the cases/ copy exists
    delete_mock.assert_awaited_once_with(key="case_inbox/inbox-1/petition.pdf")


@pytest.mark.unit
async def test_accept_summon_works_on_archived_row(monkeypatch):
    """The same /accept endpoint handles archived rows (the FE labels the button 'Summon')."""
    row = _row(status="archived")
    monkeypatch.setattr(
        service.CaseInboxRepository, "get", AsyncMock(return_value=row),
    )
    _patch_matcher_returns_none(monkeypatch)
    monkeypatch.setattr(
        service.r2_service, "download_by_key", AsyncMock(return_value=b"%PDF-x"),
    )
    monkeypatch.setattr(
        service, "create_case_from_petition",
        AsyncMock(return_value=MagicMock(case=MagicMock(id="case-x"))),
    )
    monkeypatch.setattr(
        service.CaseInboxRepository, "mark_accepted", AsyncMock(return_value=1),
    )
    monkeypatch.setattr(service.r2_service, "delete_object", AsyncMock())

    await service.accept(inbox_id="inbox-1", firm_id="firm-1", user_id="user-1")
    # No exception = summon path works for archived sources


@pytest.mark.unit
async def test_accept_404_when_wrong_firm(monkeypatch):
    row = _row(firm_id="firm-other")
    monkeypatch.setattr(
        service.CaseInboxRepository, "get", AsyncMock(return_value=row),
    )
    with pytest.raises(HTTPException) as exc:
        await service.accept(inbox_id="inbox-1", firm_id="firm-1", user_id="user-1")
    assert exc.value.status_code == 404


@pytest.mark.unit
async def test_accept_409_on_atomic_claim_race(monkeypatch):
    row = _row(status="ready")
    monkeypatch.setattr(
        service.CaseInboxRepository, "get", AsyncMock(return_value=row),
    )
    _patch_matcher_returns_none(monkeypatch)
    monkeypatch.setattr(
        service.r2_service, "download_by_key", AsyncMock(return_value=b"%PDF-bytes"),
    )
    monkeypatch.setattr(
        service, "create_case_from_petition",
        AsyncMock(return_value=MagicMock(case=MagicMock(id="case-1"))),
    )
    # Race lost — another firm member's UPDATE landed first
    monkeypatch.setattr(
        service.CaseInboxRepository, "mark_accepted", AsyncMock(return_value=0),
    )

    with pytest.raises(HTTPException) as exc:
        await service.accept(inbox_id="inbox-1", firm_id="firm-1", user_id="user-1")
    assert exc.value.status_code == 409


@pytest.mark.unit
async def test_accept_409_when_row_already_dismissed(monkeypatch):
    """Pre-flight status check catches statuses other than ready/archived
    before we even hit the LLM."""
    row = _row(status="accepted")
    monkeypatch.setattr(
        service.CaseInboxRepository, "get", AsyncMock(return_value=row),
    )
    create_mock = AsyncMock()
    monkeypatch.setattr(service, "create_case_from_petition", create_mock)

    with pytest.raises(HTTPException) as exc:
        await service.accept(inbox_id="inbox-1", firm_id="firm-1", user_id="user-1")
    assert exc.value.status_code == 409
    create_mock.assert_not_awaited()  # never paid the LLM cost


# ─── dismiss ──────────────────────────────────────────────────────────────


@pytest.mark.unit
async def test_dismiss_soft_deletes_to_archived(monkeypatch):
    row = _row(status="ready")
    monkeypatch.setattr(
        service.CaseInboxRepository, "get", AsyncMock(return_value=row),
    )
    _patch_matcher_returns_none(monkeypatch)
    mark = AsyncMock(return_value=1)
    monkeypatch.setattr(
        service.CaseInboxRepository, "mark_dismissed_to_archive", mark,
    )
    # Importantly: NO r2.delete_object — bytes stay for summon recovery
    delete_mock = AsyncMock()
    monkeypatch.setattr(service.r2_service, "delete_object", delete_mock)

    result = await service.dismiss(inbox_id="inbox-1", firm_id="firm-1", user_id="user-1")

    assert result is None  # pure-archive path returns no case
    mark.assert_awaited_once_with(id="inbox-1", user_id="user-1")
    delete_mock.assert_not_awaited()  # bytes preserved for summon


@pytest.mark.unit
async def test_dismiss_409_when_not_ready(monkeypatch):
    row = _row(status="archived")
    monkeypatch.setattr(
        service.CaseInboxRepository, "get", AsyncMock(return_value=row),
    )
    with pytest.raises(HTTPException) as exc:
        await service.dismiss(inbox_id="inbox-1", firm_id="firm-1", user_id="user-1")
    assert exc.value.status_code == 409


# ─── list ─────────────────────────────────────────────────────────────────


@pytest.mark.unit
async def test_list_ready_returns_presigned_urls(monkeypatch):
    row = _row(status="ready")
    monkeypatch.setattr(
        service.CaseInboxRepository, "list_ready", AsyncMock(return_value=[row]),
    )
    monkeypatch.setattr(
        service.r2_service, "get_presigned_url_by_key",
        AsyncMock(return_value="https://presigned-url/petition.pdf"),
    )

    out = await service.list_ready(firm_id="firm-1")
    assert len(out.entries) == 1
    entry = out.entries[0]
    assert entry.id == "inbox-1"
    assert entry.petition_pdf_url == "https://presigned-url/petition.pdf"
    assert entry.ssn_extraction_status == "found"
    assert entry.ssn_last4 == "1879"


@pytest.mark.unit
async def test_list_archived_passes_search_query_through(monkeypatch):
    row = _row(status="archived")
    list_mock = AsyncMock(return_value=[row])
    monkeypatch.setattr(service.CaseInboxRepository, "list_archived", list_mock)
    monkeypatch.setattr(
        service.r2_service, "get_presigned_url_by_key",
        AsyncMock(return_value="https://x"),
    )

    await service.list_archived(firm_id="firm-1", q="Sampson", limit=10, offset=5)
    list_mock.assert_awaited_once_with(
        firm_id="firm-1", q="Sampson", limit=10, offset=5,
    )
