"""Billing API routes — checkout, subscription status, cancel."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth.models import User
from ..common.dependencies import get_current_firm_user
from ..config import settings
from .service import (
    cancel_subscription,
    create_billing_portal_session,
    create_checkout_session,
    get_active_plans,
    get_billing_overview,
    get_cost_drivers,
    get_payment_method,
    get_recent_invoices,
    get_subscription,
    get_usage_breakdown,
    report_usage_event,
    resync_subscription,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/billing", tags=["billing"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class CheckoutRequest(BaseModel):
    success_url: Optional[str] = Field(default=None, example=None)
    cancel_url: Optional[str] = Field(default=None, example=None)


class CheckoutResponse(BaseModel):
    checkout_url: str


class SubscriptionResponse(BaseModel):
    firm_id: str
    stripe_subscription_id: Optional[str]
    stripe_customer_id: Optional[str]
    status: Optional[str]
    current_period_start: Optional[str]
    current_period_end: Optional[str]
    canceled_at: Optional[str]


class PortalResponse(BaseModel):
    portal_url: str


class PlanResponse(BaseModel):
    id: str
    name: str
    stripe_price_id: Optional[str]
    price_cents: int
    features: Optional[dict]
    is_active: bool


class MeterPriceItem(BaseModel):
    key: str
    label: str
    unit_label: str
    price_cents: int


class BillingOverviewResponse(BaseModel):
    plan_name: Optional[str]
    base_price_cents: int
    billing_period: str
    meter_prices: list[MeterPriceItem]
    subscription_status: Optional[str]
    current_period_start: Optional[str]
    current_period_end: Optional[str]
    stripe_customer_id: Optional[str]


class UsageBreakdownItem(BaseModel):
    key: str
    label: str
    unit_label: str
    units_used: int
    rate_cents: int
    current_charge_cents: int
    trend_pct: int


class UsageBreakdownResponse(BaseModel):
    billing_period_start: str
    billing_period_end: str
    mtd_total_cents: int
    projected_cents: int
    items: list[UsageBreakdownItem]


class CostDriverUserItem(BaseModel):
    user_id: str
    label: str
    email: Optional[str]
    role: str
    role_display: str
    total_cents: int


class CostDriverWorkflowItem(BaseModel):
    key: str
    label: str
    total_cents: int


class CostDriversResponse(BaseModel):
    by: str
    items: list


class PaymentMethodResponse(BaseModel):
    has_payment_method: bool
    brand: Optional[str] = None
    last4: Optional[str] = None
    exp_month: Optional[int] = None
    exp_year: Optional[int] = None
    funding: Optional[str] = None


class InvoiceItem(BaseModel):
    stripe_invoice_id: str
    invoice_number: str
    amount_cents: int
    status: str
    paid_at: Optional[str]
    billing_period: Optional[str]
    invoice_url: Optional[str]
    invoice_pdf: Optional[str]


class InvoicesResponse(BaseModel):
    items: list[InvoiceItem]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/checkout", response_model=CheckoutResponse)
async def create_checkout(
    body: CheckoutRequest,
    current_user: User = Depends(get_current_firm_user),
):
    """Create a Stripe Checkout Session and return the hosted payment URL.

    Frontend redirects the user to checkout_url to enter card details.
    """
    if not current_user.firm_id:
        raise HTTPException(status_code=400, detail="User is not associated with a firm")

    success_url = body.success_url or f"{settings.FRONTEND_URL}/checkout/success"
    cancel_url = body.cancel_url or f"{settings.FRONTEND_URL}/checkout/cancel"

    try:
        url = await create_checkout_session(
            firm_id=current_user.firm_id,
            success_url=success_url,
            cancel_url=cancel_url,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"[billing] checkout error for firm {current_user.firm_id}: {e}")
        raise HTTPException(status_code=502, detail="Failed to create checkout session")

    return CheckoutResponse(checkout_url=url)


@router.get("/subscription", response_model=Optional[SubscriptionResponse])
async def get_subscription_status(
    current_user: User = Depends(get_current_firm_user),
):
    """Return the current subscription for the user's firm.

    Returns null if no subscription exists yet.
    """
    if not current_user.firm_id:
        raise HTTPException(status_code=400, detail="User is not associated with a firm")

    sub = await get_subscription(current_user.firm_id)
    if not sub:
        return None

    return SubscriptionResponse(
        firm_id=sub.firm_id,
        stripe_subscription_id=sub.stripe_subscription_id,
        stripe_customer_id=sub.stripe_customer_id,
        status=sub.status.value if sub.status else None,
        current_period_start=sub.current_period_start.isoformat() if sub.current_period_start else None,
        current_period_end=sub.current_period_end.isoformat() if sub.current_period_end else None,
        canceled_at=sub.canceled_at.isoformat() if sub.canceled_at else None,
    )


@router.get("/portal", response_model=PortalResponse)
async def get_billing_portal(
    current_user: User = Depends(get_current_firm_user),
):
    """Return a Stripe Customer Portal URL for self-service subscription management.

    The URL is single-use and expires after a short period.
    """
    if not current_user.firm_id:
        raise HTTPException(status_code=400, detail="User is not associated with a firm")

    try:
        url = await create_billing_portal_session(current_user.firm_id)
    except Exception as e:
        logger.error(f"[billing] portal session error for firm {current_user.firm_id}: {e}")
        raise HTTPException(status_code=502, detail="Failed to create billing portal session")

    return PortalResponse(portal_url=url)


@router.get("/plans", response_model=list[PlanResponse])
async def list_plans():
    """Return all active subscription plans. Public — no auth required."""
    plans = await get_active_plans()
    return [
        PlanResponse(
            id=p.id,
            name=p.name,
            stripe_price_id=p.stripe_price_id,
            price_cents=p.price_cents,
            features=p.features,
            is_active=p.is_active,
        )
        for p in plans
    ]


@router.delete("/subscription")
async def cancel_firm_subscription(
    current_user: User = Depends(get_current_firm_user),
):
    """Cancel the firm's active subscription at the end of the current period."""
    if not current_user.firm_id:
        raise HTTPException(status_code=400, detail="User is not associated with a firm")

    success = await cancel_subscription(current_user.firm_id)
    if not success:
        raise HTTPException(status_code=404, detail="No active subscription found")

    return {"status": "canceled"}


@router.get("/overview", response_model=BillingOverviewResponse)
async def billing_overview(
    current_user: User = Depends(get_current_firm_user),
):
    """Return all data needed to render the billing page in one call.

    Includes plan details, per-unit meter prices, and current subscription
    status. Frontend uses this to populate the billing page header and
    the 'How Pay-as-You-Go Works' section.
    """
    if not current_user.firm_id:
        raise HTTPException(status_code=400, detail="User is not associated with a firm")

    try:
        data = await get_billing_overview(current_user.firm_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return BillingOverviewResponse(**data)


@router.get("/usage-breakdown", response_model=UsageBreakdownResponse)
async def usage_breakdown(
    current_user: User = Depends(get_current_firm_user),
):
    """Return per-category usage, charges, and trend vs previous billing period.

    Units are counted from the firm's activity logs. Rate and label come from
    the plan_payg meter_prices config. Trend compares the current period to the
    equivalent prior period of the same length.
    """
    if not current_user.firm_id:
        raise HTTPException(status_code=400, detail="User is not associated with a firm")

    data = await get_usage_breakdown(current_user.firm_id)
    return UsageBreakdownResponse(**data)


@router.get("/cost-drivers", response_model=CostDriversResponse)
async def cost_drivers(
    by: str = "workflow",
    current_user: User = Depends(get_current_firm_user),
):
    """Return top cost drivers grouped by user or workflow for the current billing period.

    Query param: by=user  → spend per firm member, sorted descending.
                 by=workflow → spend per billing category, sorted descending.
    """
    if not current_user.firm_id:
        raise HTTPException(status_code=400, detail="User is not associated with a firm")

    if by not in ("user", "workflow"):
        raise HTTPException(status_code=400, detail="'by' must be 'user' or 'workflow'")

    data = await get_cost_drivers(current_user.firm_id, by=by)
    return CostDriversResponse(**data)


@router.get("/payment-method", response_model=PaymentMethodResponse)
async def payment_method(
    current_user: User = Depends(get_current_firm_user),
):
    """Return the default payment method on file for the firm's Stripe customer.

    Returns has_payment_method=false when no card has been added yet.
    """
    if not current_user.firm_id:
        raise HTTPException(status_code=400, detail="User is not associated with a firm")

    try:
        data = await get_payment_method(current_user.firm_id)
    except Exception as e:
        logger.error(f"[billing] payment-method error for firm {current_user.firm_id}: {e}")
        raise HTTPException(status_code=502, detail="Failed to retrieve payment method")

    return PaymentMethodResponse(**data)


@router.get("/invoices", response_model=InvoicesResponse)
async def recent_invoices(
    limit: int = 10,
    current_user: User = Depends(get_current_firm_user),
):
    """Return recent invoices with Stripe-hosted PDF download links.

    Queries Stripe directly when a customer ID exists so invoice_pdf and
    invoice_url are always populated. Falls back to local DB rows otherwise.
    limit: max number of invoices to return (default 10, max 100).
    """
    if not current_user.firm_id:
        raise HTTPException(status_code=400, detail="User is not associated with a firm")

    limit = min(limit, 100)

    try:
        items = await get_recent_invoices(current_user.firm_id, limit=limit)
    except Exception as e:
        logger.error(f"[billing] invoices error for firm {current_user.firm_id}: {e}")
        raise HTTPException(status_code=502, detail="Failed to retrieve invoices")

    return InvoicesResponse(items=[InvoiceItem(**item) for item in items])


@router.post("/sync-subscription")
async def sync_subscription(
    current_user: User = Depends(get_current_firm_user),
):
    """Re-fetch the latest subscription from Stripe and update local DB.

    Use this to fix null period dates caused by webhook processing issues.
    """
    if not current_user.firm_id:
        raise HTTPException(status_code=400, detail="User is not associated with a firm")

    try:
        result = await resync_subscription(current_user.firm_id)
    except Exception as e:
        logger.error(f"[billing] resync error for firm {current_user.firm_id}: {e}")
        raise HTTPException(status_code=502, detail="Failed to re-sync subscription")

    return result
