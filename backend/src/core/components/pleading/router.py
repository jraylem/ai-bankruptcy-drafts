"""FastAPI routes for the v2 template-draft pipeline.

All REST routes require a valid JWT via the Authorization Bearer header
(`Depends(get_current_user)`). `user_id` is always derived from the decoded
token — never trusted from query params or request bodies. Cross-user task
access is blocked by ownership checks on every {task_id} route.

The SSE `/events` endpoint accepts `?token=<jwt>` in the query string
because EventSource cannot set custom headers.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Path, Query, Request, UploadFile
from fastapi.responses import Response

from src.auth.auth import get_current_user
from src.auth.models import User
from src.core.common.storage.database import (
    CaseGenerationLogRepository,
    DraftTemplateRepository,
)
from src.core.common.storage.r2 import r2_service

from . import events, state
from .broker import core_broker
from .pdf_conversion import convert_docx_bytes_to_pdf_bytes
from .schemas import (
    CaseGenerationLogResponse,
    ChildPresignedEntry,
    CompletedDocumentEnvelope,
    StartTemplateDraftRequest,
    StartTemplateDraftResponse,
    SubmitInputRequest,
    V2TemplateDraftTaskResponse,
)
from .sse import stream_events
from .tasks import run_template_draft, run_template_draft_resume

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pleading", tags=["Pleading V2"])


# ─── Helpers ───────────────────────────────────────────────────────────


async def _load_owned_task(task_id: str, user: User):
    """Fetch a task and verify the caller owns it. 404 on either miss (so we
    don't leak existence to a different user)."""
    record = await state.get(task_id)
    if record is None or record.user_id != user.id:
        raise HTTPException(status_code=404, detail="Task not found")
    return record


# ─── REST routes ───────────────────────────────────────────────────────


@router.post("/start", response_model=StartTemplateDraftResponse)
async def start_template_draft(
    req: StartTemplateDraftRequest,
    user: Annotated[User, Depends(get_current_user)],
) -> StartTemplateDraftResponse:
    """Kick off a new template-draft attempt.

    - Rejects 429 / DUPLICATE_DRAFT_IN_FLIGHT if the user already has a
      non-terminal task for the same (case, template).
    - Rejects 429 / QUEUE_FULL if the per-user queue is at its hard cap.
    - Otherwise: if under MAX_CONCURRENT_TEMPLATE_DRAFTS, kicks the worker
      with status=PENDING. If over, parks the task with status=QUEUED.
    """
    # Validate template exists + has a committed agent_config
    template = await DraftTemplateRepository.get(req.template_id)
    if template is None:
        raise HTTPException(status_code=404, detail=f"Template {req.template_id} not found")
    if not template.agent_config:
        raise HTTPException(
            status_code=400,
            detail=f"Template {req.template_id} has no committed agent config — run compose-agent-config first.",
        )
    if template.bundle_role == "child_only":
        raise HTTPException(
            status_code=400,
            detail=f"Template {req.template_id} is child-only and cannot be drafted directly.",
        )

    # Dedup guard — block firing the same draft twice while one is in-flight
    if not req.skip_existing_check:
        duplicate = await state.find_active_duplicate(
            user_id=user.id, case_id=req.case_id, template_id=req.template_id,
        )
        if duplicate is not None:
            raise HTTPException(
                status_code=429,
                detail={
                    "code": "DUPLICATE_DRAFT_IN_FLIGHT",
                    "message": "An ongoing generation is already underway for this template and case.",
                    "existing_task_id": duplicate.task_id,
                    "existing_status": duplicate.status,
                },
            )

    # Decide: kick immediately or queue
    active_count = await state.count_active_for_user(user.id)
    queue_len = await state.queue_size(user.id)

    if active_count >= state.MAX_CONCURRENT_TEMPLATE_DRAFTS:
        if queue_len >= state.MAX_QUEUED_TEMPLATE_DRAFTS:
            raise HTTPException(
                status_code=429,
                detail={
                    "code": "QUEUE_FULL",
                    "message": (
                        f"Queue is full ({state.MAX_QUEUED_TEMPLATE_DRAFTS} queued). "
                        "Wait for some drafts to finish before starting more."
                    ),
                },
            )
        record = await state.create(
            user_id=user.id,
            case_id=req.case_id,
            template_id=req.template_id,
            template_name=template.name or "",
            bundle_picks=req.bundle_picks,
            status="QUEUED",
        )
        await state.enqueue(record.task_id, user.id)
        await events.emit(user.id, record.task_id, "status_changed")
        return StartTemplateDraftResponse(task=V2TemplateDraftTaskResponse.from_record(record))

    record = await state.create(
        user_id=user.id,
        case_id=req.case_id,
        template_id=req.template_id,
        template_name=template.name or "",
        bundle_picks=req.bundle_picks,
        status="PENDING",
    )
    await events.emit(user.id, record.task_id, "status_changed")
    await run_template_draft.kiq(
        task_id=record.task_id,
        user_id=user.id,
        template_id=req.template_id,
        case_id=req.case_id,
        bundle_picks=req.bundle_picks,
        skip_existing_check=req.skip_existing_check,
    )
    return StartTemplateDraftResponse(task=V2TemplateDraftTaskResponse.from_record(record))


@router.post("/{task_id}/submit-input", response_model=V2TemplateDraftTaskResponse)
async def submit_input(
    req: SubmitInputRequest,
    task_id: Annotated[str, Path()],
    user: Annotated[User, Depends(get_current_user)],
) -> V2TemplateDraftTaskResponse:
    """Forward the user's USER_INPUT picks to the worker — resumes the draft."""
    record = await _load_owned_task(task_id, user)
    if record.status != "AWAITING_INPUT":
        raise HTTPException(
            status_code=409,
            detail=f"Task is not awaiting input (status={record.status})",
        )

    user_picks_payload = {k: v.model_dump() for k, v in req.user_picks.items()}
    await run_template_draft_resume.kiq(
        task_id=task_id,
        user_id=user.id,
        user_picks=user_picks_payload,
    )
    return V2TemplateDraftTaskResponse.from_record(record)


@router.post("/{task_id}/use-existing", response_model=V2TemplateDraftTaskResponse)
async def use_existing(
    task_id: Annotated[str, Path()],
    user: Annotated[User, Depends(get_current_user)],
) -> V2TemplateDraftTaskResponse:
    """Adopt the EXISTING_FOUND log as the task's result — no worker run."""
    record = await _load_owned_task(task_id, user)
    if record.status != "EXISTING_FOUND" or record.existing_log_id is None:
        raise HTTPException(
            status_code=409,
            detail="Task is not in EXISTING_FOUND state",
        )

    existing_log = await CaseGenerationLogRepository.get(record.existing_log_id)
    if existing_log is None:
        raise HTTPException(status_code=404, detail="Existing generation log not found")

    # Flip task → COMPLETED, point at the existing log (no new log row).
    updated = await state.set_completed(task_id, result=None, log_id=existing_log.id)
    await events.emit(user.id, task_id, "completed")
    # Adopting an existing doc still frees a slot — drain any QUEUED siblings.
    from .tasks import _try_drain_user_queue
    await _try_drain_user_queue(user.id)
    return V2TemplateDraftTaskResponse.from_record(updated or record)


@router.post("/{task_id}/regenerate", response_model=V2TemplateDraftTaskResponse)
async def regenerate(
    task_id: Annotated[str, Path()],
    user: Annotated[User, Depends(get_current_user)],
) -> V2TemplateDraftTaskResponse:
    """Re-enqueue the draft for this task — bypasses the EXISTING_FOUND check."""
    record = await _load_owned_task(task_id, user)
    if record.status not in {"EXISTING_FOUND", "COMPLETED", "FAILED"}:
        raise HTTPException(
            status_code=409,
            detail=f"Regenerate is only valid from EXISTING_FOUND, COMPLETED, or FAILED (status={record.status})",
        )

    # Reset state for the fresh run
    record.status = "PENDING"
    record.result = None
    record.error = None
    record.log_id = None
    record.existing_log_id = None
    record.resolved_values = None
    record.pending_inputs = None
    await state._persist(record)
    await events.emit(user.id, task_id, "status_changed")

    await run_template_draft.kiq(
        task_id=task_id,
        user_id=user.id,
        template_id=record.template_id,
        case_id=record.case_id,
        bundle_picks=record.bundle_picks,
        skip_existing_check=True,
    )
    return V2TemplateDraftTaskResponse.from_record(record)


@router.post("/{task_id}/cancel", response_model=V2TemplateDraftTaskResponse)
async def cancel_task(
    task_id: Annotated[str, Path()],
    user: Annotated[User, Depends(get_current_user)],
) -> V2TemplateDraftTaskResponse:
    """Mark a task CANCELLED. Pre-DRAFTING tasks (incl. QUEUED) skip the worker entirely."""
    record = await _load_owned_task(task_id, user)
    if record.status in {"COMPLETED", "FAILED", "CANCELLED"}:
        raise HTTPException(
            status_code=409,
            detail=f"Task already terminal (status={record.status})",
        )

    if record.status == "QUEUED":
        await state.remove_from_queue(task_id, user.id)

    updated = await state.set_cancelled(task_id)
    await events.emit(user.id, task_id, "cancelled")
    # If a slot freed up (cancelled active task), drain the queue.
    from .tasks import _try_drain_user_queue
    await _try_drain_user_queue(user.id)
    return V2TemplateDraftTaskResponse.from_record(updated or record)


@router.delete("/{task_id}")
async def dismiss_task(
    task_id: Annotated[str, Path()],
    user: Annotated[User, Depends(get_current_user)],
) -> dict:
    """Remove a task record from Redis (sidebar dismiss). No-op if missing."""
    record = await state.get(task_id)
    if record is None:
        return {"dismissed": False}
    if record.user_id != user.id:
        raise HTTPException(status_code=404, detail="Task not found")
    await state.delete(task_id)
    await events.emit_removed(user.id, task_id)
    return {"dismissed": True}


@router.get("/tasks", response_model=list[V2TemplateDraftTaskResponse])
async def list_tasks(
    user: Annotated[User, Depends(get_current_user)],
    case_id: str | None = Query(default=None, description="Optional case filter"),
) -> list[V2TemplateDraftTaskResponse]:
    """List the user's tasks (for snapshot rehydration on FE mount)."""
    records = await state.list_for_user(user.id)
    if case_id:
        records = [r for r in records if r.case_id == case_id]
    return [V2TemplateDraftTaskResponse.from_record(r) for r in records]


@router.get("/case-generation-logs", response_model=list[CaseGenerationLogResponse])
async def list_case_generation_logs(
    user: Annotated[User, Depends(get_current_user)],
    case_id: str = Query(..., description="Case to list generation history for"),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[CaseGenerationLogResponse]:
    """History view — every draft attempt for the (user, case) pair."""
    rows = await CaseGenerationLogRepository.list_for_case(
        user_id=user.id, case_id=case_id, limit=limit,
    )
    return [
        CaseGenerationLogResponse(
            id=row.id,
            user_id=row.user_id,
            case_id=row.case_id,
            draft_template_id=row.draft_template_id,
            template_name=row.template_name,
            status=row.status,
            task_id=row.task_id,
            error=row.error,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
        for row in rows
    ]


@router.get(
    "/case-generation-logs/{log_id}/download-url",
    response_model=CompletedDocumentEnvelope,
)
async def get_log_download_urls(
    log_id: Annotated[str, Path()],
    user: Annotated[User, Depends(get_current_user)],
) -> CompletedDocumentEnvelope:
    """Re-sign the log's parent + children R2 keys and return fresh presigned URLs (~1h TTL)."""
    log = await CaseGenerationLogRepository.get(log_id)
    if log is None or log.user_id != user.id:
        raise HTTPException(status_code=404, detail="Log not found")
    if log.status != "COMPLETED" or log.r2_object_key is None:
        raise HTTPException(
            status_code=409,
            detail=f"Log is not in a downloadable state (status={log.status})",
        )

    parent_url = await r2_service.get_presigned_url_by_key(log.r2_object_key)

    children: list[ChildPresignedEntry] = []
    for raw_child in log.children or []:
        try:
            child_url = await r2_service.get_presigned_url_by_key(raw_child["r2_object_key"])
            children.append(
                ChildPresignedEntry(
                    template_id=raw_child["template_id"],
                    template_name=raw_child["template_name"],
                    companion_label=raw_child["companion_label"],
                    url=child_url,
                )
            )
        except Exception as exc:
            logger.warning(
                "Failed to re-sign child for log %s child=%s: %s",
                log_id, raw_child.get("template_id"), exc,
            )

    return CompletedDocumentEnvelope(
        log_id=log.id,
        parent_template_id=log.draft_template_id,
        parent_url=parent_url,
        children=children,
    )


@router.get("/case-generation-logs/{log_id}/download-pdf")
async def download_log_as_pdf(
    log_id: Annotated[str, Path()],
    user: Annotated[User, Depends(get_current_user)],
    child_index: int | None = Query(
        default=None,
        description="Bundle child index; omit for the parent docx.",
    ),
) -> Response:
    """Convert the log's docx (parent or one child) to PDF on demand and stream the bytes.

    Tier 1: lazy convert on every request (no R2 caching). Each call pays the
    ~3-5s LibreOffice conversion. A follow-up tier will cache the result on
    the log row so repeat downloads are instant.
    """
    log = await CaseGenerationLogRepository.get(log_id)
    if log is None or log.user_id != user.id:
        raise HTTPException(status_code=404, detail="Log not found")
    if log.status != "COMPLETED":
        raise HTTPException(
            status_code=409,
            detail=f"Log is not in a downloadable state (status={log.status})",
        )

    if child_index is None:
        if log.r2_object_key is None:
            raise HTTPException(status_code=409, detail="Log has no parent r2_object_key.")
        target_key: str = log.r2_object_key
        filename_stem: str = log.template_name or "document"
    else:
        children = log.children or []
        if child_index < 0 or child_index >= len(children):
            raise HTTPException(
                status_code=404,
                detail=f"Child index {child_index} out of range (have {len(children)}).",
            )
        child_key = children[child_index].get("r2_object_key")
        if not child_key:
            raise HTTPException(status_code=409, detail="Child has no r2_object_key.")
        target_key = child_key
        filename_stem = children[child_index].get("template_name") or "document"

    try:
        docx_bytes = await r2_service.download_by_key(target_key)
    except Exception as exc:
        logger.exception(
            "Failed to fetch docx from R2 for log %s key=%s",
            log_id,
            target_key,
        )
        raise HTTPException(
            status_code=502,
            detail="Failed to fetch source docx from storage",
        ) from exc

    try:
        pdf_bytes = await convert_docx_bytes_to_pdf_bytes(docx_bytes)
    except Exception as exc:
        logger.exception(
            "PDF conversion failed for log %s child_index=%s",
            log_id,
            child_index,
        )
        raise HTTPException(
            status_code=500,
            detail="PDF conversion failed. Please try again.",
        ) from exc

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename_stem}.pdf"',
            "Content-Length": str(len(pdf_bytes)),
        },
    )


@router.put("/case-generation-logs/{log_id}/docx")
async def autosave_log_docx(
    log_id: Annotated[str, Path()],
    user: Annotated[User, Depends(get_current_user)],
    file: UploadFile = File(...),
    child_index: int | None = Query(default=None, description="Bundle child index; omit for the parent docx."),
) -> dict:
    """Overwrite the docx bytes for a completed log's parent (or a bundle child).

    Used by the v2 document viewer's autosave loop. Multipart body field `file`
    must carry the docx blob. Ownership-checked; only valid against COMPLETED logs.
    """
    log = await CaseGenerationLogRepository.get(log_id)
    if log is None or log.user_id != user.id:
        raise HTTPException(status_code=404, detail="Log not found")
    if log.status != "COMPLETED":
        raise HTTPException(
            status_code=409,
            detail=f"Log is not COMPLETED (status={log.status}) — cannot autosave.",
        )

    if file.filename and not file.filename.lower().endswith(".docx"):
        raise HTTPException(status_code=400, detail="Only .docx files can be autosaved.")
    content_type = file.content_type or "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    bytes_payload = await file.read()
    if not bytes_payload:
        raise HTTPException(status_code=400, detail="Empty file body.")

    if child_index is None:
        if log.r2_object_key is None:
            raise HTTPException(status_code=409, detail="Log has no parent r2_object_key.")
        target_key = log.r2_object_key
    else:
        children = log.children or []
        if child_index < 0 or child_index >= len(children):
            raise HTTPException(
                status_code=404,
                detail=f"Child index {child_index} out of range (have {len(children)}).",
            )
        target_key = children[child_index].get("r2_object_key")
        if not target_key:
            raise HTTPException(status_code=409, detail="Child has no r2_object_key.")

    try:
        await r2_service.upload_by_key(
            key=target_key,
            file_content=bytes_payload,
            content_type=content_type,
        )
    except Exception as exc:
        logger.exception("Failed to autosave docx for log %s key=%s", log_id, target_key)
        raise HTTPException(status_code=502, detail=f"R2 upload failed: {exc}") from exc

    # Touch the log's updated_at so list_for_case picks up the recency.
    refreshed = await CaseGenerationLogRepository.update_status(log.id, status="COMPLETED")
    return {
        "ok": True,
        "log_id": log.id,
        "r2_object_key": target_key,
        "child_index": child_index,
        "updated_at": (refreshed.updated_at if refreshed else log.updated_at),
    }


# ─── SSE ───────────────────────────────────────────────────────────────
# Registered BEFORE the catch-all GET /{task_id} so "events" isn't matched
# as a task_id (which carries `Depends(get_current_user)` and would 403 the
# query-param-token request).
router.get("/events")(stream_events)


@router.get("/{task_id}", response_model=V2TemplateDraftTaskResponse)
async def get_task(
    task_id: Annotated[str, Path()],
    user: Annotated[User, Depends(get_current_user)],
) -> V2TemplateDraftTaskResponse:
    """Refresh one task on demand."""
    record = await _load_owned_task(task_id, user)
    return V2TemplateDraftTaskResponse.from_record(record)
