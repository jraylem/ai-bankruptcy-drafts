"""Orchestration functions for starting and monitoring petition review tasks."""
import asyncio
from typing import Any

from .review_task_state import review_task_state
from ..config import settings


def _check_review_preconditions(user_id: str, session_id: str) -> dict[str, Any] | None:
    """Check if a new review task can be started. Returns error dict or None if OK."""
    if review_task_state.has_active_task_for_session(session_id):
        return {
            "status": "error",
            "error": "session_review_in_progress",
            "message": "A review is already in progress for this session"
        }

    if not review_task_state.can_start_new_task(user_id):
        active_count = review_task_state.count_active_tasks(user_id)
        return {
            "status": "error",
            "error": "concurrent_limit_reached",
            "message": f"Maximum {settings.MAX_CONCURRENT_REVIEW_TASKS} simultaneous reviews allowed",
            "active_tasks": active_count,
            "max_tasks": settings.MAX_CONCURRENT_REVIEW_TASKS
        }

    return None


def _build_review_response(task_id: str, case_name: str, session_id: str, worker_task_id: str) -> dict[str, Any]:
    """Build the response dict for a queued review task."""
    task = review_task_state.get_task(task_id)
    return {
        "status": "success",
        "task_id": task_id,
        "worker_task_id": worker_task_id,
        "task_status": task["status"],
        "case_name": case_name,
        "session_id": session_id,
        "created_at": task["created_at"],
        "message": "Review queued for processing"
    }


async def start_review_task(
    user_id: str,
    session_id: str,
    case_name: str,
    pdf_path: str
) -> dict[str, Any]:
    """Start a new petition review task via TaskIQ."""
    error = await asyncio.to_thread(_check_review_preconditions, user_id, session_id)
    if error:
        return error

    task_id = await asyncio.to_thread(
        review_task_state.create_task,
        user_id=user_id,
        session_id=session_id,
        case_name=case_name,
        pdf_path=pdf_path
    )

    from ..taskiq_client import enqueue_review

    taskiq_handle = await enqueue_review(task_id=task_id)

    worker_task_id = taskiq_handle.task_id
    await asyncio.to_thread(review_task_state.set_worker_task_id, task_id, worker_task_id)

    return await asyncio.to_thread(_build_review_response, task_id, case_name, session_id, worker_task_id)
