"""
Migration: Paywall DB schema — Phase 1 Foundation.

Creates: plans, firms, firm_invitations tables.
Extends: users table with firm_id, role, permissions, invited_by,
         invitation_accepted_at, stripe_subscription_item_id.
Backfills: creates a default firm and assigns all existing users to it.

Usage:
    docker compose exec backend uv run python migrations/add_paywall_db_schema.py
"""

import asyncio
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

script_dir = Path(__file__).parent.absolute()
project_root = script_dir.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from sqlalchemy import text
from src.config import settings
from src.auth.database import user_engine, UserAsyncSessionLocal
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

async def table_exists(session, table_name: str) -> bool:
    result = await session.execute(text("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_name = :t
        )
    """), {"t": table_name})
    return result.scalar()


async def column_exists(session, table_name: str, column_name: str) -> bool:
    result = await session.execute(text("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = :t AND column_name = :c
        )
    """), {"t": table_name, "c": column_name})
    return result.scalar()


async def enum_exists(session, enum_name: str) -> bool:
    result = await session.execute(text("""
        SELECT EXISTS (
            SELECT 1 FROM pg_type WHERE typname = :e
        )
    """), {"e": enum_name})
    return result.scalar()


# ──────────────────────────────────────────────
# Step 1 — Create enums
# ──────────────────────────────────────────────

async def create_enums(session):
    if not await enum_exists(session, "subscription_status_enum"):
        logger.info("Creating enum: subscription_status_enum")
        await session.execute(text("""
            CREATE TYPE subscription_status_enum
            AS ENUM ('active', 'trialing', 'past_due', 'canceled')
        """))

    if not await enum_exists(session, "user_role_enum"):
        logger.info("Creating enum: user_role_enum")
        await session.execute(text("""
            CREATE TYPE user_role_enum
            AS ENUM ('firm_owner', 'admin', 'member')
        """))


# ──────────────────────────────────────────────
# Step 2 — Create plans table
# ──────────────────────────────────────────────

async def create_plans_table(session):
    if await table_exists(session, "plans"):
        logger.info("plans table already exists — skipping")
        return

    logger.info("Creating plans table...")
    await session.execute(text("""
        CREATE TABLE plans (
            id              VARCHAR PRIMARY KEY,
            name            VARCHAR NOT NULL,
            stripe_price_id VARCHAR,
            price_cents     INTEGER NOT NULL DEFAULT 0,
            features        JSONB,
            is_active       BOOLEAN NOT NULL DEFAULT TRUE
        )
    """))
    logger.info("plans table created.")


# ──────────────────────────────────────────────
# Step 3 — Create firms table
# ──────────────────────────────────────────────

async def create_firms_table(session):
    if await table_exists(session, "firms"):
        logger.info("firms table already exists — skipping")
        return

    logger.info("Creating firms table...")
    await session.execute(text("""
        CREATE TABLE firms (
            id                    VARCHAR PRIMARY KEY,
            name                  VARCHAR NOT NULL,
            owner_email           VARCHAR NOT NULL UNIQUE,
            stripe_customer_id    VARCHAR,
            subscription_status   subscription_status_enum NOT NULL DEFAULT 'trialing',
            plan_id               VARCHAR REFERENCES plans(id),
            seat_limit            INTEGER NOT NULL DEFAULT 5,
            created_at            TIMESTAMPTZ DEFAULT NOW(),
            is_active             BOOLEAN NOT NULL DEFAULT TRUE
        )
    """))
    await session.execute(text(
        "CREATE INDEX idx_firms_owner_email ON firms (owner_email)"
    ))
    logger.info("firms table created.")


# ──────────────────────────────────────────────
# Step 4 — Add paywall columns to users
# ──────────────────────────────────────────────

async def extend_users_table(session):
    logger.info("Extending users table with paywall columns...")

    new_columns = [
        ("firm_id",                     "VARCHAR REFERENCES firms(id)"),
        ("role",                        "user_role_enum"),
        ("permissions",                 "JSONB"),
        ("invited_by",                  "VARCHAR REFERENCES users(id)"),
        ("invitation_accepted_at",      "TIMESTAMPTZ"),
        ("stripe_subscription_item_id", "VARCHAR"),
    ]

    for col_name, col_def in new_columns:
        if not await column_exists(session, "users", col_name):
            logger.info(f"  Adding column: users.{col_name}")
            await session.execute(text(
                f"ALTER TABLE users ADD COLUMN {col_name} {col_def}"
            ))
        else:
            logger.info(f"  Column users.{col_name} already exists — skipping")

    # Index on firm_id for tenant filtering performance
    await session.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_users_firm_id ON users (firm_id)
    """))
    logger.info("users table extended.")


# ──────────────────────────────────────────────
# Step 5 — Create firm_invitations table
# ──────────────────────────────────────────────

async def create_firm_invitations_table(session):
    if await table_exists(session, "firm_invitations"):
        logger.info("firm_invitations table already exists — skipping")
        return

    logger.info("Creating firm_invitations table...")
    await session.execute(text("""
        CREATE TABLE firm_invitations (
            id          VARCHAR PRIMARY KEY,
            firm_id     VARCHAR NOT NULL REFERENCES firms(id),
            email       VARCHAR NOT NULL,
            role        user_role_enum NOT NULL DEFAULT 'member',
            permissions JSONB,
            invited_by  VARCHAR NOT NULL REFERENCES users(id),
            token       VARCHAR NOT NULL UNIQUE,
            expires_at  TIMESTAMPTZ NOT NULL,
            accepted_at TIMESTAMPTZ
        )
    """))
    await session.execute(text(
        "CREATE INDEX idx_firm_invitations_firm_id ON firm_invitations (firm_id)"
    ))
    await session.execute(text(
        "CREATE INDEX idx_firm_invitations_email ON firm_invitations (email)"
    ))
    await session.execute(text(
        "CREATE INDEX idx_firm_invitations_token ON firm_invitations (token)"
    ))
    logger.info("firm_invitations table created.")


# ──────────────────────────────────────────────
# Step 6 — Seed default plan + backfill existing users
# ──────────────────────────────────────────────

async def backfill_existing_users(session):
    # Check if there are users with no firm_id
    result = await session.execute(text(
        "SELECT COUNT(*) FROM users WHERE firm_id IS NULL"
    ))
    unassigned = result.scalar()
    if unassigned == 0:
        logger.info("All users already have a firm_id — backfill not needed")
        return

    logger.info(f"Backfilling {unassigned} existing user(s) into a default firm...")

    # Seed a $0 starter plan if none exists
    result = await session.execute(text("SELECT id FROM plans LIMIT 1"))
    existing_plan = result.scalar()
    if not existing_plan:
        plan_id = str(uuid.uuid4())
        await session.execute(text("""
            INSERT INTO plans (id, name, price_cents, features, is_active)
            VALUES (:id, 'Starter', 0, '{}', TRUE)
        """), {"id": plan_id})
        logger.info(f"  Seeded default plan: {plan_id}")
    else:
        plan_id = existing_plan

    # Find or create the default firm
    result = await session.execute(text(
        "SELECT id FROM firms WHERE name = 'Default Firm' LIMIT 1"
    ))
    existing_firm = result.scalar()
    if not existing_firm:
        # Use the oldest user's email as the owner
        result = await session.execute(text(
            "SELECT email FROM users ORDER BY created_at ASC LIMIT 1"
        ))
        owner_email = result.scalar() or "admin@default.local"

        firm_id = str(uuid.uuid4())
        await session.execute(text("""
            INSERT INTO firms (id, name, owner_email, subscription_status, plan_id, seat_limit, is_active)
            VALUES (:id, 'Default Firm', :owner_email, 'active', :plan_id, 9999, TRUE)
        """), {"id": firm_id, "owner_email": owner_email, "plan_id": plan_id})
        logger.info(f"  Created default firm: {firm_id}")
    else:
        firm_id = existing_firm
        logger.info(f"  Using existing default firm: {firm_id}")

    # Assign all unassigned users to the default firm as members
    await session.execute(text("""
        UPDATE users
        SET firm_id = :firm_id,
            role    = 'member'
        WHERE firm_id IS NULL
    """), {"firm_id": firm_id})

    # Promote the owner_email user to firm_owner
    result = await session.execute(text(
        "SELECT owner_email FROM firms WHERE id = :fid"
    ), {"fid": firm_id})
    owner_email = result.scalar()
    await session.execute(text("""
        UPDATE users SET role = 'firm_owner'
        WHERE email = :email AND firm_id = :firm_id
    """), {"email": owner_email, "firm_id": firm_id})

    logger.info(f"  Backfilled {unassigned} user(s) into firm {firm_id}")


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────

async def run_migration():
    async with UserAsyncSessionLocal() as session:
        try:
            logger.info("Step 1/6 — Creating enums")
            await create_enums(session)

            logger.info("Step 2/6 — Creating plans table")
            await create_plans_table(session)

            logger.info("Step 3/6 — Creating firms table")
            await create_firms_table(session)

            logger.info("Step 4/6 — Extending users table")
            await extend_users_table(session)

            logger.info("Step 5/6 — Creating firm_invitations table")
            await create_firm_invitations_table(session)

            logger.info("Step 6/6 — Backfilling existing users")
            await backfill_existing_users(session)

            await session.commit()
            logger.info("Migration committed successfully.")

        except Exception as e:
            await session.rollback()
            logger.error(f"Migration failed: {e}")
            raise


async def main():
    logger.info("=" * 60)
    logger.info("Migration: add_paywall_db_schema")
    logger.info("=" * 60)
    try:
        await run_migration()
        code = 0
    except Exception:
        code = 1
    finally:
        await user_engine.dispose()
    logger.info("=" * 60)
    sys.exit(code)


if __name__ == "__main__":
    asyncio.run(main())
