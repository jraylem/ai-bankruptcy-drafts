"""Structural + behavioral tests for the chat router.

Like the reference_data tests, we avoid TestClient and exercise the handler
callables directly with mocked service-layer dependencies — the router is
a thin delegate.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

import src.core.components.chat.router as router_module
from src.core.components.chat.schemas import (
    GetOrCreateSessionRequest,
    SendMessageRequest,
)


def _user():
    return SimpleNamespace(id="user-1", email="user@example.com")


def _session():
    return SimpleNamespace(
        id="sess-1",
        case_id="26_10700",
        user_id="user-1",
        title="Chat",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def _case():
    return SimpleNamespace(
        id="26_10700",
        case_name="In re Doe",
        case_number="26-10700",
        chapter=13,
        court_district="FLSB",
        petition_pdf_url=None,
        case_file_collection="case_file_26_10700",
        gmail_collection="gmail_emails_26_10700",
        courtdrive_collection="courtdrive_emails_26_10700",
    )


@pytest.mark.unit
def test_chat_router_registers_expected_routes():
    registered: set[tuple[str, str]] = set()
    for route in router_module.router.routes:
        for m in getattr(route, "methods", set()) or set():
            registered.add((route.path, m))
    assert ("/chat/sessions/get-or-create", "POST") in registered
    assert ("/chat/sessions/{session_id}/messages", "GET") in registered
    assert ("/chat/sessions/{session_id}/stream", "POST") in registered
    assert ("/chat/sessions/{session_id}", "DELETE") in registered


@pytest.mark.unit
async def test_get_or_create_session_route_delegates_to_service(monkeypatch):
    """Service now returns the combined `{session, messages, has_more}`
    envelope and the route passes it through unchanged."""
    from src.core.components.chat.schemas import GetOrCreateSessionResponse
    fake_response = GetOrCreateSessionResponse(
        session=router_module.service.session_to_response(_session()),
        messages=[],
        has_more=False,
    )
    monkeypatch.setattr(
        "src.core.components.chat.service.get_or_create_session",
        AsyncMock(return_value=fake_response),
    )
    out = await router_module.get_or_create_session(
        GetOrCreateSessionRequest(case_id="26_10700"), _user(),
    )
    assert out.session.id == "sess-1"
    assert out.session.case_id == "26_10700"
    assert out.messages == []
    assert out.has_more is False


@pytest.mark.unit
async def test_list_session_messages_route_returns_paginated_envelope(monkeypatch):
    monkeypatch.setattr(
        "src.core.components.chat.service.load_owned_session",
        AsyncMock(return_value=_session()),
    )
    monkeypatch.setattr(
        "src.core.components.chat.service.list_messages",
        AsyncMock(return_value=[]),
    )
    out = await router_module.list_session_messages(
        session_id="sess-1", user=_user(), limit=50, before_sequence=None,
    )
    assert out.messages == []
    assert out.has_more is False


@pytest.mark.unit
async def test_list_session_messages_has_more_flag_when_full_page(monkeypatch):
    monkeypatch.setattr(
        "src.core.components.chat.service.load_owned_session",
        AsyncMock(return_value=_session()),
    )
    from src.core.components.chat.schemas import MessageResponse
    fake_msgs = [
        MessageResponse(
            id=f"m{i}",
            case_session_id="sess-1",
            sequence_number=i,
            role="user",
            content="x",
        )
        for i in range(50)
    ]
    monkeypatch.setattr(
        "src.core.components.chat.service.list_messages",
        AsyncMock(return_value=fake_msgs),
    )
    out = await router_module.list_session_messages(
        session_id="sess-1", user=_user(), limit=50, before_sequence=None,
    )
    assert out.has_more is True


@pytest.mark.unit
async def test_stream_session_404s_when_case_missing(monkeypatch):
    monkeypatch.setattr(
        "src.core.components.chat.service.load_owned_session",
        AsyncMock(return_value=_session()),
    )
    monkeypatch.setattr(
        "src.core.components.chat.router.CaseRepository.get",
        AsyncMock(return_value=None),
    )
    with pytest.raises(HTTPException) as exc:
        await router_module.stream_session(
            session_id="sess-1",
            req=SendMessageRequest(user_message="hi"),
            user=_user(),
        )
    assert exc.value.status_code == 404


@pytest.mark.unit
async def test_stream_session_returns_streaming_response(monkeypatch):
    """Happy path: load session + case, hand events to render_sse_response, return it."""
    monkeypatch.setattr(
        "src.core.components.chat.service.load_owned_session",
        AsyncMock(return_value=_session()),
    )
    monkeypatch.setattr(
        "src.core.components.chat.router.CaseRepository.get",
        AsyncMock(return_value=_case()),
    )

    async def fake_stream(*, user, session, case, user_message):  # noqa: ARG001
        if False:
            yield  # pragma: no cover - empty generator

    monkeypatch.setattr(
        "src.core.components.chat.service.stream_assistant_turn",
        fake_stream,
    )

    response = await router_module.stream_session(
        session_id="sess-1",
        req=SendMessageRequest(user_message="how many creditors?"),
        user=_user(),
    )
    # StreamingResponse is what render_sse_response returns.
    from fastapi.responses import StreamingResponse
    assert isinstance(response, StreamingResponse)
    assert response.media_type == "text/event-stream"


@pytest.mark.unit
async def test_delete_session_route_soft_deletes(monkeypatch):
    monkeypatch.setattr(
        "src.core.components.chat.service.load_owned_session",
        AsyncMock(return_value=_session()),
    )
    delete_mock = AsyncMock(return_value=True)
    # The router imports CaseSessionRepository inside the function body.
    monkeypatch.setattr(
        "src.core.common.storage.database.CaseSessionRepository.soft_delete",
        delete_mock,
    )
    out = await router_module.delete_session(session_id="sess-1", user=_user())
    assert out == {"deleted": True, "session_id": "sess-1"}
    delete_mock.assert_awaited_once_with("sess-1")
