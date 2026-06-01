"""
Taskiq scheduled task for cleaning up stale tasks.

Runs every 5 minutes to cleanup stale pleading and review tasks.
"""
import logging

from taskiq import TaskiqScheduler, Context
from taskiq.schedule_sources import LabelScheduleSource

from ..taskiq_app import broker

logger = logging.getLogger(__name__)


@broker.task(
    task_name="cleanup_stale_tasks",
    schedule=[{"cron": "*/5 * * * *"}],
)
async def cleanup_stale_tasks(context: Context = None) -> dict:
    """
    Periodic task to cleanup stale pleading and review tasks.

    A task is considered stale if it has been in an active status
    (PENDING, EXTRACTING, GENERATING, PROCESSING) for too long without updates.

    Thresholds:
    - Pleading tasks: 15 minutes
    - Review tasks: 35 minutes (reviews can take up to 30 min)
    """
    from .task_state import task_state
    from .review_task_state import review_task_state

    pleading_stats = task_state.cleanup_stale_tasks(stale_threshold_minutes=15)
    review_stats = review_task_state.cleanup_stale_tasks(stale_threshold_minutes=35)

    logger.info(
        f"Stale task cleanup completed - "
        f"Pleading: scanned={pleading_stats['scanned']}, cleaned={pleading_stats['cleaned']} | "
        f"Review: scanned={review_stats['scanned']}, cleaned={review_stats['cleaned']}"
    )

    return {
        "pleading": pleading_stats,
        "review": review_stats,
    }


@broker.task(
    task_name="reconcile_auto_archived_petitions",
    schedule=[{"cron": "*/30 * * * *"}],
)
async def reconcile_auto_archived_petitions(context: Context = None) -> dict:
    """
    Reconcile pending petition sessions whose files were swept by the archiver.

    Runs every 6 hours. Any pending session whose petition file no longer exists
    on disk is marked auto_archived and deactivated so it disappears from the inbox.
    """
    from ..gmail.workflow_services import CaseAcceptanceService

    service = CaseAcceptanceService()
    result = await service.auto_archive_stale_pending_cases()

    logger.info(
        f"Auto-archive reconciliation completed — archived {result['archived_count']} session(s), "
        f"errors: {len(result.get('errors', []))}"
    )
    return result
