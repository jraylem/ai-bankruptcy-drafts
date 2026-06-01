"""Phase 2 — accept/dismiss with unfiled-case merge routing.

The accept and dismiss flows share a `_resolve_match_or_create` helper
that re-runs the matcher at action time. These tests cover both call
sites across the routing decision tree:

  Stored hint  | Fresh matcher | accept routes to     | dismiss routes to
  -------------+---------------+----------------------+--------------------
  NULL         | NULL          | create_case_from…    | pure archive
  NULL         | found X       | promote X            | promote X
  X            | NULL          | create_case_from…    | pure archive
  X            | X (firm bad)  | 409 + warning        | 409 + warning
  X            | X (not unfiled)| 409                 | 409
  X            | X (happy)     | promote X            | promote X

The accept path always returns a CaseCreateResponse; the dismiss path
returns one only when a merge happened, otherwise None.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from src.core.components.case_inbox import service


def _row(
    *,
    id: str = "inbox-1",
    firm_id: str = "firm-1",
    status: str = "ready",
    matches_unfiled_case_id: str | None = None,
):
    row = MagicMock()
    row.id = id
    row.firm_id = firm_id
    row.status = status
    row.petition_r2_key = f"case_inbox/{id}/petition.pdf"
    row.case_number = "26-10700"
    row.case_name = "Jane Q Debtor"
    row.ssn_last4 = "1879"
    row.ssn_extraction_status = "found"
    row.court_district = "FLSB"
    row.source = "gmail_ecf"
    row.received_at = datetime(2026, 5, 20, tzinfo=timezone.utc)
    row.created_at = datetime(2026, 5, 20, tzinfo=timezone.utc)
    row.archived_at = None
    row.dismissed_by_user_id = None
    row.matches_unfiled_case_id = matches_unfiled_case_id
    return row


def _unfiled_case(*, id: str = "case-unfiled-1", firm_id: str = "firm-1"):
    """Build an unfiled Case ORM-shaped object."""
    return SimpleNamespace(
        id=id,
        firm_id=firm_id,
        case_name="Jane Q Debtor",
        case_number=None,
        case_number_original=None,
        court_district=None,
        chapter=None,
        petition_pdf_url=None,
        case_file_collection=None,
        gmail_collection=None,
        courtdrive_collection=None,
        legacy_id=None,
        ssn_last4="1879",
        ssn_extraction_status="found",
        status="unfiled",
        created_at=datetime(2026, 5, 10, tzinfo=timezone.utc),
    )


def _filed_case(*, id: str = "case-filed-1", firm_id: str = "firm-1"):
    return SimpleNamespace(
        id=id,
        firm_id=firm_id,
        case_name="Jane Q Debtor",
        case_number="26-10700",
        case_number_original="26-10700",
        court_district="FLSB",
        chapter=7,
        petition_pdf_url="https://r2/cases/26_10700/petition.pdf",
        case_file_collection="case_file_26_10700",
        gmail_collection="gmail_emails_26_10700",
        courtdrive_collection="courtdrive_emails_26_10700",
        legacy_id=None,
        ssn_last4="1879",
        ssn_extraction_status="found",
        status="filed",
        created_at=datetime(2026, 5, 10, tzinfo=timezone.utc),
    )


def _llm_metadata():
    """LLM-extracted metadata for the court-notice PDF."""
    return SimpleNamespace(
        case_number="26-10700",
        case_name="Jane Q Debtor",
        court_district="FLSB",
        chapter=7,
    )


def _patch_merge_path_happy(monkeypatch, *, target_case_id: str = "case-unfiled-1"):
    """Stub every dependency the merge happy-path touches.

    Returns dict of mocks so assertions can verify call shapes."""
    mocks = {
        "find_unfiled_match": AsyncMock(return_value=target_case_id),
        "update_matches": AsyncMock(return_value=1),
        "get_case": AsyncMock(return_value=_unfiled_case(id=target_case_id)),
        "download_pdf": AsyncMock(return_value=b"%PDF-court-notice"),
        "llm_run": AsyncMock(return_value=_llm_metadata()),
        "r2_upload": AsyncMock(),
        "r2_presign": AsyncMock(return_value="https://r2/cases/26_10700/petition.pdf"),
        "r2_delete": AsyncMock(),
        "promote": AsyncMock(return_value=_filed_case(id=target_case_id)),
        "pdf_index": AsyncMock(return_value=42),
        "email_index": AsyncMock(return_value=(3, 5)),
        "mark_accepted": AsyncMock(return_value=1),
        "mark_dismissed": AsyncMock(return_value=1),
    }
    monkeypatch.setattr(service.CaseRepository, "find_unfiled_match", mocks["find_unfiled_match"])
    monkeypatch.setattr(
        service.CaseInboxRepository, "update_matches_unfiled_case_id", mocks["update_matches"],
    )
    monkeypatch.setattr(service.CaseRepository, "get", mocks["get_case"])
    monkeypatch.setattr(service.r2_service, "download_by_key", mocks["download_pdf"])
    monkeypatch.setattr(service.CaseIngestionAgent, "run", mocks["llm_run"])
    monkeypatch.setattr(service.r2_service, "upload_by_key", mocks["r2_upload"])
    monkeypatch.setattr(service.r2_service, "get_presigned_url", mocks["r2_presign"])
    monkeypatch.setattr(service.r2_service, "delete_object", mocks["r2_delete"])
    monkeypatch.setattr(service.CaseRepository, "promote_unfiled", mocks["promote"])
    monkeypatch.setattr(service.PdfIndexer, "index", mocks["pdf_index"])
    monkeypatch.setattr(service.EmailIndexer, "index", mocks["email_index"])
    monkeypatch.setattr(service.CaseInboxRepository, "mark_accepted", mocks["mark_accepted"])
    monkeypatch.setattr(
        service.CaseInboxRepository, "mark_dismissed_to_archive", mocks["mark_dismissed"],
    )
    return mocks


# ─── Accept paths ─────────────────────────────────────────────────────


@pytest.mark.unit
async def test_accept_routes_to_create_when_no_match_found(monkeypatch):
    """matches_unfiled_case_id NULL + fresh matcher NULL → create-new path."""
    row = _row(matches_unfiled_case_id=None)
    monkeypatch.setattr(service.CaseInboxRepository, "get", AsyncMock(return_value=row))
    monkeypatch.setattr(
        service.CaseRepository, "find_unfiled_match", AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        service.CaseInboxRepository, "update_matches_unfiled_case_id",
        AsyncMock(return_value=1),
    )
    monkeypatch.setattr(service.r2_service, "download_by_key", AsyncMock(return_value=b"%PDF"))
    create_mock = AsyncMock(
        return_value=MagicMock(case=MagicMock(id="case-new-uuid")),
    )
    monkeypatch.setattr(service, "create_case_from_petition", create_mock)
    monkeypatch.setattr(service.CaseInboxRepository, "mark_accepted", AsyncMock(return_value=1))
    monkeypatch.setattr(service.r2_service, "delete_object", AsyncMock())

    result = await service.accept(inbox_id="inbox-1", firm_id="firm-1", user_id="u-1")

    create_mock.assert_awaited_once()
    assert result.case.id == "case-new-uuid"


@pytest.mark.unit
async def test_accept_routes_to_promote_when_fresh_match_found(monkeypatch):
    """Stored hint NULL + fresh matcher finds X → merge path triggers."""
    row = _row(matches_unfiled_case_id=None)
    monkeypatch.setattr(service.CaseInboxRepository, "get", AsyncMock(return_value=row))
    mocks = _patch_merge_path_happy(monkeypatch, target_case_id="case-unfiled-1")
    # Ensure create_case_from_petition is NOT called on merge path
    create_mock = AsyncMock()
    monkeypatch.setattr(service, "create_case_from_petition", create_mock)

    result = await service.accept(inbox_id="inbox-1", firm_id="firm-1", user_id="u-1")

    create_mock.assert_not_awaited()
    mocks["promote"].assert_awaited_once()
    mocks["pdf_index"].assert_awaited_once()
    mocks["email_index"].assert_awaited_once()
    # Persisted the fresh match back to the row
    mocks["update_matches"].assert_awaited_once_with(
        id="inbox-1", matches_unfiled_case_id="case-unfiled-1",
    )
    assert result.case.id == "case-unfiled-1"
    assert result.case_file_chunks_indexed == 42
    # mark_accepted uses the merged case id, not a fresh UUID
    mocks["mark_accepted"].assert_awaited_once_with(
        id="inbox-1", case_id="case-unfiled-1", user_id="u-1",
    )


@pytest.mark.unit
async def test_accept_clears_stale_match_when_fresh_matcher_returns_none(monkeypatch):
    """Stored hint X + fresh matcher NULL (target was promoted elsewhere) →
    falls through to create-new; row's matches_unfiled_case_id is cleared."""
    row = _row(matches_unfiled_case_id="case-was-here")
    monkeypatch.setattr(service.CaseInboxRepository, "get", AsyncMock(return_value=row))
    monkeypatch.setattr(
        service.CaseRepository, "find_unfiled_match", AsyncMock(return_value=None),
    )
    update_matches = AsyncMock(return_value=1)
    monkeypatch.setattr(
        service.CaseInboxRepository, "update_matches_unfiled_case_id", update_matches,
    )
    monkeypatch.setattr(service.r2_service, "download_by_key", AsyncMock(return_value=b"%PDF"))
    create_mock = AsyncMock(
        return_value=MagicMock(case=MagicMock(id="case-new-uuid")),
    )
    monkeypatch.setattr(service, "create_case_from_petition", create_mock)
    monkeypatch.setattr(service.CaseInboxRepository, "mark_accepted", AsyncMock(return_value=1))
    monkeypatch.setattr(service.r2_service, "delete_object", AsyncMock())

    await service.accept(inbox_id="inbox-1", firm_id="firm-1", user_id="u-1")

    # Stale hint was cleared
    update_matches.assert_awaited_once_with(id="inbox-1", matches_unfiled_case_id=None)
    create_mock.assert_awaited_once()


@pytest.mark.unit
async def test_accept_409_on_cross_firm_target(monkeypatch, caplog):
    """Defensive guard: matcher found target belonging to another firm.

    Synthetic state — the matcher's WHERE firm_id = :firm would prevent
    this naturally, but the guard exists for refactor-resistance."""
    caplog.set_level(logging.WARNING)
    row = _row(firm_id="firm-1", matches_unfiled_case_id="case-foreign")
    monkeypatch.setattr(service.CaseInboxRepository, "get", AsyncMock(return_value=row))
    monkeypatch.setattr(
        service.CaseRepository, "find_unfiled_match",
        AsyncMock(return_value="case-foreign"),
    )
    monkeypatch.setattr(
        service.CaseInboxRepository, "update_matches_unfiled_case_id",
        AsyncMock(return_value=1),
    )
    monkeypatch.setattr(
        service.CaseRepository, "get",
        AsyncMock(return_value=_unfiled_case(id="case-foreign", firm_id="firm-OTHER")),
    )

    with pytest.raises(HTTPException) as exc:
        await service.accept(inbox_id="inbox-1", firm_id="firm-1", user_id="u-1")
    assert exc.value.status_code == 409
    assert any("Cross-firm match" in r.message for r in caplog.records)


@pytest.mark.unit
async def test_accept_409_when_target_already_filed(monkeypatch):
    """Stale-status race: target was promoted via parallel path AFTER the
    fresh matcher saw it. Returns 409, no warning needed (benign race)."""
    row = _row(matches_unfiled_case_id="case-1")
    monkeypatch.setattr(service.CaseInboxRepository, "get", AsyncMock(return_value=row))
    monkeypatch.setattr(
        service.CaseRepository, "find_unfiled_match", AsyncMock(return_value="case-1"),
    )
    monkeypatch.setattr(
        service.CaseInboxRepository, "update_matches_unfiled_case_id",
        AsyncMock(return_value=1),
    )
    monkeypatch.setattr(
        service.CaseRepository, "get",
        AsyncMock(return_value=_filed_case(id="case-1")),  # status='filed'
    )

    with pytest.raises(HTTPException) as exc:
        await service.accept(inbox_id="inbox-1", firm_id="firm-1", user_id="u-1")
    assert exc.value.status_code == 409


@pytest.mark.unit
async def test_accept_merge_uploads_pdf_to_new_resource_path(monkeypatch):
    """The court-notice PDF must land at cases/<sanitized>/petition.pdf —
    NOT at the old cases/<uuid>/petition.pdf where the unfiled draft lived."""
    row = _row(matches_unfiled_case_id="case-unfiled-1")
    monkeypatch.setattr(service.CaseInboxRepository, "get", AsyncMock(return_value=row))
    mocks = _patch_merge_path_happy(monkeypatch, target_case_id="case-unfiled-1")

    await service.accept(inbox_id="inbox-1", firm_id="firm-1", user_id="u-1")

    mocks["r2_upload"].assert_awaited_once()
    upload_call = mocks["r2_upload"].await_args
    # New R2 key uses the sanitized case_number (26_10700), not the UUID
    assert upload_call.kwargs["key"] == "cases/26_10700/petition.pdf"


# ─── Dismiss paths ────────────────────────────────────────────────────


@pytest.mark.unit
async def test_dismiss_routes_to_pure_archive_when_no_match(monkeypatch):
    """No matcher signal → existing pure-archive behavior, no case touch."""
    row = _row(matches_unfiled_case_id=None)
    monkeypatch.setattr(service.CaseInboxRepository, "get", AsyncMock(return_value=row))
    monkeypatch.setattr(
        service.CaseRepository, "find_unfiled_match", AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        service.CaseInboxRepository, "update_matches_unfiled_case_id",
        AsyncMock(return_value=1),
    )
    mark = AsyncMock(return_value=1)
    monkeypatch.setattr(service.CaseInboxRepository, "mark_dismissed_to_archive", mark)
    download = AsyncMock()
    monkeypatch.setattr(service.r2_service, "download_by_key", download)
    promote = AsyncMock()
    monkeypatch.setattr(service.CaseRepository, "promote_unfiled", promote)

    result = await service.dismiss(inbox_id="inbox-1", firm_id="firm-1", user_id="u-1")

    assert result is None
    mark.assert_awaited_once_with(id="inbox-1", user_id="u-1")
    # No download, no promote — dismiss-no-match is purely archival
    download.assert_not_awaited()
    promote.assert_not_awaited()


@pytest.mark.unit
async def test_dismiss_promotes_when_fresh_match_found(monkeypatch):
    """When the matcher finds an unfiled counterpart, dismiss BOTH promotes
    the case AND archives the inbox row."""
    row = _row(matches_unfiled_case_id="case-unfiled-1")
    monkeypatch.setattr(service.CaseInboxRepository, "get", AsyncMock(return_value=row))
    mocks = _patch_merge_path_happy(monkeypatch, target_case_id="case-unfiled-1")

    result = await service.dismiss(inbox_id="inbox-1", firm_id="firm-1", user_id="u-1")

    # Merge happened
    mocks["promote"].assert_awaited_once()
    mocks["pdf_index"].assert_awaited_once()
    # Inbox row was archived, NOT accepted
    mocks["mark_dismissed"].assert_awaited_once_with(id="inbox-1", user_id="u-1")
    mocks["mark_accepted"].assert_not_awaited()
    # Response carries the promoted case for outcome-aware toast
    assert result is not None
    assert result.case.id == "case-unfiled-1"


@pytest.mark.unit
async def test_dismiss_promotes_even_when_stored_hint_was_null(monkeypatch):
    """Stored hint NULL + fresh matcher finds X → still merges. The matcher
    re-run is the authoritative routing decision, not the stored hint."""
    row = _row(matches_unfiled_case_id=None)
    monkeypatch.setattr(service.CaseInboxRepository, "get", AsyncMock(return_value=row))
    mocks = _patch_merge_path_happy(monkeypatch, target_case_id="case-unfiled-new")

    result = await service.dismiss(inbox_id="inbox-1", firm_id="firm-1", user_id="u-1")

    mocks["promote"].assert_awaited_once()
    # Persisted the fresh match back so the row reflects current truth
    mocks["update_matches"].assert_awaited_once_with(
        id="inbox-1", matches_unfiled_case_id="case-unfiled-new",
    )
    assert result is not None


@pytest.mark.unit
async def test_dismiss_409_on_cross_firm_target(monkeypatch, caplog):
    """Same defensive guard as accept — but exercised through the dismiss
    call site to prove the shared helper covers both."""
    caplog.set_level(logging.WARNING)
    row = _row(firm_id="firm-1", matches_unfiled_case_id="case-foreign")
    monkeypatch.setattr(service.CaseInboxRepository, "get", AsyncMock(return_value=row))
    monkeypatch.setattr(
        service.CaseRepository, "find_unfiled_match",
        AsyncMock(return_value="case-foreign"),
    )
    monkeypatch.setattr(
        service.CaseInboxRepository, "update_matches_unfiled_case_id",
        AsyncMock(return_value=1),
    )
    monkeypatch.setattr(
        service.CaseRepository, "get",
        AsyncMock(return_value=_unfiled_case(id="case-foreign", firm_id="firm-OTHER")),
    )

    with pytest.raises(HTTPException) as exc:
        await service.dismiss(inbox_id="inbox-1", firm_id="firm-1", user_id="u-1")
    assert exc.value.status_code == 409
