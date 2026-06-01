"""Billing models — Subscription and Invoice — stored in user_db."""

import uuid
import enum
from sqlalchemy import Column, String, DateTime, Integer, Enum, ForeignKey, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..auth.models import Base


class SubscriptionStatus(str, enum.Enum):
    active = "active"
    trialing = "trialing"
    past_due = "past_due"
    canceled = "canceled"
    incomplete = "incomplete"


class InvoiceStatus(str, enum.Enum):
    draft = "draft"
    open = "open"
    paid = "paid"
    void = "void"
    uncollectible = "uncollectible"


class Subscription(Base):
    """Mirrors a Stripe Subscription object. One row per firm."""
    __tablename__ = "subscriptions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    firm_id = Column(String, ForeignKey("firms.id"), nullable=False, index=True)
    stripe_subscription_id = Column(String, unique=True, nullable=False)
    stripe_customer_id = Column(String, nullable=False)
    plan_id = Column(String, ForeignKey("plans.id"), nullable=True)
    status = Column(
        Enum(SubscriptionStatus, name="subscription_status_billing_enum"),
        nullable=False,
        default=SubscriptionStatus.trialing,
    )
    current_period_start = Column(DateTime(timezone=True), nullable=True)
    current_period_end = Column(DateTime(timezone=True), nullable=True)
    canceled_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    firm = relationship("Firm", foreign_keys=[firm_id])
    invoices = relationship("Invoice", back_populates="subscription")


class Invoice(Base):
    """Mirrors a Stripe Invoice object."""
    __tablename__ = "invoices"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    firm_id = Column(String, ForeignKey("firms.id"), nullable=False, index=True)
    subscription_id = Column(String, ForeignKey("subscriptions.id"), nullable=True)
    stripe_invoice_id = Column(String, unique=True, nullable=False)
    amount_cents = Column(Integer, nullable=False, default=0)
    status = Column(
        Enum(InvoiceStatus, name="invoice_status_enum"),
        nullable=False,
        default=InvoiceStatus.draft,
    )
    paid_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    firm = relationship("Firm", foreign_keys=[firm_id])
    subscription = relationship("Subscription", back_populates="invoices")
