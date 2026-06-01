"""
Migration: create dashboard_chat_messages table.

Persists dashboard AI chat history per user + date-range key so that
conversations survive server restarts and work across multiple workers.

Usage:
    docker compose exec backend uv run python migrations/add_dashboard_chat_messages.py
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

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


async def table_exists() -> bool:
    async with AsyncSessionLocal() as session:
        result = await session.execute(text("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'dashboard_chat_messages'
            )
        """))
        return result.scalar()


async def column_exists(column: str) -> bool:
    async with AsyncSessionLocal() as session:
        result = await session.execute(text("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'dashboard_chat_messages'
                  AND column_name = :col
            )
        """), {"col": column})
        return result.scalar()


async def create_table():
    async with AsyncSessionLocal() as session:
        try:
            logger.info("Checking if dashboard_chat_messages table already exists...")
            if await table_exists():
                logger.info("Table already exists — checking for missing columns...")

                if not await column_exists("user_email"):
                    logger.info("Adding missing user_email column...")
                    await session.execute(text(
                        "ALTER TABLE dashboard_chat_messages ADD COLUMN user_email VARCHAR"
                    ))
                    await session.commit()
                    logger.info("✅ user_email column added.")
                else:
                    logger.info("✅ All columns present. Nothing to do.")

                return True

            logger.info("Creating dashboard_chat_messages table...")
            await session.execute(text("""
                CREATE TABLE dashboard_chat_messages (
                    id         VARCHAR PRIMARY KEY,
                    user_id    VARCHAR NOT NULL,
                    user_email VARCHAR,
                    range_key  VARCHAR NOT NULL,
                    role       VARCHAR NOT NULL,
                    content    TEXT    NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """))
            await session.execute(text(
                "CREATE INDEX ix_dashboard_chat_user_range "
                "ON dashboard_chat_messages (user_id, range_key)"
            ))
            await session.commit()
            logger.info("✅ Table and index created successfully.")
            return True

        except Exception as e:
            await session.rollback()
            logger.error(f"❌ Error creating table: {e}")
            raise


async def main():
    logger.info("=" * 60)
    logger.info("Migration: create dashboard_chat_messages")
    logger.info("=" * 60)
    logger.info(f"Database: {settings.CHAT_DATABASE_HOST}:{settings.CHAT_DATABASE_PORT}/{settings.CHAT_DATABASE_DB}")
    try:
        success = await create_table()
        code = 0 if success else 1
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        code = 1
    finally:
        await engine.dispose()
    logger.info("=" * 60)
    sys.exit(code)


if __name__ == "__main__":
    asyncio.run(main())
