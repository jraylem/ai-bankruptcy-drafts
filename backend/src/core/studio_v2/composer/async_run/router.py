"""FastAPI routes for the v2 composer-async pipeline.

All REST routes require a valid JWT via the Authorization Bearer
header (`Depends(get_current_user)`). `user_id` is derived from the
decoded token — never trusted from query params or request bodies.
Cross-user task access is blocked by ownership checks on every
{task_id} route.

The SSE `/events` endpoint accepts `?token=<jwt>` in the query string
because EventSource cannot set custom headers.

Mounted at `/api/v3/studio/composer-async/*`. Sibling endpoints under
`/api/v3/studio/composer/*` (sync `generate-template`, `parse`, etc.)
stay in place during the transition; the FE picks which to call.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Path,
    Request,
    UploadFile,
)

from src.auth.auth import get_current_user
from src.auth.models import User
from src.core.studio_v2.repositories import TemplatesV2Repository

from . import events, state
from .schemas import (
    StartComposerTaskResponse,
    StartRegenerateRequest,
    V2ComposerTaskResponse,
)
from .sse import stream_events
from .tasks import run_composer_generate, run_composer_regenerate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/studio/composer-async", tags=["Composer Async (Studio V2)"])


# ─── Helpers ───────────────────────────────────────────────────────────


async def _load_owned_task(task_id: str, user: User):
    """Fetch a task and verify the caller owns it. 404 on either miss
    so we don't leak existence to a different user."""
    record = await state.get(task_id)
    if record is None or record.user_id != user.id:
        raise HTTPException(status_code=404, detail="Task not found")
    return record


async def _enforce_queue_caps(user_id: str) -> bool:
    """Returns True when the task should be QUEUED rather than kicked
    immediately. Raises 429 when even the queue is full.
    """
    active_count = await state.count_active_for_user(user_id)
    queue_len = await state.queue_size(user_id)
    if active_count >= state.MAX_CONCURRENT_COMPOSER_TASKS:
        if queue_len >= state.MAX_QUEUED_COMPOSER_TASKS:
            raise HTTPException(
                status_code=429,
                detail={
                    "code": "QUEUE_FULL",
                    "message": (
                        f"Composer queue is full ({state.MAX_QUEUED_COMPOSER_TASKS} queued). "
                        "Wait for some tasks to finish before starting more."
                    ),
                },
            )
        return True
    return False


# ─── REST routes ───────────────────────────────────────────────────────


@router.post("/generate", response_model=StartComposerTaskResponse)
async def start_generate(
    user: Annotated[User, Depends(get_current_user)],
    file: Annotated[UploadFile, File(...)],
    template_name: Annotated[str, Form(...)],
    template_role: Annotated[str, Form()] = "single",
) -> StartComposerTaskResponse:
    """Kick off an async template-generation task.

    Multipart body: `file` (the .docx) + `template_name` + `template_role`.
    Returns immediately with `{task_id, status}`. The FE subscribes to
    SSE `/events` to receive status_changed → completed/failed.
    """
    if template_role not in ("single", "master", "part_of_packet"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid template_role: {template_role}",
        )
    file_content = await file.read()
    if not file_content:
        raise HTTPException(status_code=400, detail="Empty upload")

    should_queue = await _enforce_queue_caps(user.id)

    blob_key = await state.stage_upload_blob(file_content)

    record = await state.create(
        user_id=user.id,
        firm_id=getattr(user, "firm_id", None),
        kind="generate",
        template_name=template_name,
        template_role=template_role,
        original_filename=file.filename or "uploaded.docx",
        upload_blob_key=blob_key,
        status="QUEUED" if should_queue else "PENDING",
    )

    if should_queue:
        await state.enqueue(record.task_id, user.id)
        await events.emit(user.id, record.task_id, "status_changed")
        return StartComposerTaskResponse(task_id=record.task_id, status=record.status)

    await events.emit(user.id, record.task_id, "status_changed")
    await run_composer_generate.kiq(task_id=record.task_id, user_id=user.id)
    return StartComposerTaskResponse(task_id=record.task_id, status=record.status)


@router.post("/regenerate", response_model=StartComposerTaskResponse)
async def start_regenerate(
    req: StartRegenerateRequest,
    user: Annotated[User, Depends(get_current_user)],
) -> StartComposerTaskResponse:
    """Kick off an async template-regeneration (re-extract) task.

    Body: `template_id` + optional `ignored_texts`, `merges`,
    `regeneration_instruction`. Returns immediately with task_id.
    """
    template = await TemplatesV2Repository.get(req.template_id)
    if template is None:
        raise HTTPException(
            status_code=404,
            detail=f"Template {req.template_id} not found",
        )

    should_queue = await _enforce_queue_caps(user.id)

    record = await state.create(
        user_id=user.id,
        firm_id=getattr(user, "firm_id", None),
        kind="regenerate",
        template_name=getattr(template, "name", "") or "",
        template_id=req.template_id,
        ignored_texts=req.ignored_texts,
        merges=req.merges,
        regeneration_instruction=req.regeneration_instruction,
        status="QUEUED" if should_queue else "PENDING",
    )

    if should_queue:
        await state.enqueue(record.task_id, user.id)
        await events.emit(user.id, record.task_id, "status_changed")
        return StartComposerTaskResponse(task_id=record.task_id, status=record.status)

    await events.emit(user.id, record.task_id, "status_changed")
    await run_composer_regenerate.kiq(task_id=record.task_id, user_id=user.id)
    return StartComposerTaskResponse(task_id=record.task_id, status=record.status)


@router.post("/{task_id}/cancel", response_model=V2ComposerTaskResponse)
async def cancel_task(
    task_id: Annotated[str, Path()],
    user: Annotated[User, Depends(get_current_user)],
) -> V2ComposerTaskResponse:
    """Mark a task CANCELLED. Worker checks the cancel flag at the
    start of each phase and stops persisting results."""
    record = await _load_owned_task(task_id, user)
    if record.status in ("COMPLETED", "FAILED", "CANCELLED"):
        return V2ComposerTaskResponse.from_record(record)

    if record.status == "QUEUED":
        await state.remove_from_queue(task_id, user.id)
    updated = await state.set_cancelled(task_id)
    await events.emit(user.id, task_id, "cancelled")
    return V2ComposerTaskResponse.from_record(updated or record)


@router.delete("/{task_id}")
async def delete_task(
    task_id: Annotated[str, Path()],
    user: Annotated[User, Depends(get_current_user)],
) -> dict:
    """Hard-delete the task record (FE dismisses a finished card)."""
    record = await _load_owned_task(task_id, user)
    await state.delete(task_id)
    await events.emit_removed(user.id, task_id)
    return {"removed": True, "task_id": task_id}


@router.get("/tasks", response_model=list[V2ComposerTaskResponse])
async def list_user_tasks(
    user: Annotated[User, Depends(get_current_user)],
) -> list[V2ComposerTaskResponse]:
    """Polling fallback / cold-rehydrate for the FE strip."""
    records = await state.list_for_user(user.id)
    return [V2ComposerTaskResponse.from_record(r) for r in records]


@router.get("/tasks/{task_id}", response_model=V2ComposerTaskResponse)
async def get_task(
    task_id: Annotated[str, Path()],
    user: Annotated[User, Depends(get_current_user)],
) -> V2ComposerTaskResponse:
    """Polling fallback for a single card. SSE-driven UIs don't need
    this; included for FE robustness on flaky proxies."""
    record = await _load_owned_task(task_id, user)
    return V2ComposerTaskResponse.from_record(record)


@router.get("/events")
async def events_stream(request: Request):
    """SSE stream for the user's composer tasks."""
    return await stream_events(request)
