import asyncio
import logging
import re
from pathlib import Path
from typing import Any, Optional

_UUID_RE = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..config import settings
from ..tasks.task_state import task_state, TaskStatus
from ..tasks.orchestrator import (
    start_pleading_generation,
    get_motion_display_name,
)
from ..chatbot.database import log_user_action, get_motion_case_info
from ..tasks.pleading_helpers import build_download_filename
from ..billing.service import report_usage_event

logger = logging.getLogger(__name__)

OUT_DIR = Path(__file__).parent.parent / "motion_filling" / "out"

router = APIRouter()


class GeneratePleadingRequest(BaseModel):
    session_id: str
    motion_type: str
    case_name: str
    source: str = "gmail"
    include_certificate_of_service: bool = True
    include_order_sustaining: bool = False
    initial_user_input: Optional[dict[str, Any]] = None
    skip_existing_check: bool = False
    modification_type: str = "delinquent"
    extension_type: str = "regular"


class SubmitInputRequest(BaseModel):
    user_input: dict[str, Any]


class GeneratePleadingResponse(BaseModel):
    task_id: str
    status: str
    motion_type: str
    motion_type_display: str
    case_name: str
    created_at: str
    message: str


class TaskListResponse(BaseModel):
    tasks: list[dict]
    count: int
    limit: int


@router.post("/generate", response_model=GeneratePleadingResponse)
async def generate_pleading(
    request: GeneratePleadingRequest,
    user_id: str = Query(..., description="User ID for concurrency tracking"),
    firm_id: str | None = Query(None),
):
    result = await start_pleading_generation(
        user_id=user_id,
        session_id=request.session_id,
        motion_type=request.motion_type,
        case_name=request.case_name,
        source=request.source,
        include_cos=request.include_certificate_of_service,
        include_order_sustaining=request.include_order_sustaining,
        initial_user_input=request.initial_user_input,
        skip_existing_check=request.skip_existing_check,
        modification_type=request.modification_type,
        extension_type=request.extension_type,
    )

    if result.get("status") == "error":
        raise HTTPException(
            status_code=429,
            detail={
                "error": result.get("error"),
                "message": result.get("message"),
                "active_tasks": result.get("active_tasks")
            }
        )

    await log_user_action(
        action="draft_motion",
        user_id=user_id,
        session_id=request.session_id,
        firm_id=firm_id,
        metadata={"motion_type": request.motion_type, "case_name": request.case_name},
    )
    if firm_id:
        asyncio.create_task(report_usage_event(firm_id, "pleading_generation"))

    return GeneratePleadingResponse(
        task_id=result["task_id"],
        status=result["task_status"],
        motion_type=result["motion_type"],
        motion_type_display=result["motion_type_display"],
        case_name=result["case_name"],
        created_at=result["created_at"],
        message=result["message"]
    )


@router.get("/tasks", response_model=TaskListResponse)
def list_tasks(
    user_id: str = Query(..., description="User ID to list tasks for"),
    status: Optional[str] = Query(None, description="Reserved; currently ignored — visible tasks (active + completed + failed) are always returned")
):
    tasks = task_state.get_visible_tasks(user_id)

    for task in tasks:
        if not task.get("motion_type_display") and task.get("motion_type"):
            task["motion_type_display"] = get_motion_display_name(task["motion_type"])

    return TaskListResponse(
        tasks=tasks,
        count=len(tasks),
        limit=settings.MAX_CONCURRENT_PLEADING_TASKS
    )


@router.post("/tasks/{task_id}/input")
async def submit_task_input(task_id: str, request: SubmitInputRequest):
    task = await asyncio.to_thread(task_state.get_task, task_id)

    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    if task["status"] != TaskStatus.AWAITING_INPUT.value:
        raise HTTPException(
            status_code=400,
            detail=f"Task is not awaiting input. Current status: {task['status']}"
        )

    success = await asyncio.to_thread(task_state.submit_input, task_id, request.user_input)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to submit input")

    # Check if this is an intermediate input (missing_field set)
    input_required = task.get("input_required", {})
    missing_field = input_required.get("missing_field") if input_required else None
    is_intermediate_input = missing_field is not None

    if is_intermediate_input:
        from ..taskiq_client import enqueue_resume_extraction

        taskiq_handle = await enqueue_resume_extraction(
            task_id=task_id,
            session_id=task["session_id"],
            motion_type=task["motion_type"],
            user_input=request.user_input,
            include_cos=task.get("include_cos", True),
            include_order_sustaining=task.get("include_order_sustaining", False),
            modification_type=task.get("modification_type", "delinquent"),
            extension_type=task.get("extension_type", "regular"),
        )
        worker_task_id = taskiq_handle.task_id
        message = "Input received, continuing extraction..."
    else:
        from ..taskiq_client import enqueue_generate_documents

        taskiq_handle = await enqueue_generate_documents(
            task_id=task_id,
            session_id=task["session_id"],
            motion_type=task["motion_type"],
            user_input=request.user_input,
            include_cos=task.get("include_cos", True),
            include_order_sustaining=task.get("include_order_sustaining", False),
        )
        worker_task_id = taskiq_handle.task_id
        message = "Input received, generating documents..."

    await asyncio.to_thread(task_state.set_worker_task_id, task_id, worker_task_id)
    updated_task = await asyncio.to_thread(task_state.get_task, task_id)

    return {
        "task_id": task_id,
        "status": updated_task["status"],
        "worker_task_id": worker_task_id,
        "message": message
    }


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(task_id: str):
    task = await asyncio.to_thread(task_state.get_task, task_id)

    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    if task["status"] in [TaskStatus.COMPLETED.value, TaskStatus.FAILED.value, TaskStatus.CANCELLED.value]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel task with status: {task['status']}"
        )

    success = await asyncio.to_thread(task_state.cancel_task, task_id)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to cancel task")

    session_id = task.get("session_id")
    motion_type = task.get("motion_type")
    if session_id and motion_type:
        try:
            from ..tasks.motion_tracker import log_draft_cancelled
            await log_draft_cancelled(session_id=session_id, motion_type=motion_type)
        except Exception as e:
            logger.warning(f"Failed to log draft cancellation for task {task_id}: {e}")

    return {
        "task_id": task_id,
        "status": TaskStatus.CANCELLED.value,
        "message": "Task cancelled successfully"
    }


@router.post("/tasks/{task_id}/regenerate")
async def regenerate_task(task_id: str):
    """Continue from EXISTING_FOUND state to regenerate the document."""
    task = await asyncio.to_thread(task_state.get_task, task_id)

    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    if task["status"] != TaskStatus.EXISTING_FOUND.value:
        raise HTTPException(
            status_code=400,
            detail=f"Task is not in EXISTING_FOUND state. Current status: {task['status']}"
        )

    success = await asyncio.to_thread(task_state.continue_to_extract, task_id)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to continue task")

    from ..taskiq_client import enqueue_extract_pleading

    taskiq_handle = await enqueue_extract_pleading(
        task_id=task_id,
        session_id=task["session_id"],
        motion_type=task["motion_type"],
        source=task.get("source", "gmail"),
        include_cos=task.get("include_cos", True),
        include_order_sustaining=task.get("include_order_sustaining", False),
        initial_user_input=task.get("initial_user_input"),
        skip_existing_check=True,
        modification_type=task.get("modification_type", "delinquent"),
        extension_type=task.get("extension_type", "regular"),
    )
    worker_task_id = taskiq_handle.task_id

    await asyncio.to_thread(task_state.set_worker_task_id, task_id, worker_task_id)
    updated_task = await asyncio.to_thread(task_state.get_task, task_id)

    return {
        "task_id": task_id,
        "worker_task_id": worker_task_id,
        "status": updated_task["status"],
        "message": "Regeneration started, extracting case information..."
    }


@router.post("/tasks/{task_id}/use-existing")
def use_existing_document(task_id: str):
    """Use existing document and mark task as completed."""
    task = task_state.get_task(task_id)

    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    if task["status"] != TaskStatus.EXISTING_FOUND.value:
        raise HTTPException(
            status_code=400,
            detail=f"Task is not in EXISTING_FOUND state. Current status: {task['status']}"
        )

    existing_docs = task.get("existing_documents", {})

    task_state.set_result(
        task_id,
        documents=existing_docs,
        payload={"used_existing": True}
    )

    return {
        "task_id": task_id,
        "status": TaskStatus.COMPLETED.value,
        "documents": existing_docs,
        "message": "Using existing document"
    }


@router.delete("/tasks/{task_id}")
def delete_task(task_id: str):
    """Permanently delete a task record (user dismissed the card)."""
    task = task_state.get_task(task_id)

    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    success = task_state.delete_task(task_id)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete task")

    return {
        "task_id": task_id,
        "message": "Task deleted successfully"
    }


@router.get("/tasks/{task_id}/result")
def get_task_result(task_id: str):
    task = task_state.get_task(task_id)

    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    if task["status"] != TaskStatus.COMPLETED.value:
        raise HTTPException(
            status_code=400,
            detail=f"Task is not completed. Current status: {task['status']}"
        )

    result = task.get("result", {})

    return {
        "task_id": task_id,
        "status": task["status"],
        "motion_type": task["motion_type"],
        "case_name": task["case_name"],
        "documents": result.get("documents", {}),
        "payload": result.get("payload", {})
    }


@router.get("/health/taskiq")
async def taskiq_health_check():
    """Check Taskiq broker health."""
    try:
        from ..taskiq_app import broker

        is_running = broker.is_worker_process or True

        return {
            "status": "healthy" if is_running else "unhealthy",
            "broker_type": type(broker).__name__,
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }


@router.post("/health/cleanup-stale")
def cleanup_stale_tasks():
    """Manually trigger cleanup of stale tasks."""
    from ..tasks.review_task_state import review_task_state

    pleading_stats = task_state.cleanup_stale_tasks(stale_threshold_minutes=15)
    review_stats = review_task_state.cleanup_stale_tasks(stale_threshold_minutes=35)

    return {
        "status": "completed",
        "pleading": pleading_stats,
        "review": review_stats,
    }


@router.get("/files/{filename}")
async def get_generated_file(filename: str):
    file_path = OUT_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    if filename.endswith(".pdf"):
        media_type = "application/pdf"
        ext = "pdf"
    elif filename.endswith(".docx"):
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ext = "docx"
    else:
        media_type = "application/octet-stream"
        ext = ""

    download_name = filename
    uuid_match = _UUID_RE.search(filename)
    if uuid_match and ext:
        session_id = uuid_match.group(0)
        prefix = filename[: uuid_match.start()].rstrip("_")
        case_name, case_number = await get_motion_case_info(session_id)
        download_name = build_download_filename(prefix, case_name, case_number, ext)

    return FileResponse(path=str(file_path), filename=download_name, media_type=media_type)


@router.put("/files/{filename}")
async def update_generated_file(filename: str, file: UploadFile = File(...)):
    """Replace an existing generated DOCX and regenerate its PDF."""
    if not filename.endswith(".docx"):
        raise HTTPException(status_code=400, detail="Only .docx files can be updated")
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    from ..tasks.pleading_helpers import GENERATED_DOCX_DIR, GENERATED_PDF_DIR

    out_docx = OUT_DIR / filename
    legacy_docx = GENERATED_DOCX_DIR / filename
    out_exists = out_docx.exists()
    legacy_exists = legacy_docx.exists()

    if not out_exists and not legacy_exists:
        raise HTTPException(status_code=404, detail="File not found")

    content = await file.read()
    if out_exists:
        out_docx.write_bytes(content)
    if legacy_exists:
        legacy_docx.write_bytes(content)

    # Regenerate PDF from updated DOCX
    from ..motion_filling.pdf_utils import convert_to_pdf_libreoffice

    conversion_source = out_docx if out_exists else legacy_docx
    conversion_out_dir = OUT_DIR if out_exists else GENERATED_PDF_DIR
    pdf_result = convert_to_pdf_libreoffice(conversion_source, conversion_out_dir)

    pdf_filename = filename[:-5] + ".pdf"
    out_pdf = OUT_DIR / pdf_filename
    legacy_pdf = GENERATED_PDF_DIR / pdf_filename
    if pdf_result and out_exists and legacy_pdf.exists():
        import shutil

        shutil.copy2(pdf_result, legacy_pdf)
    if pdf_result and legacy_exists and out_pdf.exists():
        import shutil

        shutil.copy2(pdf_result, out_pdf)

    return {"message": "Document updated", "pdf_regenerated": pdf_result is not None}
