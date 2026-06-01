"""
Motion tracking services.

Two separate concerns:
  1. motion_draft_log  — lifecycle tracking for ALL drafted motions/orders
                         (pending → completed | failed). Used by the dashboard.
  2. monitored_motions — order-generation monitoring for the 6 motion types
                         that need a corresponding order generated later.
                         Used by the Gmail poll worker / court-mail service.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text
from ..chatbot.models import MonitoredMotion, MotionDraftLog
from ..chatbot.database import AsyncSessionLocal

logger = logging.getLogger(__name__)


async def _resolve_firm_id(db, session_id: str) -> Optional[str]:
    """Look up firm_id from the sessions table for a given session_id."""
    result = await db.execute(
        text("SELECT firm_id FROM sessions WHERE id = :sid LIMIT 1"),
        {"sid": session_id},
    )
    row = result.fetchone()
    return row._mapping["firm_id"] if row else None


# ---------------------------------------------------------------------------
# motion_draft_log — full lifecycle tracking (all motion types)
# ---------------------------------------------------------------------------

# Called by: orchestrator.start_pleading_generation_async()
async def log_draft_pending(
    session_id: str,
    motion_type: str,
    case_name: Optional[str] = None,
) -> Optional[str]:
    """Insert a motion_draft_logs row with status='pending' at task creation.

    Returns the record ID, or None on failure (never raises — a logging
    failure must not break the calling request).
    """
    async with AsyncSessionLocal() as db:
        try:
            record = MotionDraftLog(
                session_id=session_id,
                motion_type=motion_type,
                status="pending",
                case_name=case_name,
                firm_id=await _resolve_firm_id(db, session_id),
            )
            db.add(record)
            await db.commit()
            await db.refresh(record)
            logger.info(f"[draft_log] pending '{motion_type}' for session {session_id}")
            return record.id
        except Exception as e:
            await db.rollback()
            logger.warning(f"[draft_log] failed to insert pending record for session {session_id}: {e}")
            return None


# Called by: pleading_tasks_taskiq.generate_pleading_documents()
async def log_draft_completed(
    session_id: str,
    motion_type: str,
    case_number: Optional[str] = None,
    cos_type: Optional[str] = None,
) -> bool:
    """Update the most recent pending motion_draft_logs row to 'completed'.

    Falls back to a direct insert if no pending row exists (e.g. on restart).
    Returns True on success, False on failure.
    """
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(
                select(MotionDraftLog)
                .where(MotionDraftLog.session_id == session_id)
                .where(MotionDraftLog.motion_type == motion_type)
                .where(MotionDraftLog.status == "pending")
                .order_by(MotionDraftLog.created_at.desc())
                .limit(1)
            )
            record = result.scalar_one_or_none()

            if record:
                record.status = "completed"
                record.case_number = case_number
                record.completed_at = datetime.now(timezone.utc)
                record.cos_type = cos_type
            else:
                record = MotionDraftLog(
                    session_id=session_id,
                    motion_type=motion_type,
                    status="completed",
                    case_number=case_number,
                    completed_at=datetime.now(timezone.utc),
                    cos_type=cos_type,
                    firm_id=await _resolve_firm_id(db, session_id),
                )
                db.add(record)

            await db.commit()
            logger.info(f"[draft_log] completed '{motion_type}' for session {session_id}")
            return True
        except Exception as e:
            await db.rollback()
            logger.error(f"[draft_log] failed to mark completed for session {session_id}: {e}")
            return False


# Called by: pleadings.cancel_task() route (routes/pleadings.py)
async def log_draft_cancelled(
    session_id: str,
    motion_type: str,
) -> bool:
    """Update the most recent pending motion_draft_logs row to 'cancelled'.

    Falls back to a direct insert if no pending row exists.
    Returns True on success, False on failure.
    """
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(
                select(MotionDraftLog)
                .where(MotionDraftLog.session_id == session_id)
                .where(MotionDraftLog.motion_type == motion_type)
                .where(MotionDraftLog.status == "pending")
                .order_by(MotionDraftLog.created_at.desc())
                .limit(1)
            )
            record = result.scalar_one_or_none()

            if record:
                record.status = "cancelled"
                record.completed_at = datetime.now(timezone.utc)
            else:
                record = MotionDraftLog(
                    session_id=session_id,
                    motion_type=motion_type,
                    status="cancelled",
                    completed_at=datetime.now(timezone.utc),
                    firm_id=await _resolve_firm_id(db, session_id),
                )
                db.add(record)

            await db.commit()
            logger.info(f"[draft_log] cancelled '{motion_type}' for session {session_id}")
            return True
        except Exception as e:
            await db.rollback()
            logger.error(f"[draft_log] failed to mark cancelled for session {session_id}: {e}")
            return False


# Called by: pleading_tasks_taskiq.generate_pleading_documents() (exception handler)
async def log_draft_failed(
    session_id: str,
    motion_type: str,
) -> bool:
    """Update the most recent pending motion_draft_logs row to 'failed'.

    Falls back to a direct insert if no pending row exists.
    Returns True on success, False on failure.
    """
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(
                select(MotionDraftLog)
                .where(MotionDraftLog.session_id == session_id)
                .where(MotionDraftLog.motion_type == motion_type)
                .where(MotionDraftLog.status == "pending")
                .order_by(MotionDraftLog.created_at.desc())
                .limit(1)
            )
            record = result.scalar_one_or_none()

            if record:
                record.status = "failed"
                record.completed_at = datetime.now(timezone.utc)
            else:
                record = MotionDraftLog(
                    session_id=session_id,
                    motion_type=motion_type,
                    status="failed",
                    completed_at=datetime.now(timezone.utc),
                    firm_id=await _resolve_firm_id(db, session_id),
                )
                db.add(record)

            await db.commit()
            logger.info(f"[draft_log] failed '{motion_type}' for session {session_id}")
            return True
        except Exception as e:
            await db.rollback()
            logger.error(f"[draft_log] failed to mark failed for session {session_id}: {e}")
            return False


# ---------------------------------------------------------------------------
# monitored_motions — order-generation monitoring (6 motion types only)
# ---------------------------------------------------------------------------

# Motion types that require a corresponding order to be generated later.
ORDER_MAPPING = {
    "extend":    "order-extend",
    "withdraw":  "order-withdraw",
    "waive":     "order-waive",
    "reinstate": "order-reinstate",
    "claim":     "objection-sustain",
    "value":     "order-value",
}


# Called by: pleading_tasks_taskiq (tasks/pleading_tasks_taskiq.py) after a motion is generated
async def track_motion_for_order(
    session_id: str,
    motion_type: str,
    metadata: Optional[dict] = None,
) -> Optional[MonitoredMotion]:
    """Insert a monitored_motions row for order-generation monitoring.

    Only runs for motion types in ORDER_MAPPING. Returns None silently for
    types without a corresponding order.
    """
    pending_order = ORDER_MAPPING.get(motion_type)
    if not pending_order:
        logger.debug(f"[order_monitor] '{motion_type}' has no corresponding order, skipping")
        return None

    async with AsyncSessionLocal() as db:
        try:
            record = MonitoredMotion(
                session_id=session_id,
                motion_type=motion_type,
                pending_order_type=pending_order,
                status="pending",
                motion_metadata=metadata,
            )
            db.add(record)
            await db.commit()
            await db.refresh(record)
            logger.info(f"[order_monitor] tracked '{motion_type}' for session {session_id}, pending order: {pending_order}")
            return record
        except Exception as e:
            await db.rollback()
            logger.error(f"[order_monitor] failed to track '{motion_type}' for session {session_id}: {e}")
            raise


