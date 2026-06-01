"""
Migration: create user_activity_logs table.

Tracks meaningful user actions for dashboard activity metrics and audit trail.

Usage:
    docker compose exec backend uv run python migrations/add_user_activity_logs.py
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
                WHERE table_name = 'user_activity_logs'
            )
        """))
        return result.scalar()


async def create_table():
    async with AsyncSessionLocal() as session:
        try:
            logger.info("Checking if user_activity_logs table already exists...")
            if await table_exists():
                logger.info("✅ Table already exists. Migration not needed.")
                return True

            logger.info("Creating user_activity_logs table...")
            await session.execute(text("""
                CREATE TABLE user_activity_logs (
                    id          VARCHAR PRIMARY KEY,
                    user_id     VARCHAR,
                    session_id  VARCHAR,
                    action      VARCHAR NOT NULL,
                    metadata    JSONB,
                    created_at  TIMESTAMPTZ DEFAULT NOW()
                )
            """))
            await session.execute(text("CREATE INDEX idx_activity_user_id    ON user_activity_logs (user_id)"))
            await session.execute(text("CREATE INDEX idx_activity_action      ON user_activity_logs (action)"))
            await session.execute(text("CREATE INDEX idx_activity_created_at  ON user_activity_logs (created_at)"))
            await session.commit()
            logger.info("✅ Table and indexes created successfully.")
            return True

        except Exception as e:
            await session.rollback()
            logger.error(f"❌ Error creating table: {e}")
            raise


async def main():
    logger.info("=" * 60)
    logger.info("Migration: create user_activity_logs")
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
