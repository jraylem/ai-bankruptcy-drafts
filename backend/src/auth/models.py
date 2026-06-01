"""User authentication models."""

from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
import uuid
import enum

Base = declarative_base()


class UserRole(str, enum.Enum):
    firm_owner = "firm_owner"
    admin = "admin"
    member = "member"


class User(Base):
    """Database model for user authentication."""
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    is_active = Column(Boolean, default=True)

    # Email verification
    email_verified = Column(Boolean, nullable=False, default=False)
    email_verification_token = Column(String, nullable=True, unique=True)
    email_verification_expires_at = Column(DateTime(timezone=True), nullable=True)

    # Password reset
    password_reset_token = Column(String, nullable=True, unique=True)
    password_reset_expires_at = Column(DateTime(timezone=True), nullable=True)

    # Paywall / multi-tenancy fields
    firm_id = Column(String, ForeignKey("firms.id"), nullable=True, index=True)
    role = Column(
        Enum(UserRole, name="user_role_enum"),
        nullable=True,
    )
    permissions = Column(JSONB, nullable=True)
    invited_by = Column(String, ForeignKey("users.id"), nullable=True)
    invitation_accepted_at = Column(DateTime(timezone=True), nullable=True)
    stripe_subscription_item_id = Column(String, nullable=True)
    is_accepted = Column(Boolean, nullable=False, default=False)

    # User approval flow — token emailed to admin after email verification
    approval_token = Column(String, nullable=True, unique=True)
    approval_token_expires_at = Column(DateTime(timezone=True), nullable=True)


class RefreshSession(Base):
    """Server-side refresh token record. The raw token is stored only in the
    client HttpOnly cookie; only its SHA-256 hash lives here."""
    __tablename__ = "refresh_sessions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, nullable=False)
    token_hash = Column(String, nullable=False, unique=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)

    __table_args__ = (
        Index("ix_refresh_sessions_user_id", "user_id"),
    )
