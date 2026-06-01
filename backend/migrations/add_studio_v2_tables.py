"""
Migration: Studio V2 tables — Phase 1.

Creates: templates_v2, template_fields_v2 in the core database.

Idempotent — checks information_schema before each CREATE TABLE / CREATE
INDEX. Mirrors the pattern in migrations/add_billing_tables.py.

⚠️ IMPORTANT: Run inside Docker container.

Usage:
    docker compose exec backend uv run python migrations/add_studio_v2_tables.py
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

from src.chatbot.database import AsyncSessionLocal

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


async def index_exists(session, index_name: str) -> bool:
    result = await session.execute(text("""
        SELECT EXISTS (
            SELECT 1 FROM pg_indexes
            WHERE indexname = :i
        )
    """), {"i": index_name})
    return result.scalar()


async def run():
    async with AsyncSessionLocal() as session:
        # ── templates_v2 ────────────────────────────────────────────────

        if not await table_exists(session, "templates_v2"):
            await session.execute(text("""
                CREATE TABLE templates_v2 (
                    id                  VARCHAR PRIMARY KEY,
                    firm_id             VARCHAR,
                    name                VARCHAR(255) NOT NULL,
                    config              JSONB NOT NULL DEFAULT '{"role": "single", "companions": []}'::jsonb,
                    original_doc_url    TEXT,
                    template_doc_url    TEXT,
                    published_at        TIMESTAMPTZ,
                    published_spec      JSONB,
                    created_at          TIMESTAMPTZ DEFAULT NOW(),
                    updated_at          TIMESTAMPTZ DEFAULT NOW(),
                    is_active           BOOLEAN NOT NULL DEFAULT TRUE
                )
            """))
            logger.info("Created table: templates_v2")
        else:
            logger.info("Table templates_v2 already exists — skipping")

        if not await index_exists(session, "idx_templates_v2_name"):
            await session.execute(text(
                "CREATE INDEX idx_templates_v2_name ON templates_v2(name)"
            ))
            logger.info("Created index: idx_templates_v2_name")
        else:
            logger.info("Index idx_templates_v2_name already exists — skipping")

        if not await index_exists(session, "idx_templates_v2_firm_id"):
            await session.execute(text("""
                CREATE INDEX idx_templates_v2_firm_id ON templates_v2(firm_id)
                WHERE firm_id IS NOT NULL
            """))
            logger.info("Created index: idx_templates_v2_firm_id")
        else:
            logger.info("Index idx_templates_v2_firm_id already exists — skipping")

        if not await index_exists(session, "idx_templates_v2_published"):
            await session.execute(text("""
                CREATE INDEX idx_templates_v2_published ON templates_v2(published_at)
                WHERE published_at IS NOT NULL
            """))
            logger.info("Created index: idx_templates_v2_published")
        else:
            logger.info("Index idx_templates_v2_published already exists — skipping")

        # ── template_fields_v2 ─────────────────────────────────────────

        if not await table_exists(session, "template_fields_v2"):
            await session.execute(text("""
                CREATE TABLE template_fields_v2 (
                    id                                  VARCHAR PRIMARY KEY,
                    template_id                         VARCHAR NOT NULL
                        REFERENCES templates_v2(id) ON DELETE CASCADE,
                    template_variable                   VARCHAR(255) NOT NULL,
                    template_property_marker            TEXT,
                    template_property_marker_aliases    JSONB,
                    template_identifying_text_match     TEXT,
                    description                         TEXT,
                    template_index                      INTEGER NOT NULL DEFAULT 0,
                    params                              JSONB,
                    created_at                          TIMESTAMPTZ DEFAULT NOW(),
                    updated_at                          TIMESTAMPTZ DEFAULT NOW()
                )
            """))
            logger.info("Created table: template_fields_v2")
        else:
            logger.info("Table template_fields_v2 already exists — skipping")

        if not await index_exists(session, "uq_template_fields_v2_variable"):
            await session.execute(text("""
                CREATE UNIQUE INDEX uq_template_fields_v2_variable
                ON template_fields_v2(template_id, template_variable)
            """))
            logger.info("Created unique index: uq_template_fields_v2_variable")
        else:
            logger.info("Index uq_template_fields_v2_variable already exists — skipping")

        if not await index_exists(session, "idx_template_fields_v2_template_index"):
            await session.execute(text("""
                CREATE INDEX idx_template_fields_v2_template_index
                ON template_fields_v2(template_id, template_index)
            """))
            logger.info("Created index: idx_template_fields_v2_template_index")
        else:
            logger.info("Index idx_template_fields_v2_template_index already exists — skipping")

        await session.commit()
        logger.info("Migration complete.")


if __name__ == "__main__":
    asyncio.run(run())
