"""
Migration: backfill firm_id on all tenant-scoped tables — Phase 1 Task 6.

Runs against both DBs sequentially:

Phase A — Auth DB (user_db):
  1. Fetch default firm ID (firms where name = 'Default Firm')
  2. Backfill any users still missing firm_id
  3. Enforce NOT NULL on users.firm_id

Phase B — Chatbot DB (chat_db):
  1. Backfill all 5 tables with the default firm ID
  2. Enforce NOT NULL on each table's firm_id column

Prerequisites:
  - add_paywall_db_schema.py must have been run (firms + users.firm_id exist)
  - add_firm_id_to_chatbot_tables.py must have been run (chatbot tables have firm_id column)

Usage:
    docker compose exec backend uv run python migrations/backfill_chatbot_firm_ids.py
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
from src.chatbot.database import engine, AsyncSessionLocal
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

CHATBOT_TABLES = [
    "sessions",
    "chat_threads",
    "pdf_documents",
    "motion_draft_logs",
    "user_activity_logs",
]


async def phase_a_auth_db() -> str:
    """Backfill users and return the default firm ID."""
    async with UserAsyncSessionLocal() as session:
        try:
            # Fetch default firm
            result = await session.execute(text(
                "SELECT id FROM firms WHERE name = 'Default Firm' LIMIT 1"
            ))
            firm_id = result.scalar()
            if not firm_id:
                raise RuntimeError(
                    "No 'Default Firm' found in firms table. "
                    "Run add_paywall_db_schema.py first."
                )
            logger.info(f"Phase A — Using default firm: {firm_id}")

            # Backfill any remaining unassigned users
            result = await session.execute(text(
                "SELECT COUNT(*) FROM users WHERE firm_id IS NULL"
            ))
            unassigned = result.scalar()
            if unassigned > 0:
                logger.info(f"  Backfilling {unassigned} user(s) with firm_id")
                await session.execute(text("""
                    UPDATE users SET firm_id = :fid WHERE firm_id IS NULL
                """), {"fid": firm_id})
            else:
                logger.info("  All users already have firm_id — skipping backfill")

            # Enforce NOT NULL
            logger.info("  Enforcing NOT NULL on users.firm_id")
            await session.execute(text(
                "ALTER TABLE users ALTER COLUMN firm_id SET NOT NULL"
            ))

            await session.commit()
            logger.info("Phase A committed.")
            return firm_id

        except Exception as e:
            await session.rollback()
            logger.error(f"Phase A failed: {e}")
            raise


async def phase_b_chatbot_db(firm_id: str):
    """Backfill chatbot tables and enforce NOT NULL."""
    async with AsyncSessionLocal() as session:
        try:
            # Backfill each table
            for table in CHATBOT_TABLES:
                result = await session.execute(text(
                    f"SELECT COUNT(*) FROM {table} WHERE firm_id IS NULL"
                ))
                unassigned = result.scalar()
                if unassigned > 0:
                    logger.info(f"  Backfilling {unassigned} row(s) in {table}")
                    await session.execute(text(
                        f"UPDATE {table} SET firm_id = :fid WHERE firm_id IS NULL"
                    ), {"fid": firm_id})
                else:
                    logger.info(f"  {table}: all rows already have firm_id — skipping backfill")

            # Enforce NOT NULL on each table
            for table in CHATBOT_TABLES:
                logger.info(f"  Enforcing NOT NULL on {table}.firm_id")
                await session.execute(text(
                    f"ALTER TABLE {table} ALTER COLUMN firm_id SET NOT NULL"
                ))

            await session.commit()
            logger.info("Phase B committed.")

        except Exception as e:
            await session.rollback()
            logger.error(f"Phase B failed: {e}")
            raise


async def main():
    logger.info("=" * 60)
    logger.info("Migration: backfill_chatbot_firm_ids")
    logger.info("=" * 60)
    code = 0
    try:
        firm_id = await phase_a_auth_db()
        await phase_b_chatbot_db(firm_id)
        logger.info("All phases completed successfully.")
    except Exception:
        code = 1
    finally:
        await user_engine.dispose()
        await engine.dispose()
    logger.info("=" * 60)
    sys.exit(code)


if __name__ == "__main__":
    asyncio.run(main())
