"""
Migration: add onboarding_status to firms table.

Adds onboarding_status_enum type and onboarding_status column to firms.
Default value: 'pending'. All existing firms are set to 'pending'.

Usage:
    docker compose exec backend uv run python migrations/add_onboarding_status_to_firms.py
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


async def enum_exists(session, enum_name: str) -> bool:
    result = await session.execute(text("""
        SELECT EXISTS (
            SELECT 1 FROM pg_type WHERE typname = :e
        )
    """), {"e": enum_name})
    return result.scalar()


async def column_exists(session, table_name: str, column_name: str) -> bool:
    result = await session.execute(text("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = :t AND column_name = :c
        )
    """), {"t": table_name, "c": column_name})
    return result.scalar()


async def run_migration():
    async with UserAsyncSessionLocal() as session:
        try:
            if not await enum_exists(session, "onboarding_status_enum"):
                logger.info("Creating enum: onboarding_status_enum")
                await session.execute(text("""
                    CREATE TYPE onboarding_status_enum AS ENUM ('pending', 'completed')
                """))
            else:
                logger.info("Enum onboarding_status_enum already exists — skipping")

            if not await column_exists(session, "firms", "onboarding_status"):
                logger.info("Adding column: firms.onboarding_status")
                await session.execute(text("""
                    ALTER TABLE firms
                    ADD COLUMN onboarding_status onboarding_status_enum NOT NULL DEFAULT 'pending'
                """))
            else:
                logger.info("Column firms.onboarding_status already exists — skipping")

            await session.commit()
            logger.info("Migration committed successfully.")

        except Exception as e:
            await session.rollback()
            logger.error(f"Migration failed: {e}")
            raise


async def main():
    logger.info("=" * 60)
    logger.info("Migration: add_onboarding_status_to_firms")
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
