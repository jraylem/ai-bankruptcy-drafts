"""Collaboration routes — firm chat rooms, messages, SSE streams, and motion comments.

Router prefix: /collab
Registered in main.py as: app.include_router(collab_router, prefix="/api")
Final paths: /api/collab/...
"""

import asyncio
import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..auth.models import User, UserRole
from ..common.dependencies import get_current_firm_user
from . import service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/collab", tags=["collaboration"])

# room_id   -> list of subscriber queues
_room_queues: dict[str, list[asyncio.Queue]] = {}
# motion_id -> list of subscriber queues
_motion_queues: dict[str, list[asyncio.Queue]] = {}


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class RoomResponse(BaseModel):
    id: str
    firm_id: str
    name: str
    linked_case_number: Optional[str]
    linked_motion_id: Optional[str]
    created_by: str
    created_at: str

    @classmethod
    def from_orm(cls, r) -> "RoomResponse":
        return cls(
            id=r.id,
            firm_id=r.firm_id,
            name=r.name,
            linked_case_number=r.linked_case_number,
            linked_motion_id=r.linked_motion_id,
            created_by=r.created_by,
            created_at=r.created_at.isoformat() if r.created_at else "",
        )


class CreateRoomRequest(BaseModel):
    name: str
    linked_case_number: Optional[str] = None
    linked_motion_id: Optional[str] = None


class MessageResponse(BaseModel):
    id: str
    room_id: str
    user_id: str
    sender_name: str
    sender_email: Optional[str]
    content: str
    created_at: str

    @classmethod
    def from_orm(cls, m, user_map: dict) -> "MessageResponse":
        user = user_map.get(m.user_id, {})
        return cls(
            id=m.id,
            room_id=m.room_id,
            user_id=m.user_id,
            sender_name=user.get("display_name", m.user_id),
            sender_email=user.get("email"),
            content=m.content,
            created_at=m.created_at.isoformat() if m.created_at else "",
        )


class MessageListResponse(BaseModel):
    items: list[MessageResponse]
    total: int
    limit: int
    offset: int


class PostMessageRequest(BaseModel):
    content: str


class CommentResponse(BaseModel):
    id: str
    motion_draft_log_id: str
    user_id: str
    sender_name: str
    sender_email: Optional[str]
    content: str
    created_at: str
    updated_at: Optional[str]

    @classmethod
    def from_orm(cls, c, user_map: dict) -> "CommentResponse":
        user = user_map.get(c.user_id, {})
        return cls(
            id=c.id,
            motion_draft_log_id=c.motion_draft_log_id,
            user_id=c.user_id,
            sender_name=user.get("display_name", c.user_id),
            sender_email=user.get("email"),
            content=c.content,
            created_at=c.created_at.isoformat() if c.created_at else "",
            updated_at=c.updated_at.isoformat() if c.updated_at else None,
        )


class AddCommentRequest(BaseModel):
    content: str


class EditCommentRequest(BaseModel):
    content: str


# ---------------------------------------------------------------------------
# SSE helper
# ---------------------------------------------------------------------------

def _make_sse_stream(queue_map: dict, key: str):
    """Return a StreamingResponse for the given queue map and key."""
    queue: asyncio.Queue = asyncio.Queue()
    queue_map.setdefault(key, []).append(queue)

    async def event_generator():
        async def heartbeat():
            try:
                while True:
                    await asyncio.sleep(15)
                    queue.put_nowait({"type": "heartbeat"})
            except asyncio.CancelledError:
                pass

        hb = asyncio.create_task(heartbeat())
        try:
            while True:
                event = await queue.get()
                yield f"data: {json.dumps(event)}\n\n"
        finally:
            hb.cancel()
            try:
                queue_map[key].remove(queue)
                if not queue_map[key]:
                    del queue_map[key]
            except (ValueError, KeyError):
                pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Pragma": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _broadcast(queue_map: dict, key: str, payload: dict) -> None:
    for q in list(queue_map.get(key, [])):
        try:
            q.put_nowait(payload)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Rooms
# ---------------------------------------------------------------------------

@router.get("/rooms", response_model=list[RoomResponse])
async def list_rooms(current_user: User = Depends(get_current_firm_user)):
    """List all chat rooms for the current user's firm."""
    rooms = await service.list_rooms(current_user.firm_id)
    return [RoomResponse.from_orm(r) for r in rooms]


@router.post("/rooms", response_model=RoomResponse, status_code=201)
async def create_room(
    body: CreateRoomRequest,
    current_user: User = Depends(get_current_firm_user),
):
    """Create a new firm chat room."""
    from ..settings.service import get_or_create_firm_settings
    firm_settings = await get_or_create_firm_settings(current_user.firm_id)
    if not firm_settings.enable_chat_rooms:
        raise HTTPException(status_code=403, detail="Chat rooms are disabled for this firm")

    room = await service.create_room(
        firm_id=current_user.firm_id,
        created_by=current_user.id,
        name=body.name,
        linked_case_number=body.linked_case_number,
        linked_motion_id=body.linked_motion_id,
    )
    return RoomResponse.from_orm(room)


@router.delete("/rooms/{room_id}", status_code=204)
async def delete_room(
    room_id: str,
    current_user: User = Depends(get_current_firm_user),
):
    """Delete a room. Creator or admin/owner only."""
    is_admin = current_user.role in (UserRole.firm_owner, UserRole.admin)
    await service.delete_room(
        room_id=room_id,
        firm_id=current_user.firm_id,
        requesting_user_id=current_user.id,
        is_admin=is_admin,
    )


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------

@router.get("/rooms/{room_id}/messages", response_model=MessageListResponse)
async def list_messages(
    room_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_firm_user),
):
    """Paginated message history for a room, enriched with sender info."""
    messages, total = await service.list_messages(
        room_id=room_id,
        firm_id=current_user.firm_id,
        limit=limit,
        offset=offset,
    )
    user_map = await service.fetch_user_map(list({m.user_id for m in messages}))
    return MessageListResponse(
        items=[MessageResponse.from_orm(m, user_map) for m in messages],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/rooms/{room_id}/messages", response_model=MessageResponse, status_code=201)
async def post_message(
    room_id: str,
    body: PostMessageRequest,
    current_user: User = Depends(get_current_firm_user),
):
    """Post a message to a room and broadcast it to all SSE subscribers."""
    if not body.content.strip():
        raise HTTPException(status_code=400, detail="Message content cannot be empty")

    msg = await service.post_message(
        room_id=room_id,
        firm_id=current_user.firm_id,
        user_id=current_user.id,
        content=body.content,
    )
    user_map = await service.fetch_user_map([current_user.id])
    response = MessageResponse.from_orm(msg, user_map)
    _broadcast(_room_queues, room_id, {"type": "message", "data": response.model_dump()})
    return response


@router.delete("/rooms/{room_id}/messages/{message_id}", status_code=204)
async def delete_message(
    room_id: str,
    message_id: str,
    current_user: User = Depends(get_current_firm_user),
):
    """Delete a message. Users delete their own; admins can delete any."""
    is_admin = current_user.role in (UserRole.firm_owner, UserRole.admin)
    await service.delete_message(
        message_id=message_id,
        room_id=room_id,
        firm_id=current_user.firm_id,
        requesting_user_id=current_user.id,
        is_admin=is_admin,
    )
    _broadcast(_room_queues, room_id, {"type": "message_deleted", "data": {"message_id": message_id}})


# ---------------------------------------------------------------------------
# SSE — room stream
# ---------------------------------------------------------------------------

@router.get("/rooms/{room_id}/stream")
async def room_stream(
    room_id: str,
    current_user: User = Depends(get_current_firm_user),
):
    """SSE stream for real-time messages in a chat room.

    Pushes 'message' and 'message_deleted' events.
    A heartbeat is sent every 15 seconds to keep the connection alive.
    """
    await service.get_room(room_id, current_user.firm_id)
    return _make_sse_stream(_room_queues, room_id)


# ---------------------------------------------------------------------------
# Motion comments
# ---------------------------------------------------------------------------

@router.get("/motions/{motion_id}/comments", response_model=list[CommentResponse])
async def list_comments(
    motion_id: str,
    current_user: User = Depends(get_current_firm_user),
):
    """List all comments on a motion, enriched with sender info."""
    comments = await service.list_comments(motion_id)
    user_map = await service.fetch_user_map(list({c.user_id for c in comments}))
    return [CommentResponse.from_orm(c, user_map) for c in comments]


@router.post("/motions/{motion_id}/comments", response_model=CommentResponse, status_code=201)
async def add_comment(
    motion_id: str,
    body: AddCommentRequest,
    current_user: User = Depends(get_current_firm_user),
):
    """Add a comment to a motion and broadcast it to SSE subscribers."""
    from ..settings.service import get_or_create_firm_settings
    firm_settings = await get_or_create_firm_settings(current_user.firm_id)
    if not firm_settings.enable_motion_comments:
        raise HTTPException(status_code=403, detail="Motion comments are disabled for this firm")

    if not body.content.strip():
        raise HTTPException(status_code=400, detail="Comment content cannot be empty")

    comment = await service.add_comment(
        motion_id=motion_id,
        user_id=current_user.id,
        content=body.content,
    )
    user_map = await service.fetch_user_map([current_user.id])
    response = CommentResponse.from_orm(comment, user_map)
    _broadcast(_motion_queues, motion_id, {"type": "comment_added", "data": response.model_dump()})
    return response


@router.patch("/motions/{motion_id}/comments/{comment_id}", response_model=CommentResponse)
async def edit_comment(
    motion_id: str,
    comment_id: str,
    body: EditCommentRequest,
    current_user: User = Depends(get_current_firm_user),
):
    """Edit a comment. Users can edit their own; admins can edit any."""
    if not body.content.strip():
        raise HTTPException(status_code=400, detail="Comment content cannot be empty")

    is_admin = current_user.role in (UserRole.firm_owner, UserRole.admin)
    comment = await service.edit_comment(
        comment_id=comment_id,
        requesting_user_id=current_user.id,
        content=body.content,
        is_admin=is_admin,
    )
    user_map = await service.fetch_user_map([comment.user_id])
    response = CommentResponse.from_orm(comment, user_map)
    _broadcast(_motion_queues, motion_id, {"type": "comment_edited", "data": response.model_dump()})
    return response


@router.delete("/motions/{motion_id}/comments/{comment_id}", status_code=204)
async def delete_comment(
    motion_id: str,
    comment_id: str,
    current_user: User = Depends(get_current_firm_user),
):
    """Delete a comment. Users delete their own; admins can delete any."""
    is_admin = current_user.role in (UserRole.firm_owner, UserRole.admin)
    await service.delete_comment(
        comment_id=comment_id,
        requesting_user_id=current_user.id,
        is_admin=is_admin,
    )
    _broadcast(_motion_queues, motion_id, {"type": "comment_deleted", "data": {"comment_id": comment_id}})


# ---------------------------------------------------------------------------
# SSE — motion comment stream
# ---------------------------------------------------------------------------

@router.get("/motions/{motion_id}/stream")
async def motion_stream(
    motion_id: str,
    current_user: User = Depends(get_current_firm_user),
):
    """SSE stream for real-time comment activity on a motion.

    Pushes 'comment_added', 'comment_edited', and 'comment_deleted' events.
    A heartbeat is sent every 15 seconds to keep the connection alive.
    """
    return _make_sse_stream(_motion_queues, motion_id)
