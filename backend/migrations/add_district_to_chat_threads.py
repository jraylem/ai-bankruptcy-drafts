"""
Migration script to add district column to chat_threads table.

The district column stores the court district code (flsb, flmb, flnb, pawb)
derived from the sender email of the court notification that originated the case.
The column is nullable — existing records and manually uploaded sessions will have NULL.

Usage:
    docker compose exec backend uv run python migrations/add_district_to_chat_threads.py
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
                WHERE table_name = 'chat_threads'
                AND column_name = 'district'
            """))
            exists = result.fetchone() is not None
            await session.commit()
            return exists
        except Exception as e:
            await session.rollback()
            logger.error(f"Error checking if column exists: {e}")
            raise


async def add_district_column():
    async with AsyncSessionLocal() as session:
        try:
            logger.info("Checking if district column already exists...")
            if await check_column_exists():
                logger.info("✅ Column 'district' already exists in chat_threads table. Migration not needed.")
                return True

            logger.info("Adding district column to chat_threads table...")
            await session.execute(text("""
                ALTER TABLE chat_threads
                ADD COLUMN district VARCHAR
            """))
            await session.commit()
            logger.info("✅ Successfully added district column to chat_threads table!")

            if await check_column_exists():
                logger.info("✅ Verified: district column now exists in chat_threads table.")
                return True
            else:
                logger.error("❌ Column was not added successfully.")
                return False

        except Exception as e:
            await session.rollback()
            logger.error(f"❌ Error adding district column: {e}")
            raise


async def main():
    try:
        logger.info("=" * 60)
        logger.info("Migration: Add district column to chat_threads")
        logger.info("=" * 60)
        logger.info(f"Database: {settings.CHAT_DATABASE_HOST}:{settings.CHAT_DATABASE_PORT}/{settings.CHAT_DATABASE_DB}")

        success = await add_district_column()

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
