"""Pydantic request/response schemas for /api/v2/core/chat/*.

These shapes are the contract with the FE — keep field names stable.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class GetOrCreateSessionRequest(BaseModel):
    """Body for POST /chat/sessions/get-or-create — one canonical chat per (user, case)."""
    case_id: str


class SessionResponse(BaseModel):
    """Shape returned for any CaseSession over the wire."""
    id: str
    case_id: str
    user_id: str
    title: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ToolCallSummary(BaseModel):
    """One tool invocation emitted by the assistant on a single turn."""
    id: str
    name: str
    input: dict


class MessageResponse(BaseModel):
    """Shape returned for any CaseSessionMessage over the wire."""
    id: str
    case_session_id: str
    sequence_number: int
    role: str  # "user" | "assistant" | "tool"
    content: str
    thinking: str | None = None
    tool_calls: list[ToolCallSummary] | None = None
    tool_call_id: str | None = None
    created_at: datetime | None = None


class MessagesPageResponse(BaseModel):
    """Paginated transcript reply."""
    messages: list[MessageResponse]
    has_more: bool = False


class GetOrCreateSessionResponse(BaseModel):
    """Combined session-resolve + first-page-of-transcript reply.

    Returned by `POST /chat/sessions/get-or-create`. Bundling the
    transcript into the same response cuts a round trip (used to be
    `get-or-create` then `GET messages`) and lets the BE skip its
    `list_by_session(limit=1)` welcome-seed check — the limit=200
    fetch we already do here covers both questions.
    """
    session: SessionResponse
    messages: list[MessageResponse]
    has_more: bool = False


class SendMessageRequest(BaseModel):
    """Body for POST /chat/sessions/{id}/stream — the user's prompt."""
    user_message: str = Field(min_length=1, max_length=20000)
