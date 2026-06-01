"""
Migration script to normalize existing case numbers to XX-XXXXX format.

Converts case numbers like:
- 1:25-bk-15244  ->  25-15244
- 26-bk-11993    ->  26-11993
- 25-31154-KKS   ->  25-31154

Usage:
    docker compose exec backend uv run python migrations/normalize_case_numbers.py
"""

import asyncio
import json
import sys
import re
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


def normalize_to_short(value: str) -> str:
    """Normalize any case number format to XX-XXXXX."""
    candidate = (value or "").strip()
    if not candidate:
        return candidate

    normalized = re.sub(r"[_\s]+", "-", candidate)
    normalized = re.sub(r"-{2,}", "-", normalized).strip("-")
    normalized = re.sub(r"(?i)-bk-", "-bk-", normalized)

    # chapter:year-bk-number (e.g. 1:25-bk-15244)
    m = re.fullmatch(r"(?i)(\d{1,2})[:-](\d{2})-bk-(\d{4,7})(?:-([A-Za-z]{2,5}))?", normalized)
    if m:
        return f"{m.group(2)}-{m.group(3)}"

    # year-bk-number (e.g. 26-bk-11993)
    m = re.fullmatch(r"(?i)(\d{2})-bk-(\d{4,7})(?:-([A-Za-z]{2,5}))?", normalized)
    if m:
        return f"{m.group(1)}-{m.group(2)}"

    # year-number with optional judge suffix (e.g. 25-31154-KKS)
    m = re.fullmatch(r"(?i)(\d{2})-(\d{5})(?:-([A-Za-z]{2,5}))?", normalized)
    if m:
        return f"{m.group(1)}-{m.group(2)}"

    return candidate


async def normalize_case_numbers():
    """Normalize all existing case numbers in chat_threads and courtdrive_ingestions."""
    async with AsyncSessionLocal() as session:
        try:
            # --- chat_threads ---
            result = await session.execute(text(
                "SELECT id, case_number FROM chat_threads WHERE case_number IS NOT NULL AND case_number != ''"
            ))
            rows = result.fetchall()
            updated_threads = 0

            for row in rows:
                row_id, old_value = row[0], row[1]
                new_value = normalize_to_short(old_value)
                if new_value != old_value:
                    await session.execute(
                        text("UPDATE chat_threads SET case_number = :new WHERE id = :id"),
                        {"new": new_value, "id": row_id}
                    )
                    logger.info(f"  chat_threads [{row_id}]: '{old_value}' -> '{new_value}'")
                    updated_threads += 1

            logger.info(f"Updated {updated_threads}/{len(rows)} rows in chat_threads")

            # --- courtdrive_ingestions ---
            result = await session.execute(text(
                "SELECT id, case_number FROM courtdrive_ingestions WHERE case_number IS NOT NULL AND case_number != ''"
            ))
            rows = result.fetchall()
            updated_ingestions = 0

            for row in rows:
                row_id, old_value = row[0], row[1]
                new_value = normalize_to_short(old_value)
                if new_value != old_value:
                    await session.execute(
                        text("UPDATE courtdrive_ingestions SET case_number = :new WHERE id = :id"),
                        {"new": new_value, "id": row_id}
                    )
                    logger.info(f"  courtdrive_ingestions [{row_id}]: '{old_value}' -> '{new_value}'")
                    updated_ingestions += 1

            logger.info(f"Updated {updated_ingestions}/{len(rows)} case_number column in courtdrive_ingestions")

            # --- courtdrive_ingestions JSON result payload ---
            result = await session.execute(text(
                "SELECT id, result FROM courtdrive_ingestions WHERE result IS NOT NULL"
            ))
            rows = result.fetchall()
            updated_payloads = 0

            CASE_KEYS = ("case_number", "resolved_case_number")
            for row in rows:
                row_id = row[0]
                raw = row[1]
                if not raw:
                    continue
                try:
                    payload = json.loads(raw) if isinstance(raw, str) else raw
                except (json.JSONDecodeError, TypeError):
                    continue
                if not isinstance(payload, dict):
                    continue

                changed = False
                for key in CASE_KEYS:
                    old_val = (payload.get(key) or "").strip()
                    if not old_val:
                        continue
                    new_val = normalize_to_short(old_val)
                    if new_val != old_val:
                        payload[key] = new_val
                        changed = True
                        logger.info(f"  courtdrive_ingestions result [{row_id}] {key}: '{old_val}' -> '{new_val}'")

                if changed:
                    await session.execute(
                        text("UPDATE courtdrive_ingestions SET result = :result WHERE id = :id"),
                        {"result": json.dumps(payload), "id": row_id}
                    )
                    updated_payloads += 1

            logger.info(f"Updated {updated_payloads}/{len(rows)} result payloads in courtdrive_ingestions")

            await session.commit()
            return updated_threads + updated_ingestions

        except Exception as e:
            await session.rollback()
            logger.error(f"Error normalizing case numbers: {e}")
            raise


async def main():
    try:
        logger.info("=" * 60)
        logger.info("Migration: Normalize case numbers to XX-XXXXX format")
        logger.info("=" * 60)

        count = await normalize_case_numbers()
        logger.info(f"Total rows updated: {count}")
        logger.info("Migration completed successfully!")
        return 0

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        logger.exception(e)
        return 1
    finally:
        await engine.dispose()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
