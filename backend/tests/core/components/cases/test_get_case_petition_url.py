"""Tests for the GET /core/cases/{case_id}/petition-url service layer."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from src.core.common.storage.database import CaseRepository
from src.core.common.storage.r2 import r2_service
from src.core.components.cases.service import get_case_petition_url


def _legacy_case(legacy_slug: str = "26_10700"):
    """Build a minimal Case-like object that case_resource_key understands.

    Legacy migrated rows have `legacy_id` populated with the pre-UUID
    sanitized slug — that's the value case_resource_key returns and
    therefore what R2 is signed against.
    """
    return SimpleNamespace(
        id="00000000-0000-0000-0000-000000000000",
        legacy_id=legacy_slug,
        case_number="26-10700",
    )


@pytest.mark.unit
async def test_get_case_petition_url_returns_freshly_signed_url(monkeypatch):
    """Happy path: legacy case exists, r2 signs a URL keyed off legacy_id."""
    monkeypatch.setattr(
        CaseRepository,
        "get",
        AsyncMock(return_value=_legacy_case()),
    )
    fake_sign = AsyncMock(return_value="https://r2/cases/26_10700/petition.pdf?X-Amz-…")
    monkeypatch.setattr(r2_service, "get_presigned_url", fake_sign)

    resp = await get_case_petition_url("26_10700")

    assert resp.petition_pdf_url == "https://r2/cases/26_10700/petition.pdf?X-Amz-…"
    fake_sign.assert_awaited_once_with(
        template_id="26_10700",
        filename="petition.pdf",
        prefix="cases",
    )


@pytest.mark.unit
async def test_get_case_petition_url_raises_404_when_case_missing(monkeypatch):
    monkeypatch.setattr(CaseRepository, "get", AsyncMock(return_value=None))
    fake_sign = AsyncMock()
    monkeypatch.setattr(r2_service, "get_presigned_url", fake_sign)

    with pytest.raises(HTTPException) as exc:
        await get_case_petition_url("not_there")

    assert exc.value.status_code == 404
    assert "not_there" in exc.value.detail
    fake_sign.assert_not_awaited()


@pytest.mark.unit
async def test_get_case_petition_url_propagates_r2_failure(monkeypatch):
    """If r2 signing fails, the exception bubbles up — no swallowing."""
    monkeypatch.setattr(CaseRepository, "get", AsyncMock(return_value=_legacy_case()))
    boom = RuntimeError("r2 signing failed")
    monkeypatch.setattr(r2_service, "get_presigned_url", AsyncMock(side_effect=boom))

    with pytest.raises(RuntimeError) as exc:
        await get_case_petition_url("26_10700")

    assert "r2 signing failed" in str(exc.value)
