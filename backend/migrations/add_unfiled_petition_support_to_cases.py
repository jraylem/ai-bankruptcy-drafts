"""
Migration: Phase 1 of the unfiled-petitions epic.

Extends the `cases` table to support unfiled petitions (manual uploads
or BKDrafts@ email intake) that don't yet have a docket number. The PK
becomes a UUID; sanitized case_number lives on `legacy_id` for back-compat.
Adds matching keys (`firm_id`, `ssn_last4`, `status`) the Phase 2 matcher
will use to attach incoming ECF notices to existing unfiled rows.

Operations (single transaction):
  1. Column additions on cases (firm_id, ssn_last4, ssn_extraction_status,
     status, legacy_id) + relax case_number / collection columns to NULL
  2. Indexes (idx_cases_firm_id, idx_cases_status, idx_cases_legacy_id,
     composite idx_cases_ssn_match, partial UNIQUE uq_cases_case_number)
  3. Drop the case_sessions.case_id FK, rewrite cases.id (and all
     references) to UUIDs preserving the old slug in legacy_id, re-add FK
  4. Backfill firm_id := settings.DEFAULT_INTAKE_FIRM_ID on every legacy row

Preflight checks:
  - case_number duplicates among existing rows → abort (cases.id PK
    already enforces uniqueness, so 0 is expected, but verify defensively)
  - settings.DEFAULT_INTAKE_FIRM_ID required if any cases rows exist

Idempotent: re-running detects column existence, UUID format on cases.id,
unique index presence, and zero NULL firm_ids — all no-op if already
applied.

Usage:
    docker compose exec backend uv run python migrations/add_unfiled_petition_support_to_cases.py
"""

import asyncio
import logging
import re
import sys
import uuid
from pathlib import Path

script_dir = Path(__file__).parent.absolute()
project_root = script_dir.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from sqlalchemy import text

from src.chatbot.database import AsyncSessionLocal, engine
from src.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


async def column_exists(session, table_name: str, column_name: str) -> bool:
    result = await session.execute(
        text(
            "SELECT EXISTS ("
            "  SELECT 1 FROM information_schema.columns "
            "  WHERE table_name = :t AND column_name = :c"
            ")"
        ),
        {"t": table_name, "c": column_name},
    )
    return bool(result.scalar())


async def index_exists(session, index_name: str) -> bool:
    result = await session.execute(
        text(
            "SELECT 1 FROM pg_indexes "
            "WHERE schemaname = 'public' AND indexname = :name"
        ),
        {"name": index_name},
    )
    return result.first() is not None


async def constraint_exists(session, table_name: str, constraint_name: str) -> bool:
    result = await session.execute(
        text(
            "SELECT 1 FROM information_schema.table_constraints "
            "WHERE table_name = :t AND constraint_name = :c"
        ),
        {"t": table_name, "c": constraint_name},
    )
    return result.first() is not None


async def find_case_number_duplicates(session) -> int:
    result = await session.execute(
        text(
            "SELECT count(*) FROM ("
            "  SELECT case_number FROM cases "
            "  WHERE case_number IS NOT NULL "
            "  GROUP BY case_number "
            "  HAVING count(*) > 1"
            ") t"
        )
    )
    return int(result.scalar() or 0)


async def count_cases(session) -> int:
    result = await session.execute(text("SELECT count(*) FROM cases"))
    return int(result.scalar() or 0)


async def all_ids_are_uuid(session) -> bool:
    """Idempotency probe — every row's id must match the UUID pattern."""
    result = await session.execute(
        text(
            "SELECT count(*) FROM cases "
            "WHERE id !~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'"
        )
    )
    return int(result.scalar() or 0) == 0


async def count_null_firm_ids(session) -> int:
    result = await session.execute(
        text("SELECT count(*) FROM cases WHERE firm_id IS NULL")
    )
    return int(result.scalar() or 0)


async def add_columns(session) -> None:
    """Step 1: column additions + nullability relaxations."""
    cols = [
        ("firm_id", "VARCHAR NULL"),
        ("ssn_last4", "VARCHAR(4) NULL"),
        ("ssn_extraction_status", "VARCHAR(16) NOT NULL DEFAULT 'not_found'"),
        ("status", "VARCHAR(16) NOT NULL DEFAULT 'filed'"),
        ("legacy_id", "VARCHAR(100) NULL"),
    ]
    for col_name, col_def in cols:
        if await column_exists(session, "cases", col_name):
            logger.info(f"  cases.{col_name} already exists, skipping")
            continue
        logger.info(f"  ADD COLUMN cases.{col_name} {col_def}")
        await session.execute(text(f"ALTER TABLE cases ADD COLUMN {col_name} {col_def}"))

    # Relax nullable on case_number and the three collection columns.
    # PostgreSQL's "ALTER COLUMN ... DROP NOT NULL" is idempotent — no
    # error if the column is already nullable.
    for col_name in ("case_number", "case_file_collection", "gmail_collection", "courtdrive_collection"):
        logger.info(f"  ALTER COLUMN cases.{col_name} DROP NOT NULL (idempotent)")
        await session.execute(text(f"ALTER TABLE cases ALTER COLUMN {col_name} DROP NOT NULL"))


async def add_indexes(session) -> None:
    """Step 2: indexes (partial + composite + partial UNIQUE)."""
    indexes = [
        (
            "idx_cases_firm_id",
            "CREATE INDEX idx_cases_firm_id ON cases (firm_id) WHERE firm_id IS NOT NULL",
        ),
        (
            "idx_cases_status",
            "CREATE INDEX idx_cases_status ON cases (status)",
        ),
        (
            "idx_cases_legacy_id",
            "CREATE INDEX idx_cases_legacy_id ON cases (legacy_id) WHERE legacy_id IS NOT NULL",
        ),
        (
            "idx_cases_ssn_match",
            "CREATE INDEX idx_cases_ssn_match ON cases (firm_id, ssn_last4, status) "
            "WHERE status = 'unfiled' AND ssn_last4 IS NOT NULL",
        ),
        (
            "uq_cases_case_number",
            "CREATE UNIQUE INDEX uq_cases_case_number ON cases (case_number) "
            "WHERE case_number IS NOT NULL",
        ),
    ]
    for name, ddl in indexes:
        if await index_exists(session, name):
            logger.info(f"  index {name} already exists, skipping")
            continue
        logger.info(f"  CREATE {name}")
        await session.execute(text(ddl))


async def uuid_backfill(session) -> int:
    """Step 3: drop FK, rewrite cases.id to UUIDs (preserving slug in
    legacy_id), propagate to child tables, re-add FK. Returns number of
    rows rewritten.
    """
    if await all_ids_are_uuid(session):
        logger.info("  every cases.id is already a UUID — skipping rewrite")
        return 0

    # 3a. Drop the FK so cases.id can be rewritten without violating it.
    fk_existed = await constraint_exists(session, "case_sessions", "case_sessions_case_id_fkey")
    if fk_existed:
        logger.info("  ALTER TABLE case_sessions DROP CONSTRAINT case_sessions_case_id_fkey")
        await session.execute(
            text("ALTER TABLE case_sessions DROP CONSTRAINT case_sessions_case_id_fkey")
        )
    else:
        logger.warning(
            "  case_sessions.case_id_fkey not found by expected name — "
            "skipping drop step (re-add will be skipped too)"
        )

    # 3b. Build mapping in Python; UPDATE cases + each referring table.
    rows = (await session.execute(text("SELECT id FROM cases"))).fetchall()
    rewritten = 0
    for (old_id,) in rows:
        if _UUID_RE.match(old_id):
            continue
        new_id = str(uuid.uuid4())
        params = {"old": old_id, "new": new_id}
        await session.execute(
            text(
                "UPDATE cases SET legacy_id = id, id = :new WHERE id = :old"
            ),
            params,
        )
        await session.execute(
            text("UPDATE case_sessions SET case_id = :new WHERE case_id = :old"),
            params,
        )
        await session.execute(
            text(
                "UPDATE case_generation_logs SET case_id = :new WHERE case_id = :old"
            ),
            params,
        )
        await session.execute(
            text(
                "UPDATE case_inbox SET accepted_case_id = :new WHERE accepted_case_id = :old"
            ),
            params,
        )
        rewritten += 1

    # 3c. Re-add the FK with the same shape it had before.
    if fk_existed:
        logger.info(
            "  ALTER TABLE case_sessions ADD CONSTRAINT case_sessions_case_id_fkey "
            "FOREIGN KEY (case_id) REFERENCES cases(id)"
        )
        await session.execute(
            text(
                "ALTER TABLE case_sessions "
                "ADD CONSTRAINT case_sessions_case_id_fkey "
                "FOREIGN KEY (case_id) REFERENCES cases(id)"
            )
        )

    return rewritten


async def firm_id_backfill(session) -> int:
    """Step 4: UPDATE cases SET firm_id := settings.DEFAULT_INTAKE_FIRM_ID
    for any rows still NULL. Returns rowcount.
    """
    null_count = await count_null_firm_ids(session)
    if null_count == 0:
        logger.info("  no rows with NULL firm_id — skipping")
        return 0

    default_firm_id = settings.DEFAULT_INTAKE_FIRM_ID
    logger.info(
        f"  UPDATE cases SET firm_id = '{default_firm_id}' WHERE firm_id IS NULL "
        f"({null_count} row(s))"
    )
    result = await session.execute(
        text("UPDATE cases SET firm_id = :firm_id WHERE firm_id IS NULL"),
        {"firm_id": default_firm_id},
    )
    return result.rowcount or 0


async def run_migration() -> bool:
    async with AsyncSessionLocal() as session:
        try:
            row_count = await count_cases(session)
            logger.info(f"Found {row_count} row(s) in cases.")

            # --- Preflight: case_number duplicates ---
            dupes = await find_case_number_duplicates(session)
            if dupes:
                logger.error(
                    f"❌ Found {dupes} case_number duplicate group(s) — "
                    "cannot create partial UNIQUE on case_number. Resolve "
                    "duplicates manually and re-run."
                )
                return False

            # --- Preflight: DEFAULT_INTAKE_FIRM_ID set when needed ---
            if row_count > 0 and not settings.DEFAULT_INTAKE_FIRM_ID:
                logger.error(
                    "❌ settings.DEFAULT_INTAKE_FIRM_ID is empty but cases "
                    "rows exist; firm_id backfill would leave them NULL. "
                    "Set DEFAULT_INTAKE_FIRM_ID in .env before re-running."
                )
                return False

            logger.info("Step 1/4: column additions + nullability relaxations…")
            await add_columns(session)

            logger.info("Step 2/4: indexes…")
            await add_indexes(session)

            logger.info("Step 3/4: UUID backfill (cases.id + child references)…")
            rewritten = await uuid_backfill(session)
            logger.info(f"  rewrote {rewritten} cases row(s) to UUID ids")

            logger.info("Step 4/4: firm_id backfill…")
            updated = await firm_id_backfill(session)
            logger.info(f"  backfilled firm_id on {updated} row(s)")

            await session.commit()
            return True
        except Exception as e:
            await session.rollback()
            logger.exception(f"❌ Migration failed: {e}")
            raise


async def main() -> int:
    logger.info("=" * 60)
    logger.info("Migration: add_unfiled_petition_support_to_cases")
    logger.info("=" * 60)
    try:
        ok = await run_migration()
        if ok:
            logger.info("✅ Migration completed successfully.")
            return 0
        logger.error("❌ Migration aborted; address preflight failures and retry.")
        return 1
    finally:
        await engine.dispose()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
