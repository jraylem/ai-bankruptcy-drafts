from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..config import settings
from ..tasks.review_task_state import review_task_state, ReviewTaskStatus
from ..tasks.review_orchestrator import start_review_task
from ..chatbot.database import get_session_pdfs, get_session_chat_thread, log_user_action


router = APIRouter()


class StartReviewRequest(BaseModel):
    session_id: str


class StartReviewResponse(BaseModel):
    task_id: str
    status: str
    case_name: str
    session_id: str
    created_at: str
    message: str


class TaskListResponse(BaseModel):
    tasks: list[dict]
    count: int
    limit: int


@router.post("/start", response_model=StartReviewResponse)
async def start_review(
    request: StartReviewRequest,
    user_id: str = Query(..., description="User ID for concurrency tracking"),
    firm_id: str | None = Query(None),
):
    """Start a new petition review task."""
    session_pdfs = await get_session_pdfs(request.session_id)
    if not session_pdfs:
        raise HTTPException(status_code=400, detail="No uploaded PDFs found for session")

    # Find the best available PDF path — prefer Bankruptcy_Petition_ files
    from pathlib import Path as _Path
    pdf_path = None
    for pdf in session_pdfs:
        candidate = _Path(pdf.file_path)
        if candidate.exists():
            pdf_path = str(candidate)
            break
        # Fallback: same filename in uploads/ root
        fallback = _Path("/app/uploads") / candidate.name
        if fallback.exists():
            pdf_path = str(fallback)
            break

    if not pdf_path:
        raise HTTPException(
            status_code=404,
            detail="Petition PDF file not found on disk. Please re-summon the petition using the Case Number tab."
        )

    chat_thread = await get_session_chat_thread(request.session_id)
    case_name = "Bankruptcy Review"
    if chat_thread and chat_thread.title:
        case_name = chat_thread.title

    result = await start_review_task(
        user_id=user_id,
        session_id=request.session_id,
        case_name=case_name,
        pdf_path=pdf_path
    )

    if result.get("status") == "error":
        raise HTTPException(
            status_code=429,
            detail={
                "error": result.get("error"),
                "message": result.get("message"),
                "active_tasks": result.get("active_tasks"),
                "max_tasks": result.get("max_tasks")
            }
        )

    await log_user_action(
        action="start_review",
        user_id=user_id,
        session_id=request.session_id,
        firm_id=firm_id,
        metadata={"case_name": case_name},
    )
    return StartReviewResponse(
        task_id=result["task_id"],
        status=result["task_status"],
        case_name=result["case_name"],
        session_id=result["session_id"],
        created_at=result["created_at"],
        message=result["message"]
    )


@router.get("/tasks", response_model=TaskListResponse)
def list_tasks(
    user_id: str = Query(..., description="User ID to list tasks for"),
):
    """List visible review tasks (active + completed + failed) for a user."""
    tasks = review_task_state.get_visible_tasks(user_id)

    return TaskListResponse(
        tasks=tasks,
        count=len(tasks),
        limit=settings.MAX_CONCURRENT_REVIEW_TASKS
    )


@router.post("/tasks/{task_id}/cancel")
def cancel_task(task_id: str):
    """Cancel a review task."""
    task = review_task_state.get_task(task_id)

    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    if task["status"] in [ReviewTaskStatus.COMPLETED.value, ReviewTaskStatus.FAILED.value, ReviewTaskStatus.CANCELLED.value]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel task with status: {task['status']}"
        )

    success = review_task_state.cancel_task(task_id)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to cancel task")

    return {
        "task_id": task_id,
        "status": ReviewTaskStatus.CANCELLED.value,
        "message": "Review cancelled successfully"
    }


@router.delete("/tasks/{task_id}")
def delete_task(task_id: str):
    """Delete a task from Redis (cleanup)."""
    task = review_task_state.get_task(task_id)

    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    success = review_task_state.delete_task(task_id)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete task")

    return {
        "task_id": task_id,
        "message": "Task deleted successfully"
    }


@router.get("/health/taskiq")
async def taskiq_health_check():
    """Check Taskiq broker health for review tasks."""
    try:
        from ..taskiq_app import broker

        return {
            "status": "healthy",
            "broker_type": type(broker).__name__,
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }


@router.post("/health/cleanup-stale")
def cleanup_stale_review_tasks():
    """Manually trigger cleanup of stale review tasks."""
    stats = review_task_state.cleanup_stale_tasks(stale_threshold_minutes=35)

    return {
        "status": "completed",
        "review": stats,
    }
