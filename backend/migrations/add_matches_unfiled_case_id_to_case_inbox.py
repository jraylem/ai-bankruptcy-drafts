"""
Migration: add case_inbox.matches_unfiled_case_id for Phase 2 unfiled-petition matching.

Populated by the matcher in case_inbox/ingest.py:_process_link when an
ECF notice arrives for a client who already has an unfiled petition
(same firm, same SSN last-4, fuzzy-name match >= 85%). Surfaces the
match in the paralegal's Accept/Reject confirm modal so they know the
court notice will merge into the existing unfiled case rather than
spawn a duplicate.

Schema:
  ALTER TABLE case_inbox ADD COLUMN matches_unfiled_case_id VARCHAR NULL;
  CREATE INDEX idx_case_inbox_matches_unfiled
    ON case_inbox (matches_unfiled_case_id)
    WHERE matches_unfiled_case_id IS NOT NULL;

Partial index because most rows have no match — keeps the index small.

Usage:
    docker compose exec backend uv run python migrations/add_matches_unfiled_case_id_to_case_inbox.py
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

from src.chatbot.database import AsyncSessionLocal, engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


async def column_exists(session, table: str, column: str) -> bool:
    result = await session.execute(
        text(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = :table
              AND column_name = :column
            """
        ),
        {"table": table, "column": column},
    )
    return result.first() is not None


async def index_exists(session, index_name: str) -> bool:
    result = await session.execute(
        text(
            """
            SELECT 1 FROM pg_indexes
            WHERE schemaname = 'public' AND indexname = :name
            """
        ),
        {"name": index_name},
    )
    return result.first() is not None


async def apply_migration() -> bool:
    async with AsyncSessionLocal() as session:
        try:
            if await column_exists(session, "case_inbox", "matches_unfiled_case_id"):
                logger.info("✅ Column 'matches_unfiled_case_id' already exists, skipping ALTER.")
            else:
                logger.info("Adding column case_inbox.matches_unfiled_case_id…")
                await session.execute(
                    text("ALTER TABLE case_inbox ADD COLUMN matches_unfiled_case_id VARCHAR NULL")
                )
                logger.info("✅ Column added.")

            if await index_exists(session, "idx_case_inbox_matches_unfiled"):
                logger.info("✅ Index 'idx_case_inbox_matches_unfiled' already exists, skipping.")
            else:
                logger.info("Creating partial index idx_case_inbox_matches_unfiled…")
                await session.execute(
                    text(
                        """
                        CREATE INDEX idx_case_inbox_matches_unfiled
                        ON case_inbox (matches_unfiled_case_id)
                        WHERE matches_unfiled_case_id IS NOT NULL
                        """
                    )
                )
                logger.info("✅ Index created.")

            await session.commit()
            return True
        except Exception as e:
            await session.rollback()
            logger.exception("❌ Migration failed: %s", e)
            raise


async def main() -> int:
    logger.info("=" * 60)
    logger.info("Migration: add_matches_unfiled_case_id_to_case_inbox")
    logger.info("=" * 60)
    try:
        ok = await apply_migration()
        if ok:
            logger.info("✅ Migration completed successfully.")
            return 0
        return 1
    finally:
        await engine.dispose()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
