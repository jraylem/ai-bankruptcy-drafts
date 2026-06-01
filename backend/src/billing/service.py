"""Billing service — Stripe operations and local DB sync."""

import logging
from calendar import monthrange
from datetime import datetime, timezone, timedelta
from typing import Optional

import stripe
from sqlalchemy import select, func as sql_func

from ..auth.database import UserAsyncSessionLocal
from ..auth.models import User
from ..chatbot.database import AsyncSessionLocal
from ..chatbot.models import UserActivityLog
from ..firms.models import Firm, Plan
from .models import Invoice, InvoiceStatus, Subscription, SubscriptionStatus
from ..config import settings
from ..permissions.constants import ROLE_DISPLAY_NAMES

# Maps activity log action names → billing meter category keys
_ACTION_CATEGORY_MAP: dict[str, str] = {
    "chat_message": "chat",
    "upload_pdf": "ingestion",
    "gmail_ingest": "ingestion",
    "generate_document": "agt_composition",
    "draft_motion": "pleading_generation",
}

logger = logging.getLogger(__name__)

stripe.api_key = settings.STRIPE_SECRET_KEY


# ---------------------------------------------------------------------------
# Stripe customer
# ---------------------------------------------------------------------------

async def get_or_create_stripe_customer(firm_id: str) -> str:
    """Return existing stripe_customer_id for the firm, or create one in Stripe.

    Updates firms.stripe_customer_id when a new customer is created.
    Raises ValueError if firm is not found.
    """
    async with UserAsyncSessionLocal() as db:
        result = await db.execute(select(Firm).where(Firm.id == firm_id))
        firm = result.scalar_one_or_none()
        if not firm:
            raise ValueError(f"Firm {firm_id} not found")

        if firm.stripe_customer_id:
            return firm.stripe_customer_id

        customer = stripe.Customer.create(
            email=firm.owner_email,
            name=firm.name,
            metadata={"firm_id": firm_id},
        )
        firm.stripe_customer_id = customer.id
        await db.commit()
        logger.info(f"[billing] created Stripe customer {customer.id} for firm {firm_id}")
        return customer.id


# ---------------------------------------------------------------------------
# Checkout
# ---------------------------------------------------------------------------

async def create_checkout_session(
    firm_id: str,
    success_url: str,
    cancel_url: str,
) -> str:
    """Create a Stripe Checkout Session for the PAYG plan and return the hosted URL.

    Loads all 4 metered price IDs from the plan_payg plan and adds them as
    line items so the firm's subscription tracks every usage category.
    Stripe redirects to success_url / cancel_url when done.
    """
    customer_id = await get_or_create_stripe_customer(firm_id)

    async with UserAsyncSessionLocal() as db:
        result = await db.execute(select(Plan).where(Plan.id == "plan_payg"))
        plan = result.scalar_one_or_none()
        if not plan:
            raise ValueError("plan_payg not found — run seed_plans() first")

    price_ids: dict = (plan.features or {}).get("price_ids", {})
    if not any(price_ids.values()):
        raise ValueError("plan_payg has no price IDs configured in features.price_ids")

    line_items = [{"price": pid} for pid in price_ids.values() if pid]

    session = stripe.checkout.Session.create(
        customer=customer_id,
        payment_method_types=["card"],
        line_items=line_items,
        mode="subscription",
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={"firm_id": firm_id},
        subscription_data={"metadata": {"firm_id": firm_id}},
    )
    logger.info(f"[billing] checkout session {session.id} created for firm {firm_id} ({len(line_items)} price items)")
    return session.url


# ---------------------------------------------------------------------------
# Usage reporting
# ---------------------------------------------------------------------------

async def report_usage_event(firm_id: str, event_name: str, quantity: int = 1) -> None:
    """Report a metered usage event to Stripe for the given firm.

    event_name must match a meter name configured in the Stripe dashboard:
      "chat", "ingestion", "agt_composition", "pleading_generation"

    Fire-and-forget — logs errors but never raises, so billing failures
    never block the user's actual request.
    """
    if not firm_id:
        return
    try:
        customer_id = await get_or_create_stripe_customer(firm_id)
        stripe.billing.MeterEvent.create(
            event_name=event_name,
            payload={
                "stripe_customer_id": customer_id,
                "value": str(quantity),
            },
        )
        logger.info(f"[billing] meter event '{event_name}' x{quantity} reported for firm {firm_id}")
    except Exception as e:
        logger.error(f"[billing] failed to report meter event '{event_name}' for firm {firm_id}: {e}")


# ---------------------------------------------------------------------------
# Subscription
# ---------------------------------------------------------------------------

async def get_subscription(firm_id: str) -> Optional[Subscription]:
    """Return the active/trialing subscription row for a firm, or None."""
    async with UserAsyncSessionLocal() as db:
        result = await db.execute(
            select(Subscription)
            .where(Subscription.firm_id == firm_id)
            .order_by(Subscription.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()


async def cancel_subscription(firm_id: str) -> bool:
    """Cancel the firm's active Stripe subscription at period end.

    Updates local subscription row to 'canceled' and sets canceled_at.
    Returns True on success, False if no active subscription found.
    """
    async with UserAsyncSessionLocal() as db:
        result = await db.execute(
            select(Subscription)
            .where(Subscription.firm_id == firm_id)
            .where(Subscription.status.in_([
                SubscriptionStatus.active,
                SubscriptionStatus.trialing,
                SubscriptionStatus.past_due,
            ]))
            .order_by(Subscription.created_at.desc())
            .limit(1)
        )
        sub = result.scalar_one_or_none()
        if not sub:
            logger.warning(f"[billing] no active subscription found for firm {firm_id}")
            return False

        stripe.Subscription.modify(
            sub.stripe_subscription_id,
            cancel_at_period_end=True,
        )

        # Don't change status — subscription stays active until period end in Stripe.
        # The customer.subscription.updated/deleted webhooks will set the final status.
        sub.canceled_at = datetime.now(timezone.utc)
        await db.commit()
        logger.info(f"[billing] cancel_at_period_end set for subscription {sub.stripe_subscription_id} for firm {firm_id}")
        return True


# ---------------------------------------------------------------------------
# Webhook sync helpers (called by Task 15 webhook handler)
# ---------------------------------------------------------------------------

async def sync_subscription_from_stripe(stripe_sub) -> None:
    """Upsert a Subscription row from a Stripe subscription object.

    Called when Stripe fires customer.subscription.* webhook events.
    """
    if not isinstance(stripe_sub, dict):
        if hasattr(stripe_sub, "to_dict_recursive"):
            stripe_sub = stripe_sub.to_dict_recursive()
        else:
            import json
            stripe_sub = json.loads(str(stripe_sub))

    firm_id = stripe_sub.get("metadata", {}).get("firm_id")
    if not firm_id:
        logger.warning(f"[billing] webhook subscription {stripe_sub['id']} missing firm_id metadata, skipping")
        return

    async with UserAsyncSessionLocal() as db:
        result = await db.execute(
            select(Subscription).where(
                Subscription.stripe_subscription_id == stripe_sub["id"]
            )
        )
        sub = result.scalar_one_or_none()

        status = SubscriptionStatus(stripe_sub["status"]) if stripe_sub["status"] in SubscriptionStatus._value2member_map_ else SubscriptionStatus.incomplete
        ps = stripe_sub.get("current_period_start")
        pe = stripe_sub.get("current_period_end")
        ca = stripe_sub.get("canceled_at")
        period_start = datetime.fromtimestamp(ps, tz=timezone.utc) if ps is not None else None
        period_end   = datetime.fromtimestamp(pe, tz=timezone.utc) if pe is not None else None
        canceled_at  = datetime.fromtimestamp(ca, tz=timezone.utc) if ca is not None else None
        logger.info(f"[billing] sync sub {stripe_sub['id']} status={stripe_sub['status']} period={ps}→{pe}")

        if sub:
            sub.status = status
            sub.current_period_start = period_start
            sub.current_period_end = period_end
            sub.canceled_at = canceled_at
        else:
            customer_id = stripe_sub.get("customer", "")
            sub = Subscription(
                firm_id=firm_id,
                stripe_subscription_id=stripe_sub["id"],
                stripe_customer_id=customer_id,
                status=status,
                current_period_start=period_start,
                current_period_end=period_end,
                canceled_at=canceled_at,
            )
            db.add(sub)

        # Keep firms.subscription_status in sync
        firm_result = await db.execute(select(Firm).where(Firm.id == firm_id))
        firm = firm_result.scalar_one_or_none()
        if firm:
            from ..firms.models import SubscriptionStatus as FirmSubStatus
            try:
                firm.subscription_status = FirmSubStatus(stripe_sub["status"])
            except ValueError:
                logger.warning(
                    f"[billing] unknown Stripe subscription status '{stripe_sub['status']}' "
                    f"for firm {firm_id} — firm status not updated"
                )

        await db.commit()
        logger.info(f"[billing] synced subscription {stripe_sub['id']} for firm {firm_id} → {status}")


async def sync_invoice_from_stripe(stripe_inv) -> None:
    """Upsert an Invoice row from a Stripe invoice object.

    Called when Stripe fires invoice.* webhook events.
    """
    if not isinstance(stripe_inv, dict):
        if hasattr(stripe_inv, "to_dict_recursive"):
            stripe_inv = stripe_inv.to_dict_recursive()
        else:
            import json
            stripe_inv = json.loads(str(stripe_inv))

    firm_id = stripe_inv.get("metadata", {}).get("firm_id")
    customer_id = stripe_inv.get("customer")

    # Fall back to looking up firm by stripe_customer_id if metadata missing
    if not firm_id and customer_id:
        async with UserAsyncSessionLocal() as db:
            result = await db.execute(
                select(Firm).where(Firm.stripe_customer_id == customer_id)
            )
            firm = result.scalar_one_or_none()
            if firm:
                firm_id = firm.id

    if not firm_id:
        logger.warning(f"[billing] invoice {stripe_inv['id']} missing firm_id, skipping")
        return

    async with UserAsyncSessionLocal() as db:
        result = await db.execute(
            select(Invoice).where(Invoice.stripe_invoice_id == stripe_inv["id"])
        )
        inv = result.scalar_one_or_none()

        status = InvoiceStatus(stripe_inv["status"]) if stripe_inv.get("status") in InvoiceStatus._value2member_map_ else InvoiceStatus.open
        paid_at = datetime.fromtimestamp(stripe_inv["status_transitions"]["paid_at"], tz=timezone.utc) if stripe_inv.get("status_transitions", {}).get("paid_at") else None

        if inv:
            inv.status = status
            inv.paid_at = paid_at
            inv.amount_cents = stripe_inv.get("amount_paid", 0)
        else:
            inv = Invoice(
                firm_id=firm_id,
                stripe_invoice_id=stripe_inv["id"],
                amount_cents=stripe_inv.get("amount_paid", 0),
                status=status,
                paid_at=paid_at,
            )
            db.add(inv)

        await db.commit()
        logger.info(f"[billing] synced invoice {stripe_inv['id']} for firm {firm_id} → {status}")


# ---------------------------------------------------------------------------
# Billing portal
# ---------------------------------------------------------------------------

async def create_billing_portal_session(firm_id: str) -> str:
    """Create a Stripe Customer Portal session and return the URL.

    The firm owner lands on this URL to self-manage their subscription
    (upgrade, downgrade, cancel, update payment method).
    Called by: src/billing/routes.py GET /billing/portal
               src/billing/webhook.py invoice.payment_failed email
    """
    customer_id = await get_or_create_stripe_customer(firm_id)
    session = stripe.billing_portal.Session.create(
        customer=customer_id,
        return_url=f"{settings.FRONTEND_URL}/settings/billing",
    )
    logger.info(f"[billing] portal session created for firm {firm_id}")
    return session.url


# ---------------------------------------------------------------------------
# Plans
# ---------------------------------------------------------------------------

async def get_active_plans() -> list:
    """Return all active Plan rows ordered by price ascending.

    Called by: src/billing/routes.py GET /billing/plans (public)
    """
    async with UserAsyncSessionLocal() as db:
        result = await db.execute(
            select(Plan)
            .where(Plan.is_active.is_(True))
            .order_by(Plan.price_cents.asc())
        )
        return result.scalars().all()


# ---------------------------------------------------------------------------
# Billing overview (feeds GET /api/billing/overview)
# ---------------------------------------------------------------------------

async def get_billing_overview(firm_id: str) -> dict:
    """Aggregate all data needed for the billing page in one DB round-trip.

    Returns plan details, per-unit meter prices, and current subscription
    status so the frontend can render the full billing page from one call.
    """
    async with UserAsyncSessionLocal() as db:
        firm_result = await db.execute(select(Firm).where(Firm.id == firm_id))
        firm = firm_result.scalar_one_or_none()
        if not firm:
            raise ValueError(f"Firm {firm_id} not found")

        plan_result = await db.execute(select(Plan).where(Plan.id == "plan_payg"))
        plan = plan_result.scalar_one_or_none()

        sub_result = await db.execute(
            select(Subscription)
            .where(Subscription.firm_id == firm_id)
            .order_by(Subscription.created_at.desc())
            .limit(1)
        )
        sub = sub_result.scalar_one_or_none()

    features = plan.features or {} if plan else {}
    meter_prices = features.get("meter_prices", [])
    billing_period = features.get("billing_period", "monthly")

    return {
        "plan_name": plan.name if plan else None,
        "base_price_cents": plan.price_cents if plan else 0,
        "billing_period": billing_period,
        "meter_prices": meter_prices,
        "subscription_status": sub.status.value if sub else None,
        "current_period_start": sub.current_period_start.isoformat() if sub and sub.current_period_start else None,
        "current_period_end": sub.current_period_end.isoformat() if sub and sub.current_period_end else None,
        "stripe_customer_id": firm.stripe_customer_id,
    }


# ---------------------------------------------------------------------------
# Usage analytics helpers
# ---------------------------------------------------------------------------

async def _get_billing_period(firm_id: str) -> tuple[datetime, datetime]:
    """Return (period_start, period_end) from the firm's active subscription.

    Falls back to the current calendar month if no subscription exists.
    """
    async with UserAsyncSessionLocal() as db:
        result = await db.execute(
            select(Subscription)
            .where(Subscription.firm_id == firm_id)
            .order_by(Subscription.created_at.desc())
            .limit(1)
        )
        sub = result.scalar_one_or_none()

    if sub and sub.current_period_start and sub.current_period_end:
        return sub.current_period_start, sub.current_period_end

    now = datetime.now(timezone.utc)
    first_day = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    _, last_day_num = monthrange(now.year, now.month)
    last_day = now.replace(day=last_day_num, hour=23, minute=59, second=59, microsecond=999999)
    return first_day, last_day


async def _count_actions_by_category(
    firm_id: str,
    period_start: datetime,
    period_end: datetime,
) -> dict[str, int]:
    """Count activity log events per billing category key within a time window."""
    tracked_actions = list(_ACTION_CATEGORY_MAP.keys())
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(UserActivityLog.action, sql_func.count(UserActivityLog.id).label("cnt"))
            .where(UserActivityLog.firm_id == firm_id)
            .where(UserActivityLog.action.in_(tracked_actions))
            .where(UserActivityLog.created_at >= period_start)
            .where(UserActivityLog.created_at <= period_end)
            .group_by(UserActivityLog.action)
        )
        rows = result.all()

    counts: dict[str, int] = {}
    for action, cnt in rows:
        category = _ACTION_CATEGORY_MAP[action]
        counts[category] = counts.get(category, 0) + cnt
    return counts


# ---------------------------------------------------------------------------
# Usage breakdown  (GET /api/billing/usage-breakdown)
# ---------------------------------------------------------------------------

async def get_usage_breakdown(firm_id: str) -> dict:
    """Compute per-category usage, charges, and trends for the current billing period."""
    now = datetime.now(timezone.utc)
    period_start, period_end = await _get_billing_period(firm_id)

    async with UserAsyncSessionLocal() as db:
        plan_result = await db.execute(select(Plan).where(Plan.id == "plan_payg"))
        plan = plan_result.scalar_one_or_none()

    features = (plan.features or {}) if plan else {}
    meter_prices: list[dict] = features.get("meter_prices", [])
    rate_map = {m["key"]: m["price_cents"] for m in meter_prices}

    current_counts = await _count_actions_by_category(firm_id, period_start, period_end)

    period_duration = period_end - period_start
    prev_end = period_start - timedelta(seconds=1)
    prev_start = prev_end - period_duration
    prev_counts = await _count_actions_by_category(firm_id, prev_start, prev_end)

    items = []
    mtd_total_cents = 0
    for mp in meter_prices:
        key = mp["key"]
        units = current_counts.get(key, 0)
        rate = mp["price_cents"]
        charge = units * rate
        mtd_total_cents += charge

        prev_units = prev_counts.get(key, 0)
        if prev_units > 0:
            trend_pct = round((units - prev_units) / prev_units * 100)
        elif units > 0:
            trend_pct = 100
        else:
            trend_pct = 0

        items.append({
            "key": key,
            "label": mp["label"],
            "unit_label": mp["unit_label"],
            "units_used": units,
            "rate_cents": rate,
            "current_charge_cents": charge,
            "trend_pct": trend_pct,
        })

    days_elapsed = max((now - period_start).total_seconds() / 86400, 0.5)
    total_days = max((period_end - period_start).total_seconds() / 86400, 1)
    projected_cents = round(mtd_total_cents / days_elapsed * total_days)

    return {
        "billing_period_start": period_start.isoformat(),
        "billing_period_end": period_end.isoformat(),
        "mtd_total_cents": mtd_total_cents,
        "projected_cents": projected_cents,
        "items": items,
    }


# ---------------------------------------------------------------------------
# Cost drivers  (GET /api/billing/cost-drivers?by=user|workflow)
# ---------------------------------------------------------------------------

async def get_cost_drivers(firm_id: str, by: str = "workflow") -> dict:
    """Aggregate spend for the current billing period grouped by user or workflow."""
    period_start, period_end = await _get_billing_period(firm_id)

    async with UserAsyncSessionLocal() as db:
        plan_result = await db.execute(select(Plan).where(Plan.id == "plan_payg"))
        plan = plan_result.scalar_one_or_none()

    features = (plan.features or {}) if plan else {}
    meter_prices: list[dict] = features.get("meter_prices", [])
    rate_map = {m["key"]: m["price_cents"] for m in meter_prices}
    label_map = {m["key"]: m["label"] for m in meter_prices}

    tracked_actions = list(_ACTION_CATEGORY_MAP.keys())

    if by == "user":
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(
                    UserActivityLog.user_id,
                    UserActivityLog.action,
                    sql_func.count(UserActivityLog.id).label("cnt"),
                )
                .where(UserActivityLog.firm_id == firm_id)
                .where(UserActivityLog.action.in_(tracked_actions))
                .where(UserActivityLog.created_at >= period_start)
                .where(UserActivityLog.created_at <= period_end)
                .where(UserActivityLog.user_id.isnot(None))
                .group_by(UserActivityLog.user_id, UserActivityLog.action)
            )
            rows = result.all()

        user_spend: dict[str, int] = {}
        for user_id, action, cnt in rows:
            category = _ACTION_CATEGORY_MAP[action]
            rate = rate_map.get(category, 0)
            user_spend[user_id] = user_spend.get(user_id, 0) + cnt * rate

        if not user_spend:
            return {"by": "user", "items": []}

        async with UserAsyncSessionLocal() as db:
            result = await db.execute(
                select(User).where(User.id.in_(list(user_spend.keys())))
            )
            users: dict[str, User] = {u.id: u for u in result.scalars().all()}

        items = []
        for uid, total_cents in sorted(user_spend.items(), key=lambda x: x[1], reverse=True):
            u = users.get(uid)
            full_name = f"{u.first_name or ''} {u.last_name or ''}".strip() if u else ""
            label = full_name or (u.email if u else uid)
            role = str(u.role) if u else "member"
            items.append({
                "user_id": uid,
                "label": label,
                "email": u.email if u else None,
                "role": role,
                "role_display": ROLE_DISPLAY_NAMES.get(role, role.replace("_", " ").title()),
                "total_cents": total_cents,
            })
        return {"by": "user", "items": items}

    # by == "workflow"
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(
                UserActivityLog.action,
                sql_func.count(UserActivityLog.id).label("cnt"),
            )
            .where(UserActivityLog.firm_id == firm_id)
            .where(UserActivityLog.action.in_(tracked_actions))
            .where(UserActivityLog.created_at >= period_start)
            .where(UserActivityLog.created_at <= period_end)
            .group_by(UserActivityLog.action)
        )
        rows = result.all()

    category_spend: dict[str, int] = {}
    for action, cnt in rows:
        category = _ACTION_CATEGORY_MAP[action]
        rate = rate_map.get(category, 0)
        category_spend[category] = category_spend.get(category, 0) + cnt * rate

    items = [
        {
            "key": key,
            "label": label_map.get(key, key.replace("_", " ").title()),
            "total_cents": total,
        }
        for key, total in sorted(category_spend.items(), key=lambda x: x[1], reverse=True)
    ]
    return {"by": "workflow", "items": items}


# ---------------------------------------------------------------------------
# Payment method  (GET /api/billing/payment-method)
# ---------------------------------------------------------------------------

async def get_payment_method(firm_id: str) -> dict:
    """Return the default card on file for the firm's Stripe customer."""
    import asyncio

    customer_id = await get_or_create_stripe_customer(firm_id)

    payment_methods = await asyncio.to_thread(
        stripe.PaymentMethod.list, customer=customer_id, type="card"
    )
    if not payment_methods.data:
        customer = await asyncio.to_thread(
            stripe.Customer.retrieve, customer_id, expand=["default_source"]
        )
        import json
        if not isinstance(customer, dict):
            customer = json.loads(str(customer))
        src = customer.get("default_source")
        if src and isinstance(src, dict) and src.get("object") == "card":
            return {
                "has_payment_method": True,
                "brand": src.get("brand", "").lower(),
                "last4": src.get("last4", ""),
                "exp_month": src.get("exp_month"),
                "exp_year": src.get("exp_year"),
                "funding": src.get("funding"),
            }
        return {"has_payment_method": False}

    card = payment_methods.data[0].card
    return {
        "has_payment_method": True,
        "brand": card.brand,
        "last4": card.last4,
        "exp_month": card.exp_month,
        "exp_year": card.exp_year,
        "funding": card.funding,
    }


# ---------------------------------------------------------------------------
# Recent invoices  (GET /api/billing/invoices)
# ---------------------------------------------------------------------------

async def get_recent_invoices(firm_id: str, limit: int = 10) -> list[dict]:
    """Return recent invoices enriched with Stripe PDF/hosted URLs.

    Queries Stripe directly when a customer ID exists so the response always
    has invoice_pdf and invoice_url download links.  Falls back to local DB
    rows if no Stripe customer has been created yet.
    """
    async with UserAsyncSessionLocal() as db:
        firm_result = await db.execute(select(Firm).where(Firm.id == firm_id))
        firm = firm_result.scalar_one_or_none()

    if firm and firm.stripe_customer_id:
        import asyncio
        stripe_invoices = await asyncio.to_thread(
            stripe.Invoice.list,
            customer=firm.stripe_customer_id,
            limit=limit,
        )
        items = []
        for inv in stripe_invoices.data:
            ts = getattr(inv.status_transitions, "paid_at", None)
            paid_at = datetime.fromtimestamp(ts, tz=timezone.utc) if ts else None
            period_start_ts = getattr(inv, "period_start", None)
            billing_period = (
                datetime.fromtimestamp(period_start_ts, tz=timezone.utc).strftime("%b %Y")
                if period_start_ts
                else (paid_at.strftime("%b %Y") if paid_at else None)
            )
            items.append({
                "stripe_invoice_id": inv.id,
                "invoice_number": inv.number or inv.id,
                "amount_cents": inv.amount_paid,
                "status": inv.status,
                "paid_at": paid_at.isoformat() if paid_at else None,
                "billing_period": billing_period,
                "invoice_url": inv.hosted_invoice_url,
                "invoice_pdf": inv.invoice_pdf,
            })
        return items

    # Fallback: local invoices table (no PDF URL available)
    async with UserAsyncSessionLocal() as db:
        result = await db.execute(
            select(Invoice)
            .where(Invoice.firm_id == firm_id)
            .order_by(Invoice.created_at.desc())
            .limit(limit)
        )
        local_invoices = result.scalars().all()

    return [
        {
            "stripe_invoice_id": inv.stripe_invoice_id,
            "invoice_number": inv.stripe_invoice_id,
            "amount_cents": inv.amount_cents,
            "status": inv.status.value,
            "paid_at": inv.paid_at.isoformat() if inv.paid_at else None,
            "billing_period": inv.paid_at.strftime("%b %Y") if inv.paid_at else None,
            "invoice_url": None,
            "invoice_pdf": None,
        }
        for inv in local_invoices
    ]


# ---------------------------------------------------------------------------
# Webhook helper
# ---------------------------------------------------------------------------

async def get_firm_for_webhook(event_data) -> Optional[Firm]:
    """Resolve the Firm from a Stripe event object.

    Tries firm_id from metadata first, falls back to stripe_customer_id lookup.
    Called by: src/billing/webhook.py for email dispatch after DB sync.
    """
    if not isinstance(event_data, dict):
        if hasattr(event_data, "to_dict_recursive"):
            event_data = event_data.to_dict_recursive()
        else:
            import json
            event_data = json.loads(str(event_data))

    firm_id = event_data.get("metadata", {}).get("firm_id")
    customer_id = event_data.get("customer")

    async with UserAsyncSessionLocal() as db:
        if firm_id:
            result = await db.execute(select(Firm).where(Firm.id == firm_id))
            return result.scalar_one_or_none()
        if customer_id:
            result = await db.execute(select(Firm).where(Firm.stripe_customer_id == customer_id))
            return result.scalar_one_or_none()
    return None


# ---------------------------------------------------------------------------
# Manual re-sync  (POST /api/billing/sync-subscription)
# ---------------------------------------------------------------------------

async def resync_subscription(firm_id: str) -> dict:
    """Fetch the latest subscription from Stripe and re-sync to local DB.

    Fixes cases where the webhook ran before the StripeObject conversion was
    correct, leaving period dates null despite an active subscription.
    """
    customer_id = await get_or_create_stripe_customer(firm_id)

    import asyncio
    stripe_subs = await asyncio.to_thread(
        stripe.Subscription.list,
        customer=customer_id,
        limit=1,
        status="all",
    )
    if not stripe_subs.data:
        return {"synced": False, "detail": "No Stripe subscription found for this firm"}

    stripe_sub = stripe_subs.data[0]
    if hasattr(stripe_sub, "to_dict_recursive"):
        stripe_sub_dict = stripe_sub.to_dict_recursive()
    else:
        import json
        stripe_sub_dict = json.loads(str(stripe_sub))

    # Ensure firm_id is in metadata so sync doesn't skip it
    if not stripe_sub_dict.get("metadata", {}).get("firm_id"):
        stripe_sub_dict.setdefault("metadata", {})["firm_id"] = firm_id

    await sync_subscription_from_stripe(stripe_sub_dict)
    logger.info(f"[billing] manual re-sync completed for firm {firm_id} sub {stripe_sub_dict['id']}")
    return {"synced": True, "subscription_id": stripe_sub_dict["id"], "status": stripe_sub_dict["status"]}
