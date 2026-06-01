"""
Migration: Add is_accepted column to users table.

Adds: is_accepted (BOOLEAN NOT NULL DEFAULT FALSE)
Backfills: sets is_accepted = TRUE for all existing rows so current users
           aren't locked out after deployment.

Usage:
    docker compose exec backend uv run python migrations/add_is_accepted_to_users.py
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
            if not await column_exists(session, "users", "is_accepted"):
                logger.info("Adding column: users.is_accepted")
                await session.execute(text(
                    "ALTER TABLE users ADD COLUMN is_accepted BOOLEAN NOT NULL DEFAULT FALSE"
                ))
            else:
                logger.info("Column users.is_accepted already exists — skipping")

            # Pre-accept all existing users so they aren't locked out after deploy.
            result = await session.execute(text(
                "SELECT COUNT(*) FROM users WHERE is_accepted = FALSE"
            ))
            pending = result.scalar()
            if pending and pending > 0:
                logger.info(f"Pre-accepting {pending} existing user(s)...")
                await session.execute(text(
                    "UPDATE users SET is_accepted = TRUE WHERE is_accepted = FALSE"
                ))
            else:
                logger.info("All existing users already accepted — skipping backfill")

            await session.commit()
            logger.info("Migration committed successfully.")

        except Exception as e:
            await session.rollback()
            logger.error(f"Migration failed: {e}")
            raise


async def main():
    logger.info("=" * 60)
    logger.info("Migration: add_is_accepted_to_users")
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
