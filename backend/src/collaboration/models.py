"""Collaboration models — firm chat rooms, messages, and motion comments.

Stored in chat_db alongside sessions and motion_draft_logs.
user_id and firm_id are stored as plain strings (no FK) because
users live in user_db — same cross-DB pattern used everywhere else.
"""

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from ..chatbot.models import Base


class FirmChatRoom(Base):
    __tablename__ = "firm_chat_rooms"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    firm_id = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False)
    linked_case_number = Column(String, nullable=True)
    linked_motion_id = Column(String, ForeignKey("motion_draft_logs.id", ondelete="SET NULL"), nullable=True)
    created_by = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    messages = relationship("FirmChatMessage", back_populates="room", cascade="all, delete-orphan")


class FirmChatMessage(Base):
    __tablename__ = "firm_chat_messages"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    room_id = Column(String, ForeignKey("firm_chat_rooms.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    room = relationship("FirmChatRoom", back_populates="messages")


class MotionComment(Base):
    __tablename__ = "motion_comments"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    motion_draft_log_id = Column(String, ForeignKey("motion_draft_logs.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    motion_draft_log = relationship("MotionDraftLog", back_populates="comments")


__table_args_indexes__ = [
    Index("idx_firm_chat_rooms_firm_id", FirmChatRoom.firm_id),
    Index("idx_firm_chat_messages_room_id", FirmChatMessage.room_id),
    Index("idx_motion_comments_motion_id", MotionComment.motion_draft_log_id),
]
