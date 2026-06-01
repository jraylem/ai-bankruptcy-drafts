"""
Migration script to create pending_session_file_locks table.

This table enforces a DB-level PRIMARY KEY constraint on (user_id, file_path)
to prevent duplicate pending sessions being created from the same uploaded file
under concurrent API calls (race condition / thundering herd).

The backfill INSERT populates existing active pending sessions so the lock table
is immediately consistent after the migration runs.

This script must be run inside the Docker container because the configured
database hostnames only resolve on the Docker network.

Usage:
    docker compose exec backend uv run python migrations/add_pending_session_file_locks.py
    docker compose exec backend uv run python -m migrations.add_pending_session_file_locks
"""

import asyncio
import logging
import sys
from pathlib import Path

from sqlalchemy import text

# Determine project root and add it to sys.path for src imports.
script_dir = Path(__file__).parent.absolute()
project_root = script_dir.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.chatbot.database import AsyncSessionLocal, engine
from src.config import settings


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def check_table_exists() -> bool:
    async with AsyncSessionLocal() as session:
        try:
            result = await session.execute(
                text(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                    AND table_name = 'pending_session_file_locks'
                    """
                )
            )
            exists = result.fetchone() is not None
            await session.commit()
            return exists
        except Exception as e:
            await session.rollback()
            logger.error(f"Error checking if table exists: {e}")
            raise


async def create_table() -> None:
    async with AsyncSessionLocal() as session:
        try:
            logger.info("Creating pending_session_file_locks table...")
            await session.execute(
                text(
                    """
                    CREATE TABLE pending_session_file_locks (
                        user_id    TEXT        NOT NULL,
                        file_path  TEXT        NOT NULL,
                        session_id TEXT        NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        PRIMARY KEY (user_id, file_path)
                    )
                    """
                )
            )
            await session.commit()
            logger.info("Table created successfully.")
        except Exception as e:
            await session.rollback()
            logger.error(f"Error creating table: {e}")
            raise


async def backfill_existing_pending_sessions() -> int:
    """
    Populate the lock table from existing active pending sessions.

    For each (user_id, file_path) pair, keeps the oldest session so that the
    dedup logic in _archive_duplicate_pending_session retains the same winner
    it would have chosen.
    """
    async with AsyncSessionLocal() as session:
        try:
            logger.info("Backfilling existing active pending sessions...")
            result = await session.execute(
                text(
                    """
                    INSERT INTO pending_session_file_locks (user_id, file_path, session_id, created_at)
                    SELECT DISTINCT ON (s.user_id, pd.file_path)
                        s.user_id,
                        pd.file_path,
                        s.id,
                        s.created_at
                    FROM sessions s
                    JOIN pdf_documents pd ON pd.session_id = s.id
                    JOIN courtdrive_ingestions ci
                        ON ci.session_id = s.id
                        AND ci.ingestion_type = 'pending_acceptance'
                    WHERE s.is_active = true
                      AND pd.file_path IS NOT NULL
                      AND pd.file_path <> ''
                    ORDER BY s.user_id, pd.file_path, s.created_at ASC
                    ON CONFLICT DO NOTHING
                    """
                )
            )
            await session.commit()
            rows_inserted = result.rowcount if result.rowcount != -1 else 0
            logger.info(f"Backfilled {rows_inserted} row(s) into pending_session_file_locks.")
            return rows_inserted
        except Exception as e:
            await session.rollback()
            logger.error(f"Error backfilling existing sessions: {e}")
            raise


async def run_migration() -> bool:
    logger.info("Checking if pending_session_file_locks table already exists...")
    if await check_table_exists():
        logger.info("Table already exists. Skipping CREATE — running backfill only.")
        rows = await backfill_existing_pending_sessions()
        logger.info(f"Backfill complete ({rows} new row(s) inserted).")
        return True

    await create_table()
    await backfill_existing_pending_sessions()
    return await check_table_exists()


async def main() -> int:
    try:
        logger.info("=" * 60)
        logger.info("Migration: Create pending_session_file_locks table")
        logger.info("=" * 60)
        logger.info(
            f"Database: {settings.CHAT_DATABASE_HOST}:{settings.CHAT_DATABASE_PORT}/{settings.CHAT_DATABASE_DB}"
        )

        success = await run_migration()
        if success:
            logger.info("=" * 60)
            logger.info("Migration completed successfully.")
            logger.info("=" * 60)
            return 0

        logger.error("=" * 60)
        logger.error("Migration failed.")
        logger.error("=" * 60)
        return 1
    except Exception as e:
        logger.error(f"Migration failed with error: {e}")
        logger.exception(e)
        return 1
    finally:
        await engine.dispose()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
