"""V2 dry-run-async taskiq tasks.

Two coroutines, both decorated against `core_broker` (same broker v1
pleading + Phase 2.6A composer-async use — queue `taskiq:core`). No
new worker container needed; v2 dry-run tasks ride alongside the
existing v1 pleading + composer-async tasks on the existing
`taskiq_worker_core` service.

- `run_dry_run_initial` — first POST. PENDING → RUNNING →
  AWAITING_INPUT (paused, returns) OR COMPLETED / FAILED.
- `run_dry_run_resume` — /submit-input POST. RESUMING → COMPLETED /
  FAILED.

Both call directly into the existing sync dry-run services
(`execute_dry_run_v2`, `resume_dry_run_v2`) — no fork, no
reimplementation. The async layer just adds Taskiq + Redis state +
SSE around the work.
"""

from __future__ import annotations

import logging

from src.core.common.cost_tracking import cost_attribution
from src.core.components.pleading.broker import core_broker
from src.core.studio_v2.services.dry_run.service import (
    execute_dry_run_v2,
    resume_dry_run_v2,
)
from src.core.studio_v2.types.orchestration import (
    AwaitingInputResponseV2,
    DryRunResponseV2,
)

from . import events, state

logger = logging.getLogger(__name__)


async def _try_drain_user_queue(user_id: str) -> None:
    """At every terminal transition, see if a QUEUED task is waiting
    for a slot. Pops the oldest queued task_id, flips its status
    QUEUED → PENDING, and kicks the initial worker (queued tasks
    haven't started yet, so they always need run_dry_run_initial).
    """
    next_task_id = await state.drain_queue(user_id)
    if next_task_id is None:
        return
    record = await state.get(next_task_id)
    if record is None:
        logger.warning("dry-run drain_queue: task %s vanished, skipping", next_task_id)
        return
    await state.set_status(next_task_id, "PENDING")
    await events.emit(user_id, next_task_id, "status_changed")
    await run_dry_run_initial.kiq(task_id=next_task_id, user_id=user_id)


@core_broker.task
async def run_dry_run_initial(task_id: str, user_id: str) -> None:
    """First worker pass — calls `execute_dry_run_v2`. The result is
    either a completed `DryRunResponseV2` (no user input needed) or an
    `AwaitingInputResponseV2` (pause point; resume happens in
    `run_dry_run_resume`).
    """
    record = await state.get(task_id)
    if record is None:
        logger.warning("run_dry_run_initial: task %s vanished before start", task_id)
        return
    with cost_attribution(
        firm_id=record.firm_id,
        user_id=user_id,
        session_id=task_id,
        semantic_id=task_id,
        semantic_id_kind="dry_run_async_v2",
    ):
        await _run_dry_run_initial_impl(task_id=task_id, user_id=user_id, record=record)


async def _run_dry_run_initial_impl(*, task_id: str, user_id: str, record) -> None:
    if await state.is_cancelled(task_id):
        logger.info("run_dry_run_initial: task %s already cancelled at start", task_id)
        return

    await state.set_status(task_id, "RUNNING")
    await events.emit(user_id, task_id, "status_changed")

    try:
        result = await execute_dry_run_v2(
            template_id=record.template_id,
            template_spec=record.template_spec,
            case_id=record.case_id,
            bundle_picks=record.bundle_picks,
            candidate_bundle_role=record.bundle_role,
            candidate_bundle_companions=record.bundle_companions,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("execute_dry_run_v2 failed for task %s", task_id)
        await state.set_failed(task_id, str(exc))
        await events.emit(user_id, task_id, "failed")
        await _try_drain_user_queue(user_id)
        return

    if await state.is_cancelled(task_id):
        logger.info(
            "run_dry_run_initial: task %s cancelled before persisting result",
            task_id,
        )
        await _try_drain_user_queue(user_id)
        return

    if isinstance(result, AwaitingInputResponseV2):
        await state.set_awaiting_input(
            task_id,
            resolved_values=result.resolved_values,
            pending_inputs=result.pending_inputs,
        )
        await events.emit(user_id, task_id, "awaiting_input")
        # NOTE: do NOT drain the queue here — this task still holds a
        # concurrency slot until it either completes (post-resume) or
        # is cancelled. Draining now would let a queued task barge in
        # and double-spend the user's slot budget.
        return

    # Result is DryRunResponseV2 — completed in one shot, no pause.
    assert isinstance(result, DryRunResponseV2)
    await state.set_completed(task_id, result=result)
    await events.emit(user_id, task_id, "completed")
    await _try_drain_user_queue(user_id)


@core_broker.task
async def run_dry_run_resume(task_id: str, user_id: str) -> None:
    """Resume worker pass — calls `resume_dry_run_v2` with the
    paralegal's picks stashed on the record by /submit-input.
    """
    record = await state.get(task_id)
    if record is None:
        logger.warning("run_dry_run_resume: task %s vanished before start", task_id)
        return
    with cost_attribution(
        firm_id=record.firm_id,
        user_id=user_id,
        session_id=task_id,
        semantic_id=task_id,
        semantic_id_kind="dry_run_async_v2",
    ):
        await _run_dry_run_resume_impl(task_id=task_id, user_id=user_id, record=record)


async def _run_dry_run_resume_impl(*, task_id: str, user_id: str, record) -> None:
    if await state.is_cancelled(task_id):
        logger.info("run_dry_run_resume: task %s already cancelled at start", task_id)
        return
    if record.user_picks is None or record.resolved_values is None:
        await state.set_failed(
            task_id,
            "Resume invoked but user_picks / resolved_values missing on record",
        )
        await events.emit(user_id, task_id, "failed")
        await _try_drain_user_queue(user_id)
        return

    # /submit-input already flipped status → RESUMING; emit a fresh
    # status_changed so the FE card spinner refreshes.
    await events.emit(user_id, task_id, "status_changed")

    try:
        result = await resume_dry_run_v2(
            template_id=record.template_id,
            template_spec=record.template_spec,
            case_id=record.case_id,
            resolved_values=record.resolved_values,
            user_picks=record.user_picks,
            pending_inputs=record.pending_inputs,
            bundle_picks=record.bundle_picks,
            candidate_bundle_role=record.bundle_role,
            candidate_bundle_companions=record.bundle_companions,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("resume_dry_run_v2 failed for task %s", task_id)
        await state.set_failed(task_id, str(exc))
        await events.emit(user_id, task_id, "failed")
        await _try_drain_user_queue(user_id)
        return

    if await state.is_cancelled(task_id):
        logger.info(
            "run_dry_run_resume: task %s cancelled before persisting result",
            task_id,
        )
        await _try_drain_user_queue(user_id)
        return

    await state.set_completed(task_id, result=result)
    await events.emit(user_id, task_id, "completed")
    await _try_drain_user_queue(user_id)
