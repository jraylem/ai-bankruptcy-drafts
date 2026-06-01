"""Stripe webhook handler — receives and processes Stripe events."""

import logging

import stripe
from fastapi import APIRouter, Header, HTTPException, Request

from ..config import settings
from ..notifications.email import (
    send_payment_failed_email,
    send_subscription_activated_email,
    send_subscription_canceled_email,
)
from .service import (
    create_billing_portal_session,
    get_firm_for_webhook,
    sync_invoice_from_stripe,
    sync_subscription_from_stripe,
)

logger = logging.getLogger(__name__)

router = APIRouter()

stripe.api_key = settings.STRIPE_SECRET_KEY

# Stripe event types we care about
_SUBSCRIPTION_EVENTS = {
    "customer.subscription.created",
    "customer.subscription.updated",
    "customer.subscription.deleted",
}

_INVOICE_EVENTS = {
    "invoice.paid",
    "invoice.payment_failed",
    "invoice.updated",
}


@router.post("/billing/webhook", include_in_schema=False)
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(None, alias="stripe-signature"),
):
    """Receive Stripe webhook events and sync to local DB.

    Stripe signs every request with a HMAC signature. We verify it first
    to reject any forged payloads before touching the DB.
    """
    payload = await request.body()

    if not settings.STRIPE_WEBHOOK_SECRET:
        logger.warning("[webhook] STRIPE_WEBHOOK_SECRET not set — skipping signature verification")
        try:
            event = stripe.Event.construct_from(
                stripe.util.convert_to_stripe_object(
                    stripe.util.json.loads(payload)
                ),
                stripe.api_key,
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid payload: {e}")
    else:
        try:
            event = stripe.Webhook.construct_event(
                payload, stripe_signature, settings.STRIPE_WEBHOOK_SECRET
            )
        except stripe.error.SignatureVerificationError:
            logger.warning("[webhook] invalid Stripe signature")
            raise HTTPException(status_code=400, detail="Invalid signature")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid payload: {e}")

    event_type = event["type"]
    event_data = event["data"]["object"]

    logger.info(f"[webhook] received event: {event_type} id={event['id']}")

    try:
        if event_type in _SUBSCRIPTION_EVENTS:
            await sync_subscription_from_stripe(event_data)

            firm = await get_firm_for_webhook(event_data)
            if firm:
                if event_type == "customer.subscription.created":
                    await send_subscription_activated_email(
                        to_email=firm.owner_email,
                        firm_name=firm.name,
                        plan_name="Jurisgentic",
                    )
                elif event_type == "customer.subscription.deleted":
                    await send_subscription_canceled_email(
                        to_email=firm.owner_email,
                        firm_name=firm.name,
                    )

        elif event_type in _INVOICE_EVENTS:
            await sync_invoice_from_stripe(event_data)

            if event_type == "invoice.payment_failed":
                firm = await get_firm_for_webhook(event_data)
                if firm:
                    portal_url = f"{settings.FRONTEND_URL}/settings/billing"
                    try:
                        portal_url = await create_billing_portal_session(firm.id)
                    except Exception:
                        logger.warning(f"[webhook] could not create portal session for firm {firm.id}, using fallback URL")
                    await send_payment_failed_email(
                        to_email=firm.owner_email,
                        firm_name=firm.name,
                        portal_url=portal_url,
                    )

        else:
            logger.debug(f"[webhook] unhandled event type: {event_type}")

    except Exception as e:
        # Log but return 200 so Stripe doesn't retry endlessly
        logger.error(f"[webhook] error processing {event_type}: {e}", exc_info=True)

    return {"status": "ok"}
