"""Seed default billing plans on startup."""

import logging

from sqlalchemy import select

from ..auth.database import UserAsyncSessionLocal
from ..firms.models import Plan

logger = logging.getLogger(__name__)

# Default plans seeded on every startup (idempotent — skips if already exists).
# stripe_price_id is set to None until a real Stripe price is created in the
# Stripe dashboard and the ID is added here or via env.
DEFAULT_PLANS = [
    {
        "id": "plan_payg",
        "name": "Pay As You Go",
        # stripe_price_id is not used for PAYG — individual metered price IDs
        # are stored in features.price_ids below, one per usage category.
        "stripe_price_id": None,
        "price_cents": 0,  # base subscription is $0; charges are metered per use
        "features": {
            "model": "usage_based",
            "billing_period": "monthly",
            "price_ids": {
                "chat": "price_1TZb67K0avrNX3kHnYpVaFZe",
                "ingestion": "price_1TZb67K0avrNX3kHTGyNOhfn",
                "agt_composition": "price_1TZb67K0avrNX3kH1SDPe1MP",
                "pleading_generation": "price_1TZb67K0avrNX3kHklTJtK0j",
            },
            "meter_prices": [
                {
                    "key": "chat",
                    "label": "Chat",
                    "unit_label": "message",
                    "price_cents": 3,
                },
                {
                    "key": "ingestion",
                    "label": "Ingestion",
                    "unit_label": "page",
                    "price_cents": 12,
                },
                {
                    "key": "agt_composition",
                    "label": "AGT Composition",
                    "unit_label": "composition",
                    "price_cents": 650,
                },
                {
                    "key": "pleading_generation",
                    "label": "Pleading Generation",
                    "unit_label": "generation",
                    "price_cents": 885,
                },
            ],
        },
        "is_active": True,
    },
]


async def seed_plans() -> None:
    """Upsert default plans on every startup.

    Uses upsert (insert or update features) so changes to DEFAULT_PLANS
    above are reflected automatically without manual SQL.
    """
    async with UserAsyncSessionLocal() as db:
        try:
            for plan_data in DEFAULT_PLANS:
                result = await db.execute(
                    select(Plan).where(Plan.id == plan_data["id"])
                )
                existing = result.scalar_one_or_none()
                if existing:
                    existing.name = plan_data["name"]
                    existing.features = plan_data["features"]
                    existing.price_cents = plan_data["price_cents"]
                    existing.is_active = plan_data["is_active"]
                    logger.debug(f"[seed] updated plan '{plan_data['id']}'")
                else:
                    plan = Plan(**plan_data)
                    db.add(plan)
                    logger.info(f"[seed] inserted plan '{plan_data['id']}'")

            await db.commit()
        except Exception as e:
            await db.rollback()
            logger.warning(f"[seed] failed to seed plans: {e}")
