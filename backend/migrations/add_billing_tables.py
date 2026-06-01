"""
Migration: Billing tables — Phase 2 Task 13.

Creates: subscriptions, invoices tables in user_db.

Prerequisites:
  - add_paywall_db_schema.py must have been run (firms and plans tables exist)

Usage:
    docker compose exec backend uv run python migrations/add_billing_tables.py
"""

import asyncio
import sys
from pathlib import Path

script_dir = Path(__file__).parent.absolute()
project_root = script_dir.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from sqlalchemy import text
from src.auth.database import user_engine, UserAsyncSessionLocal
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


async def table_exists(session, table_name: str) -> bool:
    result = await session.execute(text("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_name = :t
        )
    """), {"t": table_name})
    return result.scalar()


async def enum_exists(session, enum_name: str) -> bool:
    result = await session.execute(text("""
        SELECT EXISTS (
            SELECT 1 FROM pg_type WHERE typname = :e
        )
    """), {"e": enum_name})
    return result.scalar()


async def run():
    async with UserAsyncSessionLocal() as session:
        # ── Enums ──────────────────────────────────────────────────────────

        if not await enum_exists(session, "subscription_status_billing_enum"):
            await session.execute(text("""
                CREATE TYPE subscription_status_billing_enum
                AS ENUM ('active', 'trialing', 'past_due', 'canceled', 'incomplete')
            """))
            logger.info("Created enum: subscription_status_billing_enum")
        else:
            logger.info("Enum subscription_status_billing_enum already exists — skipping")

        if not await enum_exists(session, "invoice_status_enum"):
            await session.execute(text("""
                CREATE TYPE invoice_status_enum
                AS ENUM ('draft', 'open', 'paid', 'void', 'uncollectible')
            """))
            logger.info("Created enum: invoice_status_enum")
        else:
            logger.info("Enum invoice_status_enum already exists — skipping")

        # ── subscriptions table ────────────────────────────────────────────

        if not await table_exists(session, "subscriptions"):
            await session.execute(text("""
                CREATE TABLE subscriptions (
                    id                      VARCHAR PRIMARY KEY,
                    firm_id                 VARCHAR NOT NULL REFERENCES firms(id),
                    stripe_subscription_id  VARCHAR UNIQUE NOT NULL,
                    stripe_customer_id      VARCHAR NOT NULL,
                    plan_id                 VARCHAR REFERENCES plans(id),
                    status                  subscription_status_billing_enum NOT NULL DEFAULT 'trialing',
                    current_period_start    TIMESTAMPTZ,
                    current_period_end      TIMESTAMPTZ,
                    canceled_at             TIMESTAMPTZ,
                    created_at              TIMESTAMPTZ DEFAULT NOW()
                )
            """))
            await session.execute(text(
                "CREATE INDEX idx_subscriptions_firm_id ON subscriptions(firm_id)"
            ))
            logger.info("Created table: subscriptions")
        else:
            logger.info("Table subscriptions already exists — skipping")

        # ── invoices table ─────────────────────────────────────────────────

        if not await table_exists(session, "invoices"):
            await session.execute(text("""
                CREATE TABLE invoices (
                    id                  VARCHAR PRIMARY KEY,
                    firm_id             VARCHAR NOT NULL REFERENCES firms(id),
                    subscription_id     VARCHAR REFERENCES subscriptions(id),
                    stripe_invoice_id   VARCHAR UNIQUE NOT NULL,
                    amount_cents        INTEGER NOT NULL DEFAULT 0,
                    status              invoice_status_enum NOT NULL DEFAULT 'draft',
                    paid_at             TIMESTAMPTZ,
                    created_at          TIMESTAMPTZ DEFAULT NOW()
                )
            """))
            await session.execute(text(
                "CREATE INDEX idx_invoices_firm_id ON invoices(firm_id)"
            ))
            await session.execute(text(
                "CREATE INDEX idx_invoices_subscription_id ON invoices(subscription_id)"
            ))
            logger.info("Created table: invoices")
        else:
            logger.info("Table invoices already exists — skipping")

        await session.commit()
        logger.info("Migration complete.")


if __name__ == "__main__":
    asyncio.run(run())
