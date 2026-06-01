"""
Migration: add allowed_domain to firms table.

Adds nullable allowed_domain VARCHAR column to firms.
When set, invite_member() restricts invitations to that domain only.
Default: NULL (no restriction — any email can be invited).

Usage:
    docker compose exec backend uv run python migrations/add_allowed_domain_to_firms.py
"""

import asyncio
import sys
from pathlib import Path

script_dir = Path(__file__).parent.absolute()
project_root = script_dir.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from sqlalchemy import text
from src.auth.database import user_engine, UserAsyncSessionLocal
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


async def run_migration():
    async with UserAsyncSessionLocal() as session:
        try:
            result = await session.execute(text("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'firms' AND column_name = 'allowed_domain'
                )
            """))
            if result.scalar():
                logger.info("Column firms.allowed_domain already exists — skipping")
            else:
                logger.info("Adding column: firms.allowed_domain")
                await session.execute(text(
                    "ALTER TABLE firms ADD COLUMN allowed_domain VARCHAR"
                ))
            await session.commit()
            logger.info("Migration committed successfully.")
        except Exception as e:
            await session.rollback()
            logger.error(f"Migration failed: {e}")
            raise


async def main():
    logger.info("=" * 60)
    logger.info("Migration: add_allowed_domain_to_firms")
    logger.info("=" * 60)
    try:
        await run_migration()
        code = 0
    except Exception:
        code = 1
    finally:
        await user_engine.dispose()
    logger.info("=" * 60)
    sys.exit(code)


if __name__ == "__main__":
    asyncio.run(main())
