"""Tests for `list_cases_with_signed_urls` — paginated case list with re-signed petition URLs."""

from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from src.core.common.storage.database import Case, CaseRepository
from src.core.common.storage.r2 import r2_service
from src.core.components.cases.service import list_cases_with_signed_urls


def _make_case(case_id: str, *, has_petition: bool = True) -> Case:
    return Case(
        id=case_id,
        case_name=f"Debtor {case_id}",
        case_number=case_id.replace("_", "-"),
        case_number_original=None,
        court_district="M.D. Fla.",
        chapter=13,
        petition_pdf_url=f"https://r2/cases/{case_id}/petition.pdf?old_sig" if has_petition else None,
        case_file_collection=f"case_file_{case_id}",
        gmail_collection=f"gmail_emails_{case_id}",
        courtdrive_collection=f"courtdrive_emails_{case_id}",
    )


@pytest.mark.unit
async def test_list_paginated_signs_every_url_and_returns_has_more(monkeypatch):
    """Happy path: 3 rows fit in a 2-page limit, every petition URL is re-signed."""
    rows = [_make_case("26_03082"), _make_case("26_03083")]
    monkeypatch.setattr(
        CaseRepository,
        "list_paginated",
        AsyncMock(return_value=(rows, 5)),
    )
    sign_calls: list[dict] = []

    async def fake_sign(**kwargs):
        sign_calls.append(kwargs)
        return f"https://r2/cases/{kwargs['template_id']}/petition.pdf?fresh_sig"

    monkeypatch.setattr(r2_service, "get_presigned_url", AsyncMock(side_effect=fake_sign))

    resp = await list_cases_with_signed_urls(limit=2, offset=0)

    assert resp.total == 5
    assert resp.limit == 2
    assert resp.offset == 0
    assert resp.has_more is True
    assert [c.id for c in resp.cases] == ["26_03082", "26_03083"]
    assert all(c.petition_pdf_url.endswith("fresh_sig") for c in resp.cases)
    assert len(sign_calls) == 2
    assert sign_calls[0] == {"template_id": "26_03082", "filename": "petition.pdf", "prefix": "cases"}


@pytest.mark.unit
async def test_list_paginated_last_page_has_more_false(monkeypatch):
    """The page that exactly hits `total` reports has_more=False."""
    rows = [_make_case("26_03082")]
    monkeypatch.setattr(CaseRepository, "list_paginated", AsyncMock(return_value=(rows, 21)))
    monkeypatch.setattr(r2_service, "get_presigned_url", AsyncMock(return_value="https://r2/signed"))

    resp = await list_cases_with_signed_urls(limit=20, offset=20)

    assert resp.total == 21
    assert resp.has_more is False
    assert len(resp.cases) == 1


@pytest.mark.unit
async def test_list_paginated_skips_signing_when_petition_pdf_url_is_null(monkeypatch):
    """Cases without a stored petition stay None; signing is skipped for them."""
    rows = [_make_case("26_03082", has_petition=False), _make_case("26_03083")]
    monkeypatch.setattr(CaseRepository, "list_paginated", AsyncMock(return_value=(rows, 2)))
    fake_sign = AsyncMock(return_value="https://r2/signed")
    monkeypatch.setattr(r2_service, "get_presigned_url", fake_sign)

    resp = await list_cases_with_signed_urls(limit=20, offset=0)

    assert resp.cases[0].petition_pdf_url is None
    assert resp.cases[1].petition_pdf_url == "https://r2/signed"
    # Only the case that has a petition got signed.
    fake_sign.assert_awaited_once()


@pytest.mark.unit
async def test_list_paginated_swallows_individual_sign_failure(monkeypatch):
    """If r2 signing fails for one case, the others still come back; the
    bad one gets a null URL so the FE can fall back via the per-case
    endpoint."""
    rows = [_make_case("26_03082"), _make_case("26_03083")]
    monkeypatch.setattr(CaseRepository, "list_paginated", AsyncMock(return_value=(rows, 2)))

    async def flaky_sign(**kwargs):
        if kwargs["template_id"] == "26_03082":
            raise RuntimeError("r2 blew up")
        return "https://r2/signed"

    monkeypatch.setattr(r2_service, "get_presigned_url", AsyncMock(side_effect=flaky_sign))

    resp = await list_cases_with_signed_urls(limit=20, offset=0)

    assert resp.cases[0].petition_pdf_url is None
    assert resp.cases[1].petition_pdf_url == "https://r2/signed"


@pytest.mark.unit
@pytest.mark.parametrize("limit, offset", [(0, 0), (-1, 0), (101, 0), (20, -1)])
async def test_list_paginated_rejects_out_of_range_pagination(monkeypatch, limit, offset):
    monkeypatch.setattr(CaseRepository, "list_paginated", AsyncMock())
    with pytest.raises(HTTPException) as exc:
        await list_cases_with_signed_urls(limit=limit, offset=offset)
    assert exc.value.status_code == 400
