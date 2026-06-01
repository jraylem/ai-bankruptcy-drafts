"""V2 template-draft taskiq tasks.

Two coroutines, both decorated against `core_broker` (which lives in
`broker.py`):

- `run_template_draft` — kicks off a fresh draft. CHECKING_EXISTING ->
  EXISTING_FOUND OR DRAFTING -> COMPLETED / AWAITING_INPUT / FAILED.
- `run_template_draft_resume` — picks up after the user submits picks
  from the AWAITING_INPUT modal. DRAFTING -> COMPLETED / AWAITING_INPUT
  again / FAILED.

Both call directly into the studio draft engine
(`src.core.components.engines.draft.service`) — no fork, no reimplementation.
"""

from __future__ import annotations

import logging

from pydantic import TypeAdapter

from src.core.agents.resolvers.user_input_resolver import (
    AwaitingInputResponse,
    UserSelection,
)
from src.core.agents.types.resolution import ResolvedTemplateValue
from src.core.common.cost_tracking import cost_attribution
from src.core.common.storage.database import CaseGenerationLogRepository
from src.core.components.engines.draft.service import (
    execute_draft_for_case,
    resume_draft,
)

from . import events, state
from .broker import core_broker

logger = logging.getLogger(__name__)


# UserSelection is a discriminated union (Group/SingleValue/SupportingDocs/MultiSelect)
# — direct `UserSelection(**v)` fails with `'types.UnionType' object is not callable`.
# TypeAdapter routes each dict into the right variant via the union discriminator.
_USER_PICKS_ADAPTER: TypeAdapter[dict[str, UserSelection]] = TypeAdapter(
    dict[str, UserSelection]
)


def _user_picks_from_payload(raw: dict[str, dict]) -> dict[str, UserSelection]:
    return _USER_PICKS_ADAPTER.validate_python(raw)


def _resolved_values_from_record(raw) -> list[ResolvedTemplateValue]:
    if raw is None:
        return []
    return [ResolvedTemplateValue(**v) if isinstance(v, dict) else v for v in raw]


async def _resolve_firm_id(user_id: str) -> str | None:
    """Best-effort look-up of firm_id for cost-attribution. Returns None
    on any failure — cost logging proceeds without firm scoping, which
    just means the row won't roll up into the per-firm dashboard total."""
    try:
        from src.auth.auth import get_user_by_id
        user = await get_user_by_id(user_id)
        return getattr(user, "firm_id", None) if user else None
    except Exception as e:
        logger.warning("_resolve_firm_id failed for user=%s: %s", user_id, e)
        return None


async def _try_drain_user_queue(user_id: str) -> None:
    """At every terminal transition, see if a QUEUED task is waiting for a slot.

    Pops the oldest queued task_id, flips its status QUEUED -> PENDING, kicks
    the worker. Emits status_changed so the FE sees the pill light up.
    """
    next_task_id = await state.drain_queue(user_id)
    if next_task_id is None:
        return
    record = await state.get(next_task_id)
    if record is None:
        logger.warning("drain_queue: task %s vanished, skipping", next_task_id)
        return
    await state.set_status(next_task_id, "PENDING")
    await events.emit(user_id, next_task_id, "status_changed")
    await run_template_draft.kiq(
        task_id=next_task_id,
        user_id=user_id,
        template_id=record.template_id,
        case_id=record.case_id,
        bundle_picks=record.bundle_picks,
        skip_existing_check=False,
    )


@core_broker.task
async def run_template_draft(
    task_id: str,
    user_id: str,
    template_id: str,
    case_id: str,
    bundle_picks: dict[str, str] | None,
    skip_existing_check: bool = False,
) -> None:
    """Initial draft attempt.

    On EXISTING_FOUND, parks the task awaiting `/use-existing` or
    `/regenerate`. On AwaitingInputResponse, parks awaiting `/submit-input`.
    On DraftResponse, persists to case_generation_logs + flips COMPLETED.
    """
    firm_id = await _resolve_firm_id(user_id)
    with cost_attribution(
        firm_id=firm_id, case_id=case_id, user_id=user_id, session_id=task_id,
        semantic_id=task_id, semantic_id_kind="pleading_run",
    ):
        await _run_template_draft_impl(
            task_id=task_id,
            user_id=user_id,
            template_id=template_id,
            case_id=case_id,
            bundle_picks=bundle_picks,
            skip_existing_check=skip_existing_check,
        )


async def _run_template_draft_impl(
    *,
    task_id: str,
    user_id: str,
    template_id: str,
    case_id: str,
    bundle_picks: dict[str, str] | None,
    skip_existing_check: bool = False,
) -> None:
    # 0. Cancellation check (cheapest)
    if await state.is_cancelled(task_id):
        logger.info("run_template_draft: task %s already cancelled at start", task_id)
        return

    # 1. CHECKING_EXISTING
    await state.set_status(task_id, "CHECKING_EXISTING")
    await events.emit(user_id, task_id, "status_changed")

    if not skip_existing_check:
        existing = await CaseGenerationLogRepository.find_latest_completed(
            user_id=user_id, case_id=case_id, draft_template_id=template_id,
        )
        if existing is not None:
            await state.set_existing_found(task_id, existing_log_id=existing.id)
            await events.emit(user_id, task_id, "existing_found")
            return

    # 2. Insert log row + flip DRAFTING
    record = await state.get(task_id)
    template_name = record.template_name if record else ""
    log = await CaseGenerationLogRepository.create(
        user_id=user_id,
        case_id=case_id,
        draft_template_id=template_id,
        task_id=task_id,
        template_name=template_name,
        status="DRAFTING",
    )
    await state.attach_log_id(task_id, log.id)
    await state.set_status(task_id, "DRAFTING")
    await events.emit(user_id, task_id, "status_changed")

    # 3. Run the studio engine
    try:
        result = await execute_draft_for_case(template_id, case_id, bundle_picks)
    except Exception as exc:
        logger.exception("execute_draft_for_case failed for task %s", task_id)
        await CaseGenerationLogRepository.update_status(log.id, status="FAILED", error=str(exc))
        await state.set_failed(task_id, str(exc))
        await events.emit(user_id, task_id, "failed")
        await _try_drain_user_queue(user_id)
        return

    if isinstance(result, AwaitingInputResponse):
        await CaseGenerationLogRepository.update_status(log.id, status="AWAITING_INPUT")
        await state.set_awaiting_input(
            task_id,
            resolved_values=state.serialize_resolved_values(result.resolved_values),
            pending_inputs=state.serialize_pending_inputs(result.pending_inputs),
        )
        await events.emit(user_id, task_id, "awaiting_input")
        return

    # Worker may have been cancelled mid-LLM; if so, drop the result.
    if await state.is_cancelled(task_id):
        logger.info("run_template_draft: task %s cancelled before persisting result", task_id)
        await CaseGenerationLogRepository.update_status(log.id, status="CANCELLED")
        await _try_drain_user_queue(user_id)
        return

    # COMPLETED — persist to log row + task record
    await CaseGenerationLogRepository.update_status(
        log.id,
        status="COMPLETED",
        r2_object_key=result.r2_object_key,
        children=state.serialize_children(result.children),
    )
    await state.set_completed(task_id, result=result, log_id=log.id)
    await events.emit(user_id, task_id, "completed")
    await _try_drain_user_queue(user_id)


@core_broker.task
async def run_template_draft_resume(
    task_id: str,
    user_id: str,
    user_picks: dict[str, dict],
) -> None:
    """Resume after the FE submits picks from the AWAITING_INPUT modal."""
    if await state.is_cancelled(task_id):
        return

    record = await state.get(task_id)
    if record is None:
        logger.warning("run_template_draft_resume: task %s vanished", task_id)
        return

    firm_id = await _resolve_firm_id(user_id)
    with cost_attribution(
        firm_id=firm_id,
        case_id=record.case_id,
        user_id=user_id,
        session_id=task_id,
        semantic_id=task_id,
        semantic_id_kind="pleading_run",
    ):
        await _run_template_draft_resume_impl(
            task_id=task_id,
            user_id=user_id,
            user_picks=user_picks,
            record=record,
        )


async def _run_template_draft_resume_impl(
    *,
    task_id: str,
    user_id: str,
    user_picks: dict[str, dict],
    record,
) -> None:
    await state.set_status(task_id, "DRAFTING")
    await events.emit(user_id, task_id, "status_changed")

    log_id = record.log_id
    if log_id is not None:
        await CaseGenerationLogRepository.update_status(log_id, status="DRAFTING")

    try:
        result = await resume_draft(
            template_id=record.template_id,
            case_id=record.case_id,
            resolved_values=_resolved_values_from_record(record.resolved_values),
            user_picks=_user_picks_from_payload(user_picks),
            bundle_picks=record.bundle_picks,
        )
    except Exception as exc:
        logger.exception("resume_draft failed for task %s", task_id)
        if log_id is not None:
            await CaseGenerationLogRepository.update_status(log_id, status="FAILED", error=str(exc))
        await state.set_failed(task_id, str(exc))
        await events.emit(user_id, task_id, "failed")
        await _try_drain_user_queue(user_id)
        return

    if isinstance(result, AwaitingInputResponse):
        # Another pause — rare but supported (chained user_input fields).
        if log_id is not None:
            await CaseGenerationLogRepository.update_status(log_id, status="AWAITING_INPUT")
        await state.set_awaiting_input(
            task_id,
            resolved_values=state.serialize_resolved_values(result.resolved_values),
            pending_inputs=state.serialize_pending_inputs(result.pending_inputs),
        )
        await events.emit(user_id, task_id, "awaiting_input")
        return

    if await state.is_cancelled(task_id):
        if log_id is not None:
            await CaseGenerationLogRepository.update_status(log_id, status="CANCELLED")
        await _try_drain_user_queue(user_id)
        return

    if log_id is not None:
        await CaseGenerationLogRepository.update_status(
            log_id,
            status="COMPLETED",
            r2_object_key=result.r2_object_key,
            children=state.serialize_children(result.children),
        )
    await state.set_completed(task_id, result=result, log_id=log_id)
    await events.emit(user_id, task_id, "completed")
    await _try_drain_user_queue(user_id)
