"""
Migration: relax NOT NULL on user_activity_logs.firm_id

The backfill migration enforced NOT NULL on firm_id too early. The activity
logger is called from middleware for all requests — including anonymous ones —
and the code doesn't always have a firm_id to supply (JWT doesn't carry it yet).

This drops the NOT NULL constraint so inserts without firm_id no longer crash.
Existing data is unaffected; the backfill values remain.

Usage:
    docker compose exec backend uv run python migrations/relax_activity_log_firm_id_not_null.py
"""

import asyncio
import sys
from pathlib import Path

script_dir = Path(__file__).parent.absolute()
project_root = script_dir.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from sqlalchemy import text
from src.chatbot.database import engine
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


async def run():
    async with engine.begin() as conn:
        result = await conn.execute(text("""
            SELECT is_nullable
            FROM information_schema.columns
            WHERE table_name = 'user_activity_logs' AND column_name = 'firm_id'
        """))
        row = result.fetchone()
        if row is None:
            logger.error("Column user_activity_logs.firm_id does not exist — run add_firm_id_to_chatbot_tables.py first")
            return

        if row[0] == "YES":
            logger.info("user_activity_logs.firm_id is already nullable — nothing to do")
            return

        await conn.execute(text(
            "ALTER TABLE user_activity_logs ALTER COLUMN firm_id DROP NOT NULL"
        ))
        logger.info("Dropped NOT NULL constraint from user_activity_logs.firm_id")


if __name__ == "__main__":
    asyncio.run(run())
