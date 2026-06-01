"""
Migration: Add cos_type column to motion_draft_logs.

cos_type captures whether the draft included a Certificate of Service and,
if so, whether a Notice of Hearing was also included.

Values:
  "WithNoticeOfHearing"    — motion with COS + Notice of Hearing
  "WithoutNoticeOfHearing" — motion with COS, no Notice of Hearing
  "No"                     — order, no COS requested
  NULL                     — task pending / failed / cancelled

Usage:
    docker compose exec backend uv run python migrations/add_cos_type_to_motion_draft_logs.py
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
                WHERE table_name = 'motion_draft_logs'
                AND column_name = 'cos_type'
            """))
            exists = result.fetchone() is not None
            await session.commit()
            return exists
        except Exception as e:
            await session.rollback()
            logger.error(f"Error checking if column exists: {e}")
            raise


async def add_cos_type_column():
    async with AsyncSessionLocal() as session:
        try:
            logger.info("Checking if cos_type column already exists...")
            if await check_column_exists():
                logger.info("✅ Column 'cos_type' already exists in motion_draft_logs table. Migration not needed.")
                return True

            logger.info("Adding cos_type column to motion_draft_logs table...")
            await session.execute(text("""
                ALTER TABLE motion_draft_logs
                ADD COLUMN cos_type VARCHAR(30) NULL
            """))
            await session.commit()
            logger.info("✅ Successfully added cos_type column to motion_draft_logs table!")

            if await check_column_exists():
                logger.info("✅ Verified: cos_type column now exists in motion_draft_logs table.")
                return True
            else:
                logger.error("❌ Column was not added successfully.")
                return False

        except Exception as e:
            await session.rollback()
            logger.error(f"❌ Error adding cos_type column: {e}")
            raise


async def main():
    try:
        logger.info("=" * 60)
        logger.info("Migration: Add cos_type column to motion_draft_logs")
        logger.info("=" * 60)
        logger.info(f"Database: {settings.CHAT_DATABASE_HOST}:{settings.CHAT_DATABASE_PORT}/{settings.CHAT_DATABASE_DB}")

        success = await add_cos_type_column()

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
