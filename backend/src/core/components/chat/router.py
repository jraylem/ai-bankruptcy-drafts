"""FastAPI routes for v2 case chat.

`POST /chat/sessions/get-or-create` — resolve or auto-create the canonical
    (user, case) session.
`GET  /chat/sessions/{session_id}/messages` — paginated transcript.
`POST /chat/sessions/{session_id}/stream` — SSE stream of an agent turn.
`DELETE /chat/sessions/{session_id}` — soft-delete (rarely used).

All routes require JWT via `Authorization: Bearer …` and derive `user_id`
from the token; cross-user reads are blocked by ownership checks.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query

from src.auth.auth import get_current_user
from src.auth.models import User
from src.core.common.storage.database import CaseRepository

from . import service
from .schemas import (
    GetOrCreateSessionRequest,
    GetOrCreateSessionResponse,
    MessageResponse,
    MessagesPageResponse,
    SendMessageRequest,
    SessionResponse,
)
from .sse import render_sse_response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["Chat V2"])


@router.post(
    "/sessions/get-or-create",
    response_model=GetOrCreateSessionResponse,
)
async def get_or_create_session(
    req: GetOrCreateSessionRequest,
    user: Annotated[User, Depends(get_current_user)],
) -> GetOrCreateSessionResponse:
    """Resolve the canonical chat session for `(user, case)` and return its
    first page of transcript in one round trip.

    Bundling the transcript here removes the previous follow-up
    `GET /messages` call the FE used to make on every case open and cuts
    a `list_by_session` query on the BE (the welcome-seed check is
    folded into the same fetch).
    """
    return await service.get_or_create_session(user_id=user.id, case_id=req.case_id)


@router.get(
    "/sessions/{session_id}/messages",
    response_model=MessagesPageResponse,
)
async def list_session_messages(
    session_id: Annotated[str, Path()],
    user: Annotated[User, Depends(get_current_user)],
    limit: int = Query(default=50, ge=1, le=500),
    before_sequence: int | None = Query(default=None, ge=1),
) -> MessagesPageResponse:
    """Return ordered transcript for a session. Paginate via `before_sequence` for older pages."""
    await service.load_owned_session(user_id=user.id, session_id=session_id)
    messages: list[MessageResponse] = await service.list_messages(
        session_id=session_id,
        limit=limit,
        before_sequence=before_sequence,
    )
    has_more = len(messages) == limit
    return MessagesPageResponse(messages=messages, has_more=has_more)


@router.post("/sessions/{session_id}/stream")
async def stream_session(
    session_id: Annotated[str, Path()],
    req: SendMessageRequest,
    user: Annotated[User, Depends(get_current_user)],
):
    """Stream an assistant turn over SSE.

    Persists the user message synchronously before streaming; assistant
    message and tool rows are persisted as the stream progresses.
    """
    session = await service.load_owned_session(user_id=user.id, session_id=session_id)
    case = await CaseRepository.get(session.case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")

    events = service.stream_assistant_turn(
        user=user,
        session=session,
        case=case,
        user_message=req.user_message,
    )
    return await render_sse_response(events)


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: Annotated[str, Path()],
    user: Annotated[User, Depends(get_current_user)],
) -> dict:
    """Soft-delete the session — frees the (user, case) slot for a fresh canonical session."""
    await service.load_owned_session(user_id=user.id, session_id=session_id)
    from src.core.common.storage.database import CaseSessionRepository
    await CaseSessionRepository.soft_delete(session_id)
    return {"deleted": True, "session_id": session_id}
