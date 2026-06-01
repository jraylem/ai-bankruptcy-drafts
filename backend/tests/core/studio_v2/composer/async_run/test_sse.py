"""Tests for the v2 composer-async SSE handler.

We focus on the AUTH path (token decoding + user lookup) since the
streaming-loop side is exercised in practice through integration. The
auth gate is what gets called per-connect, so it's the most
load-bearing surface to lock down.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from jose import jwt

from src.auth.auth import ALGORITHM, SECRET_KEY
from src.core.studio_v2.composer.async_run import sse


def _make_token(*, sub: str = "user-1", firm_id: str | None = "firm-A") -> str:
    payload: dict[str, object] = {"sub": sub}
    if firm_id is not None:
        payload["firm_id"] = firm_id
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


@pytest.mark.unit
async def test_decode_sse_token_returns_user_for_valid_token():
    token = _make_token()
    fake_user = type("U", (), {"id": "user-1", "firm_id": "firm-A"})()
    with patch.object(sse, "get_user_by_id", new=AsyncMock(return_value=fake_user)):
        u = await sse.decode_sse_token(token)
    assert u.id == "user-1"


@pytest.mark.unit
async def test_decode_sse_token_401_on_missing_firm_id():
    token = _make_token(firm_id=None)
    with pytest.raises(HTTPException) as exc:
        await sse.decode_sse_token(token)
    assert exc.value.status_code == 401


@pytest.mark.unit
async def test_decode_sse_token_401_on_jwt_error():
    with pytest.raises(HTTPException) as exc:
        await sse.decode_sse_token("not-a-jwt")
    assert exc.value.status_code == 401


@pytest.mark.unit
async def test_decode_sse_token_401_when_user_not_found():
    token = _make_token()
    with patch.object(sse, "get_user_by_id", new=AsyncMock(return_value=None)):
        with pytest.raises(HTTPException) as exc:
            await sse.decode_sse_token(token)
    assert exc.value.status_code == 401


@pytest.mark.unit
async def test_stream_events_401_when_no_token():
    """No cookie, no `?token=` query param → 401."""
    class _FakeRequest:
        cookies: dict = {}
        headers: dict = {}
        query_params: dict = {}

        async def is_disconnected(self):
            return True

    with pytest.raises(HTTPException) as exc:
        await sse.stream_events(_FakeRequest(), token=None)
    assert exc.value.status_code == 401
