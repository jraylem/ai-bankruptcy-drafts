"""
Migration: Add notification and collaboration flag columns to settings tables.

Adds to user_settings:
  - notify_motion_approved  BOOLEAN NOT NULL DEFAULT TRUE
  - notify_motion_rejected   BOOLEAN NOT NULL DEFAULT TRUE

Adds to firm_settings:
  - enable_chat_rooms        BOOLEAN NOT NULL DEFAULT TRUE
  - enable_motion_comments   BOOLEAN NOT NULL DEFAULT TRUE

Usage:
    docker compose exec backend uv run python migrations/add_settings_notification_collab_flags.py
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

        # ── user_settings: notify_motion_approved ──────────────────────────
        if not await column_exists(session, "user_settings", "notify_motion_approved"):
            await session.execute(text("""
                ALTER TABLE user_settings
                ADD COLUMN notify_motion_approved BOOLEAN NOT NULL DEFAULT TRUE
            """))
            logger.info("Added column: user_settings.notify_motion_approved")
        else:
            logger.info("Column user_settings.notify_motion_approved already exists — skipping")

        # ── user_settings: notify_motion_rejected ──────────────────────────
        if not await column_exists(session, "user_settings", "notify_motion_rejected"):
            await session.execute(text("""
                ALTER TABLE user_settings
                ADD COLUMN notify_motion_rejected BOOLEAN NOT NULL DEFAULT TRUE
            """))
            logger.info("Added column: user_settings.notify_motion_rejected")
        else:
            logger.info("Column user_settings.notify_motion_rejected already exists — skipping")

        # ── firm_settings: enable_chat_rooms ───────────────────────────────
        if not await column_exists(session, "firm_settings", "enable_chat_rooms"):
            await session.execute(text("""
                ALTER TABLE firm_settings
                ADD COLUMN enable_chat_rooms BOOLEAN NOT NULL DEFAULT TRUE
            """))
            logger.info("Added column: firm_settings.enable_chat_rooms")
        else:
            logger.info("Column firm_settings.enable_chat_rooms already exists — skipping")

        # ── firm_settings: enable_motion_comments ──────────────────────────
        if not await column_exists(session, "firm_settings", "enable_motion_comments"):
            await session.execute(text("""
                ALTER TABLE firm_settings
                ADD COLUMN enable_motion_comments BOOLEAN NOT NULL DEFAULT TRUE
            """))
            logger.info("Added column: firm_settings.enable_motion_comments")
        else:
            logger.info("Column firm_settings.enable_motion_comments already exists — skipping")

        await session.commit()
        logger.info("Migration complete.")


if __name__ == "__main__":
    asyncio.run(run())
