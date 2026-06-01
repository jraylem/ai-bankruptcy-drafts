"""
Migration script to remove duplicate pdf_documents rows.

Keeps the latest row per (session_id, filename, petition_status) combination
and deletes all older duplicates. No data loss — only redundant rows are removed.

Usage:
    docker compose exec backend uv run python migrations/remove_duplicate_pdf_documents.py
"""

import asyncio
import sys
from pathlib import Path

script_dir = Path(__file__).parent.absolute()
project_root = script_dir.parent

if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from sqlalchemy import text
from src.config import settings
from src.chatbot.database import AsyncSessionLocal, engine
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def count_duplicates() -> int:
    async with AsyncSessionLocal() as session:
        result = await session.execute(text("""
            SELECT COUNT(*) FROM pdf_documents
            WHERE id NOT IN (
                SELECT DISTINCT ON (session_id, filename, petition_status) id
                FROM pdf_documents
                ORDER BY session_id, filename, petition_status, uploaded_at DESC NULLS LAST
            )
        """))
        return result.scalar()


async def remove_duplicates() -> int:
    async with AsyncSessionLocal() as session:
        try:
            result = await session.execute(text("""
                DELETE FROM pdf_documents
                WHERE id NOT IN (
                    SELECT DISTINCT ON (session_id, filename, petition_status) id
                    FROM pdf_documents
                    ORDER BY session_id, filename, petition_status, uploaded_at DESC NULLS LAST
                )
            """))
            await session.commit()
            return result.rowcount
        except Exception as e:
            await session.rollback()
            logger.error(f"Error removing duplicates: {e}")
            raise


async def main():
    try:
        logger.info("=" * 60)
        logger.info("Migration: Remove duplicate pdf_documents rows")
        logger.info("=" * 60)
        logger.info(f"Database: {settings.CHAT_DATABASE_HOST}:{settings.CHAT_DATABASE_PORT}/{settings.CHAT_DATABASE_DB}")

        duplicate_count = await count_duplicates()
        logger.info(f"Found {duplicate_count} duplicate row(s) to remove.")

        if duplicate_count == 0:
            logger.info("✅ No duplicates found. Migration not needed.")
            return 0

        deleted = await remove_duplicates()
        logger.info(f"✅ Deleted {deleted} duplicate row(s).")

        remaining = await count_duplicates()
        if remaining == 0:
            logger.info("=" * 60)
            logger.info("✅ Migration completed successfully!")
            logger.info("=" * 60)
            return 0
        else:
            logger.error(f"❌ {remaining} duplicate(s) still remain after migration.")
            return 1

    except Exception as e:
        logger.error(f"❌ Migration failed with error: {e}")
        logger.exception(e)
        return 1
    finally:
        await engine.dispose()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
