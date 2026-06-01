"""FastAPI routes for the v2 dry-run-async pipeline.

All REST routes require a valid JWT via the Authorization Bearer
header (`Depends(get_current_user)`). `user_id` is derived from the
decoded token — never trusted from query params or request bodies.
Cross-user task access is blocked by ownership checks on every
{task_id} route.

The SSE `/events` endpoint accepts `?token=<jwt>` in the query string
because EventSource cannot set custom headers.

Mounted at `/api/v3/studio/dry-run-async/*`. Sibling endpoints under
`/api/v3/studio/templates/{id}/dry-run[/resume]` (sync, no Taskiq)
stay in place during the transition; the FE picks which to call.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Path,
    Request,
)

from src.auth.auth import get_current_user
from src.auth.models import User
from src.core.common.storage.database import CaseRepository
from src.core.studio_v2.repositories import TemplatesV2Repository

from . import events, state
from .schemas import (
    StartDryRunRequest,
    StartDryRunResponse,
    SubmitInputRequest,
    V2DryRunTaskResponse,
)
from .sse import stream_events
from .tasks import run_dry_run_initial, run_dry_run_resume

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/studio/dry-run-async",
    tags=["Dry Run Async (Studio V2)"],
)


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
    if active_count >= state.MAX_CONCURRENT_DRY_RUN_TASKS:
        if queue_len >= state.MAX_QUEUED_DRY_RUN_TASKS:
            raise HTTPException(
                status_code=429,
                detail={
                    "code": "QUEUE_FULL",
                    "message": (
                        f"Dry-run queue is full ({state.MAX_QUEUED_DRY_RUN_TASKS} queued). "
                        "Wait for some runs to finish before starting more."
                    ),
                },
            )
        return True
    return False


# ─── REST routes ───────────────────────────────────────────────────────


@router.post("/start", response_model=StartDryRunResponse)
async def start_dry_run(
    req: StartDryRunRequest,
    user: Annotated[User, Depends(get_current_user)],
) -> StartDryRunResponse:
    """Kick off an async dry-run task.

    Body matches the sync `DryRunRequestV2` shape exactly so FE code
    can switch between the two with a single base-URL flip.

    Returns immediately with `{task_id, status}`. The FE subscribes
    to SSE `/events` to receive status_changed → awaiting_input /
    completed / failed transitions.
    """
    template = await TemplatesV2Repository.get(req.template_id)
    if template is None:
        raise HTTPException(
            status_code=404,
            detail=f"Template {req.template_id} not found",
        )
    case = await CaseRepository.get(req.case_id)
    if case is None:
        raise HTTPException(
            status_code=404,
            detail=f"Case {req.case_id} not found",
        )

    should_queue = await _enforce_queue_caps(user.id)

    record = await state.create(
        user_id=user.id,
        firm_id=getattr(user, "firm_id", None),
        template_id=req.template_id,
        case_id=req.case_id,
        template_name=getattr(template, "name", "") or "",
        case_label=getattr(case, "case_number", "") or getattr(case, "legacy_id", "") or "",
        template_spec=req.template_spec,
        bundle_picks=req.bundle_picks,
        bundle_role=req.bundle_role,
        bundle_companions=req.bundle_companions,
        status="QUEUED" if should_queue else "PENDING",
    )

    if should_queue:
        await state.enqueue(record.task_id, user.id)
        await events.emit(user.id, record.task_id, "status_changed")
        return StartDryRunResponse(task_id=record.task_id, status=record.status)

    await events.emit(user.id, record.task_id, "status_changed")
    await run_dry_run_initial.kiq(task_id=record.task_id, user_id=user.id)
    return StartDryRunResponse(task_id=record.task_id, status=record.status)


@router.post("/{task_id}/submit-input", response_model=StartDryRunResponse)
async def submit_input(
    task_id: Annotated[str, Path()],
    req: SubmitInputRequest,
    user: Annotated[User, Depends(get_current_user)],
) -> StartDryRunResponse:
    """Resume a paused dry-run with the paralegal's picks.

    Only valid when the task is AWAITING_INPUT. Stashes user_picks
    (and optionally an amended bundle_picks) on the record, flips the
    status to RESUMING, and enqueues `run_dry_run_resume`.
    """
    record = await _load_owned_task(task_id, user)
    if record.status != "AWAITING_INPUT":
        raise HTTPException(
            status_code=409,
            detail=f"Task is in status {record.status}; submit-input requires AWAITING_INPUT",
        )

    # `user_picks` value type is UserSelectionV2 — a discriminated
    # union. Round-trip through model_dump so the persisted record
    # carries plain dicts (Pydantic will re-validate on read).
    user_picks_dump: dict[str, Any] = {
        k: (v.model_dump() if hasattr(v, "model_dump") else v)
        for k, v in req.user_picks.items()
    }

    await state.set_user_picks(
        task_id,
        user_picks=user_picks_dump,
        bundle_picks=req.bundle_picks,
    )
    await events.emit(user.id, task_id, "status_changed")
    await run_dry_run_resume.kiq(task_id=task_id, user_id=user.id)
    refreshed = await state.get(task_id)
    return StartDryRunResponse(
        task_id=task_id,
        status=refreshed.status if refreshed else "RESUMING",
    )


@router.post("/{task_id}/cancel", response_model=V2DryRunTaskResponse)
async def cancel_task(
    task_id: Annotated[str, Path()],
    user: Annotated[User, Depends(get_current_user)],
) -> V2DryRunTaskResponse:
    """Mark a task CANCELLED. Worker checks the cancel flag at the
    start of each phase and stops persisting results."""
    record = await _load_owned_task(task_id, user)
    if record.status in ("COMPLETED", "FAILED", "CANCELLED"):
        return V2DryRunTaskResponse.from_record(record)

    if record.status == "QUEUED":
        await state.remove_from_queue(task_id, user.id)
    updated = await state.set_cancelled(task_id)
    await events.emit(user.id, task_id, "cancelled")
    return V2DryRunTaskResponse.from_record(updated or record)


@router.delete("/{task_id}")
async def delete_task(
    task_id: Annotated[str, Path()],
    user: Annotated[User, Depends(get_current_user)],
) -> dict:
    """Hard-delete the task record (FE dismisses a finished card)."""
    await _load_owned_task(task_id, user)
    await state.delete(task_id)
    await events.emit_removed(user.id, task_id)
    return {"removed": True, "task_id": task_id}


@router.get("/tasks", response_model=list[V2DryRunTaskResponse])
async def list_user_tasks(
    user: Annotated[User, Depends(get_current_user)],
) -> list[V2DryRunTaskResponse]:
    """Polling fallback / cold-rehydrate for the FE rail section."""
    records = await state.list_for_user(user.id)
    return [V2DryRunTaskResponse.from_record(r) for r in records]


@router.get("/tasks/{task_id}", response_model=V2DryRunTaskResponse)
async def get_task(
    task_id: Annotated[str, Path()],
    user: Annotated[User, Depends(get_current_user)],
) -> V2DryRunTaskResponse:
    """Polling fallback for a single card. SSE-driven UIs don't need
    this; included for FE robustness on flaky proxies."""
    record = await _load_owned_task(task_id, user)
    return V2DryRunTaskResponse.from_record(record)


@router.get("/events")
async def events_stream(request: Request):
    """SSE stream for the user's dry-run tasks."""
    return await stream_events(request)
