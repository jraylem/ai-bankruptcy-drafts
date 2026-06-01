"""
Migration: Add approval_token columns to users table.

Adds:
  - approval_token (VARCHAR UNIQUE NULLABLE)
  - approval_token_expires_at (TIMESTAMPTZ NULLABLE)

No backfill needed — existing users already have is_accepted=TRUE
from the prior add_is_accepted_to_users migration.

Usage:
    docker compose exec backend uv run python migrations/add_approval_token_to_users.py
"""

import asyncio
import sys
from pathlib import Path

script_dir = Path(__file__).parent.absolute()
project_root = script_dir.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import logging

from sqlalchemy import text

from src.auth.database import UserAsyncSessionLocal, user_engine

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
            if not await column_exists(session, "users", "approval_token"):
                logger.info("Adding column: users.approval_token")
                await session.execute(text(
                    "ALTER TABLE users ADD COLUMN approval_token VARCHAR UNIQUE"
                ))
            else:
                logger.info("Column users.approval_token already exists — skipping")

            if not await column_exists(session, "users", "approval_token_expires_at"):
                logger.info("Adding column: users.approval_token_expires_at")
                await session.execute(text(
                    "ALTER TABLE users ADD COLUMN approval_token_expires_at TIMESTAMPTZ"
                ))
            else:
                logger.info("Column users.approval_token_expires_at already exists — skipping")

            await session.commit()
            logger.info("Migration committed successfully.")

        except Exception as e:
            await session.rollback()
            logger.error(f"Migration failed: {e}")
            raise


async def main():
    logger.info("=" * 60)
    logger.info("Migration: add_approval_token_to_users")
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
