"""Firm, Plan, and FirmInvitation models — stored in user_db."""

import uuid
from sqlalchemy import (
    Column, String, DateTime, Boolean, Integer, Enum, ForeignKey, Index
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..auth.models import Base
import enum


class SubscriptionStatus(str, enum.Enum):
    active = "active"
    trialing = "trialing"
    past_due = "past_due"
    canceled = "canceled"


class OnboardingStatus(str, enum.Enum):
    pending = "pending"
    completed = "completed"


class UserRole(str, enum.Enum):
    firm_owner = "firm_owner"
    admin = "admin"
    member = "member"


class Plan(Base):
    __tablename__ = "plans"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    stripe_price_id = Column(String, nullable=True)
    price_cents = Column(Integer, nullable=False, default=0)
    features = Column(JSONB, nullable=True)
    is_active = Column(Boolean, default=True)

    firms = relationship("Firm", back_populates="plan")


class Firm(Base):
    __tablename__ = "firms"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    owner_email = Column(String, unique=True, nullable=False)
    stripe_customer_id = Column(String, nullable=True)
    subscription_status = Column(
        Enum(SubscriptionStatus, name="subscription_status_enum"),
        nullable=False,
        default=SubscriptionStatus.trialing,
    )
    plan_id = Column(String, ForeignKey("plans.id"), nullable=True)
    seat_limit = Column(Integer, nullable=False, default=5)
    allowed_domain = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    is_active = Column(Boolean, default=True)
    onboarding_status = Column(
        Enum(OnboardingStatus, name="onboarding_status_enum"),
        nullable=False,
        default=OnboardingStatus.pending,
        server_default="pending",
    )

    # Firm profile fields
    address = Column(String, nullable=True)
    firm_type = Column(String, nullable=True)
    contact_number = Column(String, nullable=True)

    plan = relationship("Plan", back_populates="firms")
    members = relationship("User", foreign_keys="User.firm_id")
    invitations = relationship("FirmInvitation", back_populates="firm")


class FirmInvitation(Base):
    __tablename__ = "firm_invitations"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    firm_id = Column(String, ForeignKey("firms.id"), nullable=False)
    email = Column(String, nullable=False)
    role = Column(
        Enum(UserRole, name="user_role_enum"),
        nullable=False,
        default=UserRole.member,
    )
    permissions = Column(JSONB, nullable=True)
    invited_by = Column(String, ForeignKey("users.id"), nullable=False)
    token = Column(String, unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    expires_at = Column(DateTime(timezone=True), nullable=False)
    accepted_at = Column(DateTime(timezone=True), nullable=True)

    firm = relationship("Firm", back_populates="invitations")


__table_args_indexes__ = [
    Index("idx_firm_invitations_firm_id", FirmInvitation.firm_id),
    Index("idx_firm_invitations_email", FirmInvitation.email),
    Index("idx_firm_invitations_token", FirmInvitation.token),
]
