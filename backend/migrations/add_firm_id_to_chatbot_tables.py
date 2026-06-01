"""
Migration: add firm_id to chatbot tables — Phase 1 Task 5.

Adds nullable firm_id VARCHAR column (with index) to:
  - sessions
  - chat_threads
  - pdf_documents
  - motion_draft_logs
  - user_activity_logs

Column is nullable at this stage. Run backfill_chatbot_firm_ids.py
afterwards to populate values and enforce NOT NULL.

Usage:
    docker compose exec backend uv run python migrations/add_firm_id_to_chatbot_tables.py
"""

import asyncio
import sys
from pathlib import Path

script_dir = Path(__file__).parent.absolute()
project_root = script_dir.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from sqlalchemy import text
from src.chatbot.database import engine, AsyncSessionLocal
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

TABLES = [
    "sessions",
    "chat_threads",
    "pdf_documents",
    "motion_draft_logs",
    "user_activity_logs",
]


async def column_exists(session, table_name: str, column_name: str) -> bool:
    result = await session.execute(text("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = :t AND column_name = :c
        )
    """), {"t": table_name, "c": column_name})
    return result.scalar()


async def run_migration():
    async with AsyncSessionLocal() as session:
        try:
            for table in TABLES:
                if not await column_exists(session, table, "firm_id"):
                    logger.info(f"  Adding firm_id to {table}")
                    await session.execute(text(
                        f"ALTER TABLE {table} ADD COLUMN firm_id VARCHAR"
                    ))
                    await session.execute(text(
                        f"CREATE INDEX IF NOT EXISTS idx_{table}_firm_id ON {table} (firm_id)"
                    ))
                else:
                    logger.info(f"  {table}.firm_id already exists — skipping")

            await session.commit()
            logger.info("Migration committed successfully.")

        except Exception as e:
            await session.rollback()
            logger.error(f"Migration failed: {e}")
            raise


async def main():
    logger.info("=" * 60)
    logger.info("Migration: add_firm_id_to_chatbot_tables")
    logger.info("=" * 60)
    try:
        await run_migration()
        code = 0
    except Exception:
        code = 1
    finally:
        await engine.dispose()
    logger.info("=" * 60)
    sys.exit(code)


if __name__ == "__main__":
    asyncio.run(main())
