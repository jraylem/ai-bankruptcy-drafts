"""
Migration: Settings tables — Phase 4.

Creates: user_settings, firm_settings tables in user_db.

Usage:
    docker compose exec backend uv run python migrations/add_settings_tables.py
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


async def table_exists(session, table_name: str) -> bool:
    result = await session.execute(text("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_name = :t
        )
    """), {"t": table_name})
    return result.scalar()


async def run():
    async with UserAsyncSessionLocal() as session:

        # ── user_settings ──────────────────────────────────────────────────
        if not await table_exists(session, "user_settings"):
            await session.execute(text("""
                CREATE TABLE user_settings (
                    user_id                VARCHAR PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                    notification_email     BOOLEAN NOT NULL DEFAULT TRUE,
                    notification_inapp     BOOLEAN NOT NULL DEFAULT TRUE,
                    theme                  VARCHAR NOT NULL DEFAULT 'light',
                    updated_at             TIMESTAMPTZ
                )
            """))
            logger.info("Created table: user_settings")
        else:
            logger.info("Table user_settings already exists — skipping")

        # ── firm_settings ──────────────────────────────────────────────────
        if not await table_exists(session, "firm_settings"):
            await session.execute(text("""
                CREATE TABLE firm_settings (
                    firm_id                    VARCHAR PRIMARY KEY REFERENCES firms(id) ON DELETE CASCADE,
                    allow_member_invites       BOOLEAN NOT NULL DEFAULT FALSE,
                    motion_approval_required   BOOLEAN NOT NULL DEFAULT FALSE,
                    updated_at                 TIMESTAMPTZ
                )
            """))
            logger.info("Created table: firm_settings")
        else:
            logger.info("Table firm_settings already exists — skipping")

        await session.commit()
        logger.info("Migration complete.")


if __name__ == "__main__":
    asyncio.run(run())
