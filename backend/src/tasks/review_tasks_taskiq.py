"""
Taskiq task for running parallel bankruptcy petition reviews.

Async-native implementation using Taskiq for better concurrency with I/O-bound LLM calls.
"""
import asyncio
import logging
import traceback
from pathlib import Path
from typing import Any

from ..taskiq_app import broker
from .review_task_state import review_task_state, ReviewTaskStatus

logger = logging.getLogger(__name__)

REVIEW_TIMEOUT_SECONDS = 1800


def _create_progress_callback(task_id: str):
    """Create a callback that updates Redis with progress messages."""
    def callback(event: dict):
        stage = event.get("stage", "")
        message = event.get("message", "")

        if stage == "init":
            progress = "Starting bankruptcy review..."
        elif stage == "extract_client_info":
            progress = "Extracting client name and case number..."
        elif stage == "start_group":
            progress = message
        elif stage == "start_master":
            progress = "Generating clarity report..."
        elif stage == "end_master":
            progress = "Finalizing review..."
        elif stage == "done":
            progress = "Review complete!"
        else:
            return

        review_task_state.update_progress(task_id, progress)

    return callback


def _format_review_response(results: dict, master_review: str) -> str:
    """Format the review results as a chat message."""
    response_text = "Complete bankruptcy review completed!\n\n"
    response_text += "Schedule Reviews:\n"

    for schedule_name, review_data in (results.get("group_reviews") or {}).items():
        status = review_data.get("status", "unknown")
        if status == "completed":
            response_text += f"  - {schedule_name} (completed)\n"
        else:
            response_text += f"  - {schedule_name} ({status})\n"

    response_text += "\nMaster Analysis:\n"
    master_result = results.get("master_review", {}) or {}
    if master_result.get("status") == "completed":
        response_text += "  - Master review completed\n"
        response_text += f"\nComplete Master Review:\n\n{master_review}"
    else:
        response_text += f"  - Master review failed: {master_result.get('error', 'Unknown error')}"

    response_text += "\n\nResults saved for further analysis."
    return response_text


async def _save_to_chat_history(session_id: str, pdf_path: str, results: dict, response_text: str):
    """Save the review results to database and chat history."""
    from ..chatbot.database import (
        save_review_results,
        create_or_update_chat_thread,
        save_chat_message,
        update_thread_metadata as db_update_thread_metadata
    )

    await save_review_results(session_id, pdf_path, results)

    chat_thread = await create_or_update_chat_thread(session_id)
    if not (chat_thread.title and chat_thread.title.strip()):
        await db_update_thread_metadata(chat_thread.id, title="Review Bankruptcy Petition")

    await save_chat_message(thread_id=chat_thread.id, role="user", content="Review Bankruptcy Petition")
    await save_chat_message(thread_id=chat_thread.id, role="assistant", content=response_text)


async def _run_review_async(task_id: str, session_id: str, pdf_path: str, progress_callback) -> dict[str, Any]:
    """Run the review asynchronously and save results."""
    from ..chatbot.parallel_reviewer import run_parallel_bankruptcy_review_async

    results = await run_parallel_bankruptcy_review_async(
        pdf_path=pdf_path,
        session_id=session_id,
        progress_callback=progress_callback
    )

    if review_task_state.is_cancelled(task_id):
        return {"status": "cancelled", "message": "Task was cancelled"}

    if not results:
        review_task_state.set_error(task_id, "Review returned no results")
        return {"status": "error", "message": "Review returned no results"}

    if results.get("is_skeleton"):
        skeleton_message = "It looks like this petition is a skeleton. We will give you a full review once the updated schedules are filed or inputted."
        review_task_state.set_result(
            task_id=task_id,
            debtor_name="N/A",
            case_number="N/A",
            master_review=skeleton_message,
            group_reviews={}
        )
        await _save_to_chat_history(session_id, pdf_path, results, skeleton_message)
        return {"status": "completed", "is_skeleton": True}

    debtor_name = results.get("debtor_name", "N/A")
    case_number = results.get("case_number", "N/A")
    master_result = results.get("master_review", {})
    master_review = master_result.get("master_review", "") if isinstance(master_result, dict) else ""
    group_reviews = results.get("group_reviews", {})

    serializable_group_reviews = {}
    for name, data in group_reviews.items():
        serializable_group_reviews[name] = {
            "status": data.get("status", "unknown"),
            "review": data.get("review", "")
        }

    review_task_state.set_result(
        task_id=task_id,
        debtor_name=debtor_name,
        case_number=case_number,
        master_review=master_review,
        group_reviews=serializable_group_reviews
    )

    response_text = _format_review_response(results, master_review)
    await _save_to_chat_history(session_id, pdf_path, results, response_text)

    return {
        "status": "completed",
        "task_id": task_id,
        "debtor_name": debtor_name,
        "case_number": case_number
    }


@broker.task(
    task_name="run_petition_review",
    retry_on_error=True,
    max_retries=2,
)
async def run_petition_review(task_id: str) -> dict[str, Any]:
    """
    Single-phase review task:
    1. Get task from Redis
    2. Update status to PROCESSING
    3. Run parallel_reviewer.run_parallel_bankruptcy_review_async()
    4. Store result (master_review markdown + group_reviews)
    5. Save to chat history
    6. Update status to COMPLETED

    Async-native implementation - no asyncio.run() needed.
    """
    task = review_task_state.get_task(task_id)
    if task is None:
        return {"status": "error", "message": "Task not found"}

    if review_task_state.is_cancelled(task_id):
        return {"status": "cancelled", "message": "Task was cancelled"}

    review_task_state.update_status(
        task_id,
        ReviewTaskStatus.PROCESSING,
        "Analyzing bankruptcy petition..."
    )

    try:
        session_id = task["session_id"]
        pdf_path = task["pdf_path"]

        _pdf = Path(pdf_path)
        if not _pdf.exists():
            _fallback = Path("/app/uploads") / _pdf.name
            if _fallback.exists():
                logger.info(f"[review] pdf_path not found at {pdf_path}, using fallback: {_fallback}")
                pdf_path = str(_fallback)
            else:
                raise FileNotFoundError(
                    f"Petition PDF not found at '{pdf_path}' or '{_fallback}'. "
                    "Please re-summon the petition using the Case Number tab."
                )

        if review_task_state.is_cancelled(task_id):
            return {"status": "cancelled", "message": "Task was cancelled"}

        progress_callback = _create_progress_callback(task_id)

        result = await asyncio.wait_for(
            _run_review_async(task_id, session_id, pdf_path, progress_callback),
            timeout=REVIEW_TIMEOUT_SECONDS
        )

        return result

    except asyncio.TimeoutError:
        error_message = "Review task exceeded time limit (30 minutes). The petition may be too large or complex."
        review_task_state.set_error(task_id, error_message)
        return {"status": "error", "message": error_message}

    except Exception as exc:
        error_message = f"{str(exc)}\n{traceback.format_exc()}"
        logger.exception(f"Review task {task_id} failed: {exc}")
        review_task_state.set_error(task_id, error_message)
        raise
