"""
Migration: Add email verification columns to users table.

Adds: email_verified, email_verification_token, email_verification_expires_at
Backfills: sets email_verified = TRUE for all existing rows (pre-verified).

Usage:
    docker compose exec backend uv run python migrations/add_email_verification_to_users.py
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
            # Add columns (idempotent)
            new_columns = [
                ("email_verified",                "BOOLEAN NOT NULL DEFAULT FALSE"),
                ("email_verification_token",      "VARCHAR UNIQUE"),
                ("email_verification_expires_at", "TIMESTAMPTZ"),
            ]

            for col_name, col_def in new_columns:
                if not await column_exists(session, "users", col_name):
                    logger.info(f"Adding column: users.{col_name}")
                    await session.execute(text(
                        f"ALTER TABLE users ADD COLUMN {col_name} {col_def}"
                    ))
                else:
                    logger.info(f"Column users.{col_name} already exists — skipping")

            # Pre-verify all existing users (Decision 1 — existing users are pre-verified)
            result = await session.execute(text(
                "SELECT COUNT(*) FROM users WHERE email_verified = FALSE"
            ))
            unverified = result.scalar()
            if unverified and unverified > 0:
                logger.info(f"Pre-verifying {unverified} existing user(s)...")
                await session.execute(text(
                    "UPDATE users SET email_verified = TRUE WHERE email_verified = FALSE"
                ))
            else:
                logger.info("All existing users already verified — skipping backfill")

            await session.commit()
            logger.info("Migration committed successfully.")

        except Exception as e:
            await session.rollback()
            logger.error(f"Migration failed: {e}")
            raise


async def main():
    logger.info("=" * 60)
    logger.info("Migration: add_email_verification_to_users")
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
