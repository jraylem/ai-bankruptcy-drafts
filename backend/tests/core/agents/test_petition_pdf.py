"""Tests for the petition-PDF download helper."""

from unittest.mock import AsyncMock

import httpx
import pytest

from src.core.agents.utils import petition_pdf
from src.core.common.storage import r2 as r2_module


@pytest.mark.unit
async def test_returns_none_for_empty_url():
    assert await petition_pdf.fetch_petition_pdf_bytes(None) is None
    assert await petition_pdf.fetch_petition_pdf_bytes("") is None
    assert await petition_pdf.fetch_petition_pdf_bytes("   ") is None


@pytest.mark.unit
async def test_external_https_url_uses_httpx(monkeypatch):
    """Non-R2 HTTPS URLs are fetched via httpx — no re-sign path needed."""
    captured: dict = {}

    class _FakeResponse:
        content = b"%PDF-1.7 fake"

        def raise_for_status(self):
            return None

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            captured["timeout"] = kwargs.get("timeout")

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url):
            captured["url"] = url
            return _FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)

    result = await petition_pdf.fetch_petition_pdf_bytes(
        "https://example.com/cases/26_10700/petition.pdf"
    )
    assert result == b"%PDF-1.7 fake"
    assert captured["url"].startswith("https://example.com/")


@pytest.mark.unit
async def test_r2_presigned_url_routes_through_resign(monkeypatch):
    """Stale-or-not R2 presigned URLs MUST go through r2_service so boto3
    signs a fresh request — sidesteps URL TTL expiry."""
    captured: dict = {}

    async def fake_download_by_key(key):
        captured["key"] = key
        return b"%PDF-1.7 r2 bytes"

    monkeypatch.setattr(r2_module.r2_service, "bucket_name", "bkdrafts-agt")
    monkeypatch.setattr(r2_module.r2_service, "download_by_key", fake_download_by_key)

    # httpx must NOT be called for R2 URLs — make any attempt explode.
    class _ExplodingClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("httpx should not be used for R2 URLs")

    monkeypatch.setattr(httpx, "AsyncClient", _ExplodingClient)

    presigned = (
        "https://5a0c2d6abd5593ad977857433f279443.r2.cloudflarestorage.com/"
        "bkdrafts-agt/bkdrafts-agt/cases/26_10700/petition.pdf"
        "?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Expires=3600"
    )
    result = await petition_pdf.fetch_petition_pdf_bytes(presigned)
    assert result == b"%PDF-1.7 r2 bytes"
    # Both bucket prefixes stripped iteratively — the actual S3 key is cases/26_10700/petition.pdf.
    assert captured["key"] == "cases/26_10700/petition.pdf"


@pytest.mark.unit
async def test_external_https_url_returns_none_on_error(monkeypatch):
    class _FailingClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url):
            raise httpx.HTTPError("boom")

    monkeypatch.setattr(httpx, "AsyncClient", _FailingClient)

    result = await petition_pdf.fetch_petition_pdf_bytes(
        "https://example.com/cases/26_10700/petition.pdf"
    )
    assert result is None


@pytest.mark.unit
async def test_r2_resign_returns_none_on_error(monkeypatch):
    monkeypatch.setattr(r2_module.r2_service, "bucket_name", "bkdrafts-agt")
    monkeypatch.setattr(
        r2_module.r2_service,
        "download_by_key",
        AsyncMock(side_effect=Exception("R2 down")),
    )
    presigned = (
        "https://abc.r2.cloudflarestorage.com/bkdrafts-agt/cases/26_10700/petition.pdf"
        "?X-Amz-Expires=3600"
    )
    result = await petition_pdf.fetch_petition_pdf_bytes(presigned)
    assert result is None


@pytest.mark.unit
async def test_r2_key_routes_through_r2_service(monkeypatch):
    captured: dict = {}

    async def fake_download(template_id, filename, prefix):
        captured["template_id"] = template_id
        captured["filename"] = filename
        captured["prefix"] = prefix
        return b"%PDF-1.7 r2 bytes"

    monkeypatch.setattr(r2_module.r2_service, "download_file", fake_download)

    result = await petition_pdf.fetch_petition_pdf_bytes(
        "cases/26_10700/petition.pdf"
    )
    assert result == b"%PDF-1.7 r2 bytes"
    assert captured == {"prefix": "cases", "template_id": "26_10700", "filename": "petition.pdf"}


@pytest.mark.unit
async def test_r2_key_with_invalid_shape_returns_none():
    # Need at least prefix/template_id/filename — single-segment key is invalid.
    result = await petition_pdf.fetch_petition_pdf_bytes("petition.pdf")
    assert result is None


@pytest.mark.unit
async def test_r2_download_failure_returns_none(monkeypatch):
    monkeypatch.setattr(
        r2_module.r2_service,
        "download_file",
        AsyncMock(side_effect=Exception("R2 down")),
    )
    result = await petition_pdf.fetch_petition_pdf_bytes(
        "cases/26_10700/petition.pdf"
    )
    assert result is None
