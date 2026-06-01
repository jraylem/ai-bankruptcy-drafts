"""Taskiq scheduled tasks for the v2 ECF inbox.

Two crons:
  - ingest_ecf_inbox    every */15 — polls Gmail, ingests new petitions
  - archive_stale_inbox every  0 * — flips ready rows older than 48h to archived

Both registered against `core_broker` (the v2 queue). The shared scheduler
at `src/taskiq_scheduler.py` discovers them via LabelScheduleSource.
"""

from __future__ import annotations

import logging

from taskiq import Context

from src.config import settings
from src.core.common.storage.database import CaseInboxRepository
from src.core.components.pleading.broker import core_broker

from .ingest import run_ingest_cycle

logger = logging.getLogger(__name__)


@core_broker.task(
    task_name="ingest_ecf_inbox",
    schedule=[{"cron": "*/5 * * * *"}],  # every 5 minutes
)
async def ingest_ecf_inbox(context: Context = None) -> dict:
    """Periodic Gmail → R2 → DB ingest. Returns counters from one cycle.

    firm_id is derived at runtime from the OAuth token's email
    (User.firm_id WHERE email = oauth_email). settings.DEFAULT_INTAKE_FIRM_ID
    is kept as an optional override; leave it unset to use OAuth-derived.
    Multi-firm requires a per-firm OAuth credential model — separate follow-up.

    Gated by settings.ENABLE_ECF_INGEST (default False). Other devs running
    the worker locally short-circuit here so they don't burn PACER one-shot
    links from the shared OAuth account. Operators with legitimate access
    set ENABLE_ECF_INGEST=true in their .env. The archive_stale_inbox cron
    below is NOT gated — it's idempotent and harmless.
    """
    if not settings.ENABLE_ECF_INGEST:
        logger.info(
            "ingest_ecf_inbox: skipped (ENABLE_ECF_INGEST=false). "
            "Set ENABLE_ECF_INGEST=true in .env to opt in."
        )
        return {"skipped": True, "reason": "ENABLE_ECF_INGEST=false"}

    firm_id_override = settings.DEFAULT_INTAKE_FIRM_ID or None
    result = await run_ingest_cycle(
        firm_id=firm_id_override,
        lookback_minutes=settings.ECF_INBOX_GMAIL_LOOKBACK_MINUTES,
        max_results=settings.ECF_INBOX_GMAIL_MAX_RESULTS,
    )
    return {
        "cycle_id": result.cycle_id,
        "discovered": result.discovered,
        "inserted": result.inserted,
        "gmail_dedup_skips": result.gmail_dedup_skips,
        "fingerprint_dedup_skips": result.fingerprint_dedup_skips,
        "dead_links": result.dead_links,
        "r2_upload_failures": result.r2_upload_failures,
        "db_insert_failures": result.db_insert_failures,
        "parse_errors": result.parse_errors,
    }


@core_broker.task(
    task_name="archive_stale_inbox",
    schedule=[{"cron": "0 * * * *"}],  # top of every hour
)
async def archive_stale_inbox(context: Context = None) -> dict:
    """Promote `ready` rows older than 48h to `archived` (cron timeout).

    Single atomic UPDATE — no R2 work. Bytes stay at the same key so
    archived rows are recoverable via Summon. dismissed_by_user_id stays
    NULL on these rows — that's the UI's discriminator between
    'timed out Xd ago' and 'dismissed by Maria Xh ago'.
    """
    archived = await CaseInboxRepository.archive_stale_ready()
    logger.info("archive_stale_inbox: %d rows transitioned ready→archived", archived)
    return {"archived": archived}
