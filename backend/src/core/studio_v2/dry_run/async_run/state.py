"""Redis-backed CRUD for V2 dry-run task records.

Mirrors `studio_v2/composer/async_run/state.py` 1:1 with a richer
state machine (adds AWAITING_INPUT + RESUMING) and lower concurrency
caps. No upload-blob staging — dry-run inputs are pure JSON
(template_spec, user_picks) so they ride the task record itself.

Key families per user:
- `core:dry_run:task:{task_id}` — JSON-serialized `V2DryRunTaskRecord` (TTL 7200s)
- `core:dry_run:user_tasks:{user_id}` — Set of task_ids tracked for the user
- `core:dry_run:queue:{user_id}` — List (FIFO queue) of task_ids waiting for a slot
- `core:dry_run:task:{task_id}:cancelled` — sentinel "1" string set by /cancel

Concurrency caps:
- `MAX_CONCURRENT_DRY_RUN_TASKS = 5` — beyond this, /start enqueues with status=QUEUED
- `MAX_QUEUED_DRY_RUN_TASKS = 20` — hard absolute cap, /start returns 429 above this

Caps are LOWER than composer's (10 / 50) because dry-runs are
diagnostic tools — beyond ~5 in flight a paralegal can't track what's
going on and the cost of LLM work being thrown away on a cancellation
is higher than letting it sit in the queue.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from src.tasks.redis_client import make_async_redis

from .schemas import (
    ACTIVE_STATES,
    V2DryRunStatus,
    V2DryRunTaskRecord,
)

logger = logging.getLogger(__name__)

# ─── Key prefixes + TTLs ───────────────────────────────────────────────

TASK_KEY_PREFIX = "core:dry_run:task:"
USER_TASKS_KEY_PREFIX = "core:dry_run:user_tasks:"
USER_QUEUE_KEY_PREFIX = "core:dry_run:queue:"
CANCEL_FLAG_SUFFIX = ":cancelled"

TASK_TTL_SECONDS = 7200

# ─── Concurrency caps ──────────────────────────────────────────────────

MAX_CONCURRENT_DRY_RUN_TASKS = 5
MAX_QUEUED_DRY_RUN_TASKS = 20


def _task_key(task_id: str) -> str:
    return f"{TASK_KEY_PREFIX}{task_id}"


def _user_tasks_key(user_id: str) -> str:
    return f"{USER_TASKS_KEY_PREFIX}{user_id}"


def _queue_key(user_id: str) -> str:
    return f"{USER_QUEUE_KEY_PREFIX}{user_id}"


def _cancel_flag_key(task_id: str) -> str:
    return f"{TASK_KEY_PREFIX}{task_id}{CANCEL_FLAG_SUFFIX}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ─── Internal: persist a record ────────────────────────────────────────


async def _persist(record: V2DryRunTaskRecord) -> V2DryRunTaskRecord:
    record.updated_at = _now()
    r = make_async_redis()
    try:
        await r.setex(
            _task_key(record.task_id),
            TASK_TTL_SECONDS,
            record.model_dump_json(),
        )
        await r.sadd(_user_tasks_key(record.user_id), record.task_id)
        await r.expire(_user_tasks_key(record.user_id), TASK_TTL_SECONDS)
        return record
    finally:
        await r.aclose()


# ─── Public CRUD ───────────────────────────────────────────────────────


async def create(
    *,
    user_id: str,
    firm_id: str | None,
    template_id: str,
    case_id: str,
    template_spec: Any,
    template_name: str = "",
    case_label: str = "",
    bundle_picks: dict[str, str] | None = None,
    bundle_role: str | None = None,
    bundle_companions: list[dict[str, Any]] | None = None,
    status: V2DryRunStatus = "PENDING",
) -> V2DryRunTaskRecord:
    """Create a new dry-run task record. Status defaults to PENDING;
    callers may pass `QUEUED` when the user is over the concurrency cap.
    """
    now = _now()
    record = V2DryRunTaskRecord(
        task_id=str(uuid.uuid4()),
        user_id=user_id,
        firm_id=firm_id,
        template_id=template_id,
        case_id=case_id,
        template_name=template_name,
        case_label=case_label,
        template_spec=template_spec,
        bundle_picks=bundle_picks,
        bundle_role=bundle_role,
        bundle_companions=bundle_companions,
        status=status,
        created_at=now,
        updated_at=now,
    )
    return await _persist(record)


async def get(task_id: str) -> V2DryRunTaskRecord | None:
    r = make_async_redis()
    try:
        raw = await r.get(_task_key(task_id))
        if raw is None:
            return None
        return V2DryRunTaskRecord.model_validate_json(raw)
    finally:
        await r.aclose()


async def set_status(task_id: str, status: V2DryRunStatus) -> V2DryRunTaskRecord | None:
    record = await get(task_id)
    if record is None:
        return None
    record.status = status
    return await _persist(record)


async def set_awaiting_input(
    task_id: str,
    *,
    resolved_values: list,
    pending_inputs: dict,
) -> V2DryRunTaskRecord | None:
    """Worker-side: pipeline reached a USER_INPUT pause point. Persist
    the partial state so the FE can render pending_inputs and a
    subsequent /submit-input resume picks up cleanly.
    """
    record = await get(task_id)
    if record is None:
        return None
    record.status = "AWAITING_INPUT"
    record.resolved_values = resolved_values
    record.pending_inputs = pending_inputs
    return await _persist(record)


async def set_user_picks(
    task_id: str,
    *,
    user_picks: dict,
    bundle_picks: dict[str, str] | None = None,
) -> V2DryRunTaskRecord | None:
    """HTTP-side: /submit-input stashed the paralegal's picks. Worker
    will read them off the record when it picks up the resume job.
    """
    record = await get(task_id)
    if record is None:
        return None
    record.user_picks = user_picks
    if bundle_picks is not None:
        record.bundle_picks = bundle_picks
    record.status = "RESUMING"
    return await _persist(record)


async def set_completed(
    task_id: str, *, result,
) -> V2DryRunTaskRecord | None:
    """Worker-side: persist a dry-run completion result."""
    record = await get(task_id)
    if record is None:
        return None
    record.status = "COMPLETED"
    record.result = result
    # Clear pending_inputs / user_picks once the run is done — they're
    # stale at this point and just bloat the response.
    record.pending_inputs = None
    return await _persist(record)


async def set_failed(task_id: str, error: str) -> V2DryRunTaskRecord | None:
    record = await get(task_id)
    if record is None:
        return None
    record.status = "FAILED"
    record.error = error
    return await _persist(record)


async def set_cancelled(task_id: str) -> V2DryRunTaskRecord | None:
    """Mark a task CANCELLED + set the worker-visible cancel flag."""
    record = await get(task_id)
    if record is None:
        return None
    record.status = "CANCELLED"
    r = make_async_redis()
    try:
        await r.setex(_cancel_flag_key(task_id), TASK_TTL_SECONDS, "1")
    finally:
        await r.aclose()
    return await _persist(record)


async def is_cancelled(task_id: str) -> bool:
    """Worker-side check — true if /cancel was hit."""
    r = make_async_redis()
    try:
        return await r.get(_cancel_flag_key(task_id)) == "1"
    finally:
        await r.aclose()


async def delete(task_id: str) -> bool:
    """Hard-remove a task record + drop from the user's active set."""
    record = await get(task_id)
    if record is None:
        return False
    r = make_async_redis()
    try:
        await r.delete(_task_key(task_id))
        await r.srem(_user_tasks_key(record.user_id), task_id)
        await r.delete(_cancel_flag_key(task_id))
        await r.lrem(_queue_key(record.user_id), 0, task_id)
        return True
    finally:
        await r.aclose()


# ─── User-scoped queries ───────────────────────────────────────────────


async def list_for_user(user_id: str) -> list[V2DryRunTaskRecord]:
    """Return every task currently tracked for the user (active + terminal)."""
    r = make_async_redis()
    try:
        task_ids = await r.smembers(_user_tasks_key(user_id))
    finally:
        await r.aclose()

    records: list[V2DryRunTaskRecord] = []
    stale: list[str] = []
    for tid in task_ids:
        rec = await get(tid)
        if rec is None:
            stale.append(tid)
            continue
        records.append(rec)

    if stale:
        r = make_async_redis()
        try:
            await r.srem(_user_tasks_key(user_id), *stale)
        finally:
            await r.aclose()

    records.sort(key=lambda x: x.created_at, reverse=True)
    return records


async def list_active_for_user(user_id: str) -> list[V2DryRunTaskRecord]:
    all_records = await list_for_user(user_id)
    return [r for r in all_records if r.status in ACTIVE_STATES]


async def count_active_for_user(user_id: str) -> int:
    return len(await list_active_for_user(user_id))


# ─── Per-user FIFO queue ───────────────────────────────────────────────


async def enqueue(task_id: str, user_id: str) -> int:
    r = make_async_redis()
    try:
        size = await r.rpush(_queue_key(user_id), task_id)
        await r.expire(_queue_key(user_id), TASK_TTL_SECONDS)
        return size
    finally:
        await r.aclose()


async def queue_size(user_id: str) -> int:
    r = make_async_redis()
    try:
        return await r.llen(_queue_key(user_id))
    finally:
        await r.aclose()


async def drain_queue(user_id: str) -> str | None:
    """If the user is under the cap AND has queued tasks, pop the oldest.

    Caller is responsible for flipping the record's status QUEUED→PENDING
    and kicking the taskiq job.
    """
    active = await count_active_for_user(user_id)
    if active >= MAX_CONCURRENT_DRY_RUN_TASKS:
        return None
    r = make_async_redis()
    try:
        return await r.lpop(_queue_key(user_id))
    finally:
        await r.aclose()


async def remove_from_queue(task_id: str, user_id: str) -> int:
    r = make_async_redis()
    try:
        return await r.lrem(_queue_key(user_id), 0, task_id)
    finally:
        await r.aclose()
