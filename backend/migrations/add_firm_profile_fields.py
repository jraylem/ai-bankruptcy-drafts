"""
Migration: Add profile fields to firms table.

Adds: address, firm_type, contact_number (all nullable)

Usage:
    docker compose exec backend uv run python migrations/add_firm_profile_fields.py
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
            new_columns = [
                ("address",        "VARCHAR"),
                ("firm_type",      "VARCHAR"),
                ("contact_number", "VARCHAR"),
            ]

            for col_name, col_def in new_columns:
                if not await column_exists(session, "firms", col_name):
                    logger.info(f"Adding column: firms.{col_name}")
                    await session.execute(text(
                        f"ALTER TABLE firms ADD COLUMN {col_name} {col_def}"
                    ))
                else:
                    logger.info(f"Column firms.{col_name} already exists — skipping")

            await session.commit()
            logger.info("Migration committed successfully.")

        except Exception as e:
            await session.rollback()
            logger.error(f"Migration failed: {e}")
            raise


async def main():
    logger.info("=" * 60)
    logger.info("Migration: add_firm_profile_fields")
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
