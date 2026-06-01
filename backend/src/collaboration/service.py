"""Collaboration service — DB operations for firm chat rooms and motion comments."""

import logging
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select, func as sql_func

from ..auth.database import UserAsyncSessionLocal
from ..auth.models import User
from ..chatbot.database import AsyncSessionLocal
from .models import FirmChatMessage, FirmChatRoom, MotionComment

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# User enrichment helper
# ---------------------------------------------------------------------------

async def fetch_user_map(user_ids: list[str]) -> dict[str, dict]:
    """Return {user_id: {display_name, email}} for a list of IDs from auth DB."""
    if not user_ids:
        return {}
    async with UserAsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.id.in_(user_ids)))
        users = result.scalars().all()
    return {
        u.id: {
            "display_name": f"{u.first_name or ''} {u.last_name or ''}".strip() or u.email,
            "email": u.email,
        }
        for u in users
    }


# ---------------------------------------------------------------------------
# Rooms
# ---------------------------------------------------------------------------

async def list_rooms(firm_id: str) -> list[FirmChatRoom]:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(FirmChatRoom)
            .where(FirmChatRoom.firm_id == firm_id)
            .order_by(FirmChatRoom.created_at.asc())
        )
        return list(result.scalars().all())


async def create_room(
    firm_id: str,
    created_by: str,
    name: str,
    linked_case_number: Optional[str] = None,
    linked_motion_id: Optional[str] = None,
) -> FirmChatRoom:
    async with AsyncSessionLocal() as db:
        room = FirmChatRoom(
            firm_id=firm_id,
            name=name,
            created_by=created_by,
            linked_case_number=linked_case_number,
            linked_motion_id=linked_motion_id,
        )
        db.add(room)
        await db.commit()
        await db.refresh(room)
        return room


async def get_room(room_id: str, firm_id: str) -> FirmChatRoom:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(FirmChatRoom).where(FirmChatRoom.id == room_id)
        )
        room = result.scalar_one_or_none()
        if room is None:
            raise HTTPException(status_code=404, detail="Room not found")
        if room.firm_id != firm_id:
            raise HTTPException(status_code=403, detail="Access denied")
        return room


async def delete_room(
    room_id: str,
    firm_id: str,
    requesting_user_id: str,
    is_admin: bool,
) -> None:
    """Delete a room. Only the creator or an admin/owner can delete."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(FirmChatRoom).where(FirmChatRoom.id == room_id)
        )
        room = result.scalar_one_or_none()
        if room is None:
            raise HTTPException(status_code=404, detail="Room not found")
        if room.firm_id != firm_id:
            raise HTTPException(status_code=403, detail="Access denied")
        if not is_admin and room.created_by != requesting_user_id:
            raise HTTPException(status_code=403, detail="Only the room creator or an admin can delete this room")
        await db.delete(room)
        await db.commit()
        logger.info(f"[collab] room {room_id} deleted by user {requesting_user_id}")


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------

async def list_messages(
    room_id: str,
    firm_id: str,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[FirmChatMessage], int]:
    """Return (messages, total_count) for a room, oldest first."""
    await get_room(room_id, firm_id)
    async with AsyncSessionLocal() as db:
        total_result = await db.execute(
            select(sql_func.count(FirmChatMessage.id))
            .where(FirmChatMessage.room_id == room_id)
        )
        total = total_result.scalar_one()

        result = await db.execute(
            select(FirmChatMessage)
            .where(FirmChatMessage.room_id == room_id)
            .order_by(FirmChatMessage.created_at.asc())
            .limit(limit)
            .offset(offset)
        )
        messages = list(result.scalars().all())
    return messages, total


async def post_message(room_id: str, firm_id: str, user_id: str, content: str) -> FirmChatMessage:
    await get_room(room_id, firm_id)
    async with AsyncSessionLocal() as db:
        msg = FirmChatMessage(
            room_id=room_id,
            user_id=user_id,
            content=content,
        )
        db.add(msg)
        await db.commit()
        await db.refresh(msg)
        logger.info(f"[collab] message posted to room {room_id} by user {user_id}")
        return msg


async def delete_message(
    message_id: str,
    room_id: str,
    firm_id: str,
    requesting_user_id: str,
    is_admin: bool,
) -> None:
    """Delete a message. Users can delete their own; admins can delete any."""
    await get_room(room_id, firm_id)
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(FirmChatMessage).where(FirmChatMessage.id == message_id)
        )
        msg = result.scalar_one_or_none()
        if msg is None:
            raise HTTPException(status_code=404, detail="Message not found")
        if msg.room_id != room_id:
            raise HTTPException(status_code=400, detail="Message does not belong to this room")
        if not is_admin and msg.user_id != requesting_user_id:
            raise HTTPException(status_code=403, detail="Cannot delete another user's message")
        await db.delete(msg)
        await db.commit()
        logger.info(f"[collab] message {message_id} deleted by user {requesting_user_id}")


# ---------------------------------------------------------------------------
# Motion comments
# ---------------------------------------------------------------------------

async def list_comments(motion_id: str) -> list[MotionComment]:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(MotionComment)
            .where(MotionComment.motion_draft_log_id == motion_id)
            .order_by(MotionComment.created_at.asc())
        )
        return list(result.scalars().all())


async def add_comment(motion_id: str, user_id: str, content: str) -> MotionComment:
    async with AsyncSessionLocal() as db:
        comment = MotionComment(
            motion_draft_log_id=motion_id,
            user_id=user_id,
            content=content,
        )
        db.add(comment)
        await db.commit()
        await db.refresh(comment)
        return comment


async def edit_comment(
    comment_id: str,
    requesting_user_id: str,
    content: str,
    is_admin: bool,
) -> MotionComment:
    """Edit a comment. Users can edit their own; admins can edit any."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(MotionComment).where(MotionComment.id == comment_id)
        )
        comment = result.scalar_one_or_none()
        if comment is None:
            raise HTTPException(status_code=404, detail="Comment not found")
        if not is_admin and comment.user_id != requesting_user_id:
            raise HTTPException(status_code=403, detail="Cannot edit another user's comment")
        comment.content = content
        await db.commit()
        await db.refresh(comment)
        logger.info(f"[collab] comment {comment_id} edited by user {requesting_user_id}")
        return comment


async def delete_comment(comment_id: str, requesting_user_id: str, is_admin: bool) -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(MotionComment).where(MotionComment.id == comment_id)
        )
        comment = result.scalar_one_or_none()
        if comment is None:
            raise HTTPException(status_code=404, detail="Comment not found")
        if not is_admin and comment.user_id != requesting_user_id:
            raise HTTPException(status_code=403, detail="Cannot delete another user's comment")
        await db.delete(comment)
        await db.commit()
