"""
Migration: Drop NOT NULL constraint from users.firm_id.

Even though firm_name is required at registration, the user row is inserted
(firm_id = NULL) before create_firm() runs and backfills firm_id. The column
must allow NULL to survive that brief intermediate state.

Usage:
    docker compose exec backend uv run python migrations/relax_users_firm_id_not_null.py
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


async def run_migration():
    async with UserAsyncSessionLocal() as session:
        try:
            # Check if the column is already nullable
            result = await session.execute(text("""
                SELECT is_nullable
                FROM information_schema.columns
                WHERE table_name = 'users' AND column_name = 'firm_id'
            """))
            row = result.fetchone()
            if row and row[0] == "YES":
                logger.info("users.firm_id is already nullable — skipping")
            else:
                logger.info("Dropping NOT NULL constraint from users.firm_id...")
                await session.execute(text(
                    "ALTER TABLE users ALTER COLUMN firm_id DROP NOT NULL"
                ))
                logger.info("Done.")

            await session.commit()
            logger.info("Migration committed successfully.")

        except Exception as e:
            await session.rollback()
            logger.error(f"Migration failed: {e}")
            raise


async def main():
    logger.info("=" * 60)
    logger.info("Migration: relax_users_firm_id_not_null")
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
