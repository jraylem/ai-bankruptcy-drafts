"""
Migration script to add is_viewed column to courtdrive_ingestions table.

This script must be run inside the Docker container because the configured
database hostnames only resolve on the Docker network.

Usage:
    docker compose exec backend uv run python migrations/add_is_viewed_to_courtdrive_ingestions.py
    docker compose exec backend uv run python -m migrations.add_is_viewed_to_courtdrive_ingestions
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


async def check_column_exists() -> bool:
    """Check whether is_viewed exists on courtdrive_ingestions."""
    async with AsyncSessionLocal() as session:
        try:
            result = await session.execute(
                text(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name = 'courtdrive_ingestions'
                    AND column_name = 'is_viewed'
                    """
                )
            )
            exists = result.fetchone() is not None
            await session.commit()
            return exists
        except Exception as e:
            await session.rollback()
            logger.error(f"Error checking if is_viewed column exists: {e}")
            raise


async def add_is_viewed_column() -> bool:
    """Add is_viewed column to courtdrive_ingestions if missing."""
    async with AsyncSessionLocal() as session:
        try:
            logger.info("Checking if is_viewed column already exists...")
            if await check_column_exists():
                logger.info("Column 'is_viewed' already exists. Migration not needed.")
                return True

            logger.info("Adding is_viewed column to courtdrive_ingestions...")
            await session.execute(
                text(
                    """
                    ALTER TABLE courtdrive_ingestions
                    ADD COLUMN is_viewed BOOLEAN NOT NULL DEFAULT false
                    """
                )
            )
            await session.commit()

            if await check_column_exists():
                logger.info("Successfully added is_viewed column.")
                return True

            logger.error("Column verification failed after migration.")
            return False
        except Exception as e:
            await session.rollback()
            logger.error(f"Error adding is_viewed column: {e}")
            raise


async def main() -> int:
    """Run the migration."""
    try:
        logger.info("=" * 60)
        logger.info("Migration: Add is_viewed to courtdrive_ingestions")
        logger.info("=" * 60)
        logger.info(
            f"Database: {settings.CHAT_DATABASE_HOST}:{settings.CHAT_DATABASE_PORT}/{settings.CHAT_DATABASE_DB}"
        )

        success = await add_is_viewed_column()
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
