"""
Migration: enforce DB-level dedup on case_inbox.

Adds two partial UNIQUE indexes that prevent the
"check-then-insert" race that bypasses the Python-side dedup in
`CaseInboxRepository.find_by_gmail_message_id` and
`find_by_fingerprint`:

  - uq_case_inbox_gmail_message_id
      UNIQUE (gmail_message_id) WHERE gmail_message_id IS NOT NULL
      Two cron cycles (or a cycle + manual invocation) can't both
      insert a case_inbox row for the same Gmail message any more.

  - uq_case_inbox_firm_fingerprint
      UNIQUE (firm_id, fingerprint_sha256)
      WHERE fingerprint_sha256 IS NOT NULL
      Same PDF arriving via different emails can't double-insert.

Partial because the columns are nullable; PG partial uniques only
apply to rows where the column has a value.

IMPORTANT: this migration FAILS if duplicate rows already exist for
either key. Run the duplicate cleanup SQL FIRST (see
case_inbox_duplicate_cleanup.sql in the repo root or the docs).

Usage:
    docker compose exec backend uv run python migrations/add_case_inbox_dedup_unique_indexes.py
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


async def find_duplicates(session) -> tuple[int, int]:
    """Return (gmail_dupes, fingerprint_dupes) counts. Non-zero blocks the migration."""
    gmail_result = await session.execute(
        text(
            """
            SELECT count(*) FROM (
                SELECT gmail_message_id
                FROM case_inbox
                WHERE gmail_message_id IS NOT NULL
                GROUP BY gmail_message_id
                HAVING count(*) > 1
            ) t
            """
        )
    )
    gmail_dupes = gmail_result.scalar() or 0

    fp_result = await session.execute(
        text(
            """
            SELECT count(*) FROM (
                SELECT firm_id, fingerprint_sha256
                FROM case_inbox
                WHERE fingerprint_sha256 IS NOT NULL
                GROUP BY firm_id, fingerprint_sha256
                HAVING count(*) > 1
            ) t
            """
        )
    )
    fp_dupes = fp_result.scalar() or 0

    return gmail_dupes, fp_dupes


async def create_unique_indexes() -> bool:
    async with AsyncSessionLocal() as session:
        try:
            logger.info("Checking for existing duplicates that would block the unique constraint…")
            gmail_dupes, fp_dupes = await find_duplicates(session)
            if gmail_dupes or fp_dupes:
                logger.error(
                    "❌ Duplicates detected: %d gmail_message_id group(s), "
                    "%d (firm_id, fingerprint) group(s). "
                    "Clean these up before re-running this migration.",
                    gmail_dupes, fp_dupes,
                )
                logger.error(
                    "See `case_inbox_duplicate_cleanup.sql` for the cleanup query."
                )
                return False

            for index_name, ddl in (
                (
                    "uq_case_inbox_gmail_message_id",
                    """
                    CREATE UNIQUE INDEX uq_case_inbox_gmail_message_id
                    ON case_inbox (gmail_message_id)
                    WHERE gmail_message_id IS NOT NULL
                    """,
                ),
                (
                    "uq_case_inbox_firm_fingerprint",
                    """
                    CREATE UNIQUE INDEX uq_case_inbox_firm_fingerprint
                    ON case_inbox (firm_id, fingerprint_sha256)
                    WHERE fingerprint_sha256 IS NOT NULL
                    """,
                ),
            ):
                if await index_exists(session, index_name):
                    logger.info("✅ Index '%s' already exists, skipping.", index_name)
                    continue
                logger.info("Creating index '%s'…", index_name)
                await session.execute(text(ddl))
                logger.info("✅ Created '%s'.", index_name)

            await session.commit()
            return True
        except Exception as e:
            await session.rollback()
            logger.exception("❌ Migration failed: %s", e)
            raise


async def main() -> int:
    logger.info("=" * 60)
    logger.info("Migration: add_case_inbox_dedup_unique_indexes")
    logger.info("=" * 60)
    try:
        ok = await create_unique_indexes()
        if ok:
            logger.info("✅ Migration completed successfully.")
            return 0
        logger.error("❌ Migration aborted; resolve duplicates and retry.")
        return 1
    finally:
        await engine.dispose()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
