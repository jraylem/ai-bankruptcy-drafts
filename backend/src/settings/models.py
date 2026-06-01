"""ORM models for the Settings module — Phase 4.

UserSettings and FirmSettings live in user_db (same Base as auth/models.py).
AuditLog also lives in user_db.
"""

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, JSON, String
from sqlalchemy.sql import func

from ..auth.models import Base


class UserSettings(Base):
    """Per-user UI and notification preferences."""
    __tablename__ = "user_settings"

    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    notification_email = Column(Boolean, nullable=False, default=True)
    notification_inapp = Column(Boolean, nullable=False, default=True)
    theme = Column(String, nullable=False, default="light")
    # Per-event email/in-app notification toggles
    notify_motion_approved = Column(Boolean, nullable=False, default=True)
    notify_motion_rejected = Column(Boolean, nullable=False, default=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class FirmSettings(Base):
    """Per-firm configuration flags."""
    __tablename__ = "firm_settings"

    firm_id = Column(String, ForeignKey("firms.id", ondelete="CASCADE"), primary_key=True)
    allow_member_invites = Column(Boolean, nullable=False, default=False)
    motion_approval_required = Column(Boolean, nullable=False, default=False)
    # Collaboration feature flags
    enable_chat_rooms = Column(Boolean, nullable=False, default=True)
    enable_motion_comments = Column(Boolean, nullable=False, default=True)
    # Billing gate — set False to bypass subscription checks for this firm
    paywall_enabled = Column(Boolean, nullable=False, default=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class AuditLog(Base):
    """Firm-level security and admin event trail.

    Distinct from UserActivityLog (which tracks document generation analytics).
    This table records admin accountability events: members invited/removed,
    settings changed, passwords changed, sessions revoked, billing changes.
    """
    __tablename__ = "audit_logs"

    id = Column(String, primary_key=True)
    firm_id = Column(String, ForeignKey("firms.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action = Column(String, nullable=False)
    resource_type = Column(String, nullable=True)
    resource_id = Column(String, nullable=True)
    event_data = Column("metadata", JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
