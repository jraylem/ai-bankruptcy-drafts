"""
Migration: Add paywall_enabled flag to firm_settings.

Adds to firm_settings:
  - paywall_enabled  BOOLEAN NOT NULL DEFAULT TRUE

Set to FALSE for a firm to bypass the subscription gate entirely.

Usage:
    docker compose exec backend uv run python migrations/add_paywall_enabled_to_firm_settings.py
"""

import asyncio
import logging
import sys
from pathlib import Path

script_dir = Path(__file__).parent.absolute()
project_root = script_dir.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from sqlalchemy import text

from src.auth.database import UserAsyncSessionLocal

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


async def column_exists(session, table: str, column: str) -> bool:
    result = await session.execute(text("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = :t AND column_name = :c
        )
    """), {"t": table, "c": column})
    return result.scalar()


async def run():
    async with UserAsyncSessionLocal() as session:

        if not await column_exists(session, "firm_settings", "paywall_enabled"):
            await session.execute(text("""
                ALTER TABLE firm_settings
                ADD COLUMN paywall_enabled BOOLEAN NOT NULL DEFAULT TRUE
            """))
            logger.info("Added column: firm_settings.paywall_enabled")
        else:
            logger.info("Column firm_settings.paywall_enabled already exists — skipping")

        await session.commit()
        logger.info("Migration complete.")


if __name__ == "__main__":
    asyncio.run(run())
