"""
Migration: Settings audit log table — Phase 4.

Creates: audit_logs table in user_db.
Tracks firm-level security and admin actions (member invited/removed,
settings changed, password changed, sessions revoked, billing changes).

This is distinct from the existing UserActivityLog (which tracks
document generation and API call analytics). The audit_logs table
is for firm admin accountability and security event history.

Usage:
    docker compose exec backend uv run python migrations/add_settings_audit_log_table.py
"""

import asyncio
import logging
import sys
from pathlib import Path

script_dir = Path(__file__).parent.absolute()
project_root = script_dir.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from sqlalchemy import text

from src.auth.database import UserAsyncSessionLocal

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


async def table_exists(session, table_name: str) -> bool:
    result = await session.execute(text("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_name = :t
        )
    """), {"t": table_name})
    return result.scalar()


async def run():
    async with UserAsyncSessionLocal() as session:

        # ── audit_logs ─────────────────────────────────────────────────────
        if not await table_exists(session, "audit_logs"):
            await session.execute(text("""
                CREATE TABLE audit_logs (
                    id              VARCHAR PRIMARY KEY,
                    firm_id         VARCHAR NOT NULL REFERENCES firms(id) ON DELETE CASCADE,
                    user_id         VARCHAR REFERENCES users(id) ON DELETE SET NULL,
                    action          VARCHAR NOT NULL,
                    resource_type   VARCHAR,
                    resource_id     VARCHAR,
                    metadata        JSONB,
                    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """))
            await session.execute(text(
                "CREATE INDEX idx_audit_logs_firm_id ON audit_logs(firm_id)"
            ))
            await session.execute(text(
                "CREATE INDEX idx_audit_logs_created_at ON audit_logs(created_at DESC)"
            ))
            logger.info("Created table: audit_logs")
        else:
            logger.info("Table audit_logs already exists — skipping")

        await session.commit()
        logger.info("Migration complete.")


if __name__ == "__main__":
    asyncio.run(run())
