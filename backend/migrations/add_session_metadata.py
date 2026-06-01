"""
Migration: Session metadata — Phase 4.

Adds ip_address and user_agent columns to refresh_sessions in user_db.
These columns power the active sessions list in Settings > Security.

Usage:
    docker compose exec backend uv run python migrations/add_session_metadata.py
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


async def column_exists(session, table_name: str, column_name: str) -> bool:
    result = await session.execute(text("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = :t AND column_name = :c
        )
    """), {"t": table_name, "c": column_name})
    return result.scalar()


async def run():
    async with UserAsyncSessionLocal() as session:

        if not await column_exists(session, "refresh_sessions", "ip_address"):
            await session.execute(text(
                "ALTER TABLE refresh_sessions ADD COLUMN ip_address VARCHAR"
            ))
            logger.info("Added column: refresh_sessions.ip_address")
        else:
            logger.info("Column ip_address already exists — skipping")

        if not await column_exists(session, "refresh_sessions", "user_agent"):
            await session.execute(text(
                "ALTER TABLE refresh_sessions ADD COLUMN user_agent VARCHAR"
            ))
            logger.info("Added column: refresh_sessions.user_agent")
        else:
            logger.info("Column user_agent already exists — skipping")

        await session.commit()
        logger.info("Migration complete.")


if __name__ == "__main__":
    asyncio.run(run())
