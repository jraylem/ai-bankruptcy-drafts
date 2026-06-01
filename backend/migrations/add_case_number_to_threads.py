"""
Migration script to add case_number column to chat_threads table.

This script adds the case_number column to the chat_threads table in the chat database.
The column is nullable, so existing records will have NULL values.

⚠️ IMPORTANT: This script must be run INSIDE the Docker container because:
   - Database hostnames (chat_db) only resolve inside the Docker network
   - The .env configuration uses Docker service names as hosts

Usage:
    # Run inside Docker container (REQUIRED):
    # Use 'uv run python' since the project uses uv package manager
    docker compose exec backend uv run python migrations/add_case_number_to_threads.py
    
    # Or using module syntax:
    docker compose exec backend uv run python -m migrations.add_case_number_to_threads
"""

import asyncio
import sys
import os
from pathlib import Path

# Determine the project root directory
# When run from Docker, we're typically in /app
# When run from host, we're in ai-chatbot-be directory
script_dir = Path(__file__).parent.absolute()
project_root = script_dir.parent

# Add the project root to Python path so we can import from src
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from sqlalchemy import text
from src.config import settings
from src.chatbot.database import AsyncSessionLocal, engine
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def check_column_exists() -> bool:
    """Check if case_number column already exists in chat_threads table."""
    async with AsyncSessionLocal() as session:
        try:
            # Query to check if column exists (PostgreSQL specific)
            result = await session.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'chat_threads' 
                AND column_name = 'case_number'
            """))
            exists = result.fetchone() is not None
            await session.commit()
            return exists
        except Exception as e:
            await session.rollback()
            logger.error(f"Error checking if column exists: {e}")
            raise


async def add_case_number_column():
    """Add case_number column to chat_threads table."""
    async with AsyncSessionLocal() as session:
        try:
            logger.info("Checking if case_number column already exists...")
            
            # Check if column already exists
            column_exists = await check_column_exists()
            
            if column_exists:
                logger.info("✅ Column 'case_number' already exists in chat_threads table. Migration not needed.")
                return True
            
            logger.info("Adding case_number column to chat_threads table...")
            
            # Add the column (PostgreSQL syntax with IF NOT EXISTS)
            # Note: PostgreSQL doesn't support IF NOT EXISTS for ALTER TABLE ADD COLUMN
            # So we check manually above
            await session.execute(text("""
                ALTER TABLE chat_threads 
                ADD COLUMN case_number VARCHAR
            """))
            
            await session.commit()
            logger.info("✅ Successfully added case_number column to chat_threads table!")
            
            # Verify the column was added
            column_exists = await check_column_exists()
            if column_exists:
                logger.info("✅ Verified: case_number column now exists in chat_threads table.")
                return True
            else:
                logger.error("❌ Column was not added successfully.")
                return False
                
        except Exception as e:
            await session.rollback()
            logger.error(f"❌ Error adding case_number column: {e}")
            raise


async def main():
    """Main migration function."""
    try:
        logger.info("=" * 60)
        logger.info("Migration: Add case_number column to chat_threads")
        logger.info("=" * 60)
        logger.info(f"Database: {settings.CHAT_DATABASE_HOST}:{settings.CHAT_DATABASE_PORT}/{settings.CHAT_DATABASE_DB}")
        
        success = await add_case_number_column()
        
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
        # Close the engine
        await engine.dispose()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

