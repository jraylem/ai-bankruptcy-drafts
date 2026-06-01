"""
Migration: Collaboration tables — Phase 4 Task 26.

Creates: firm_chat_rooms, firm_chat_messages, motion_comments tables in chat_db.

Prerequisites:
  - add_firm_id_to_chatbot_tables.py must have been run (motion_draft_logs exists)

Usage:
    docker compose exec backend uv run python migrations/add_collaboration_tables.py
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

from src.chatbot.database import AsyncSessionLocal

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
    async with AsyncSessionLocal() as session:

        # ── firm_chat_rooms ────────────────────────────────────────────────
        if not await table_exists(session, "firm_chat_rooms"):
            await session.execute(text("""
                CREATE TABLE firm_chat_rooms (
                    id                  VARCHAR PRIMARY KEY,
                    firm_id             VARCHAR NOT NULL,
                    name                VARCHAR NOT NULL,
                    linked_case_number  VARCHAR,
                    linked_motion_id    VARCHAR REFERENCES motion_draft_logs(id) ON DELETE SET NULL,
                    created_by          VARCHAR NOT NULL,
                    created_at          TIMESTAMPTZ DEFAULT NOW()
                )
            """))
            await session.execute(text(
                "CREATE INDEX idx_firm_chat_rooms_firm_id ON firm_chat_rooms(firm_id)"
            ))
            logger.info("Created table: firm_chat_rooms")
        else:
            logger.info("Table firm_chat_rooms already exists — skipping")

        # ── firm_chat_messages ─────────────────────────────────────────────
        if not await table_exists(session, "firm_chat_messages"):
            await session.execute(text("""
                CREATE TABLE firm_chat_messages (
                    id          VARCHAR PRIMARY KEY,
                    room_id     VARCHAR NOT NULL REFERENCES firm_chat_rooms(id) ON DELETE CASCADE,
                    user_id     VARCHAR NOT NULL,
                    content     TEXT NOT NULL,
                    created_at  TIMESTAMPTZ DEFAULT NOW()
                )
            """))
            await session.execute(text(
                "CREATE INDEX idx_firm_chat_messages_room_id ON firm_chat_messages(room_id)"
            ))
            logger.info("Created table: firm_chat_messages")
        else:
            logger.info("Table firm_chat_messages already exists — skipping")

        # ── motion_comments ────────────────────────────────────────────────
        if not await table_exists(session, "motion_comments"):
            await session.execute(text("""
                CREATE TABLE motion_comments (
                    id                    VARCHAR PRIMARY KEY,
                    motion_draft_log_id   VARCHAR NOT NULL REFERENCES motion_draft_logs(id) ON DELETE CASCADE,
                    user_id               VARCHAR NOT NULL,
                    content               TEXT NOT NULL,
                    created_at            TIMESTAMPTZ DEFAULT NOW(),
                    updated_at            TIMESTAMPTZ
                )
            """))
            await session.execute(text(
                "CREATE INDEX idx_motion_comments_motion_id ON motion_comments(motion_draft_log_id)"
            ))
            logger.info("Created table: motion_comments")
        else:
            logger.info("Table motion_comments already exists — skipping")

        await session.commit()
        logger.info("Migration complete.")


if __name__ == "__main__":
    asyncio.run(run())
