"""
Migration script to add source column to pdf_documents table.

The source column records how a PDF entered the system:
  'manual'    — uploaded directly by the attorney via the UI
  'gdrive'    — retrieved from the Google Drive "Archived Petitions" folder
  'ecf'       — arrived automatically via ECF email / court mail downloader
  'courtdrive'— fetched via CourtDrive PACER lookup (reserved for future use)

NULL = unknown / legacy record; treated as 'manual' in dashboard queries.

Usage:
    docker compose exec backend uv run python migrations/add_source_to_pdf_documents.py
"""

import asyncio
import sys
import os
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


async def check_column_exists() -> bool:
    async with AsyncSessionLocal() as session:
        try:
            result = await session.execute(text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'pdf_documents'
                AND column_name = 'source'
            """))
            exists = result.fetchone() is not None
            await session.commit()
            return exists
        except Exception as e:
            await session.rollback()
            logger.error(f"Error checking if column exists: {e}")
            raise


async def add_source_column():
    async with AsyncSessionLocal() as session:
        try:
            logger.info("Checking if source column already exists...")
            if await check_column_exists():
                logger.info("✅ Column 'source' already exists in pdf_documents table. Migration not needed.")
                return True

            logger.info("Adding source column to pdf_documents table...")
            await session.execute(text("""
                ALTER TABLE pdf_documents
                ADD COLUMN source VARCHAR
            """))
            await session.commit()
            logger.info("✅ Successfully added source column to pdf_documents table!")

            if await check_column_exists():
                logger.info("✅ Verified: source column now exists in pdf_documents table.")
                return True
            else:
                logger.error("❌ Column was not added successfully.")
                return False

        except Exception as e:
            await session.rollback()
            logger.error(f"❌ Error adding source column: {e}")
            raise


async def main():
    try:
        logger.info("=" * 60)
        logger.info("Migration: Add source column to pdf_documents")
        logger.info("=" * 60)
        logger.info(f"Database: {settings.CHAT_DATABASE_HOST}:{settings.CHAT_DATABASE_PORT}/{settings.CHAT_DATABASE_DB}")

        success = await add_source_column()

        if success:
            logger.info("=" * 60)
            logger.info("✅ Migration completed successfully!")
            logger.info("=" * 60)
            return 0
        else:
            logger.error("=" * 60)
            logger.error("❌ Migration failed!")
            logger.error("=" * 60)
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
