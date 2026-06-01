"""Redis-backed CRUD for V2 template-draft task records.

Three key families per user:
- `core:pleading:task:{task_id}` — JSON-serialized V2TemplateDraftTaskRecord (TTL 7200s)
- `core:pleading:user_tasks:{user_id}` — Set of active task_ids for the user
- `core:pleading:queue:{user_id}` — List (FIFO queue) of task_ids waiting for a slot
- `core:pleading:task:{task_id}:cancelled` — sentinel "1" string set by /cancel

Concurrency caps:
- `MAX_CONCURRENT_TEMPLATE_DRAFTS = 20` — beyond this, /start enqueues with status=QUEUED
- `MAX_QUEUED_TEMPLATE_DRAFTS = 100` — hard absolute cap, /start returns 429 above this
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from src.tasks.redis_client import make_async_redis

from .schemas import (
    ACTIVE_STATES,
    BundleChildLog,
    V2TaskStatus,
    V2TemplateDraftTaskRecord,
)

logger = logging.getLogger(__name__)

# ─── Key prefixes + TTLs ───────────────────────────────────────────────

TASK_KEY_PREFIX = "core:pleading:task:"
USER_TASKS_KEY_PREFIX = "core:pleading:user_tasks:"
USER_QUEUE_KEY_PREFIX = "core:pleading:queue:"
CANCEL_FLAG_SUFFIX = ":cancelled"

TASK_TTL_SECONDS = 7200

# ─── Concurrency caps ──────────────────────────────────────────────────

MAX_CONCURRENT_TEMPLATE_DRAFTS = 20
MAX_QUEUED_TEMPLATE_DRAFTS = 100


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


async def _persist(record: V2TemplateDraftTaskRecord) -> V2TemplateDraftTaskRecord:
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
    case_id: str,
    template_id: str,
    template_name: str = "",
    bundle_picks: dict[str, str] | None = None,
    status: V2TaskStatus = "PENDING",
) -> V2TemplateDraftTaskRecord:
    """Create a new task record (status defaults to PENDING)."""
    now = _now()
    record = V2TemplateDraftTaskRecord(
        task_id=str(uuid.uuid4()),
        user_id=user_id,
        case_id=case_id,
        template_id=template_id,
        template_name=template_name,
        status=status,
        bundle_picks=bundle_picks,
        created_at=now,
        updated_at=now,
    )
    return await _persist(record)


async def get(task_id: str) -> V2TemplateDraftTaskRecord | None:
    """Fetch a task record by id."""
    r = make_async_redis()
    try:
        raw = await r.get(_task_key(task_id))
        if raw is None:
            return None
        return V2TemplateDraftTaskRecord.model_validate_json(raw)
    finally:
        await r.aclose()


async def set_status(task_id: str, status: V2TaskStatus) -> V2TemplateDraftTaskRecord | None:
    """Flip the status field, persist, return the refreshed record."""
    record = await get(task_id)
    if record is None:
        return None
    record.status = status
    return await _persist(record)


async def attach_log_id(task_id: str, log_id: str) -> V2TemplateDraftTaskRecord | None:
    """Stamp the case_generation_logs row id onto the task (post-CHECKING_EXISTING)."""
    record = await get(task_id)
    if record is None:
        return None
    record.log_id = log_id
    return await _persist(record)


async def set_existing_found(task_id: str, *, existing_log_id: str) -> V2TemplateDraftTaskRecord | None:
    """Surface a prior COMPLETED log to the user — drives the EXISTING_FOUND modal."""
    record = await get(task_id)
    if record is None:
        return None
    record.status = "EXISTING_FOUND"
    record.existing_log_id = existing_log_id
    return await _persist(record)


async def set_awaiting_input(
    task_id: str,
    *,
    resolved_values: list,
    pending_inputs: dict,
) -> V2TemplateDraftTaskRecord | None:
    """Persist the AwaitingInputResponse payload + flip to AWAITING_INPUT."""
    record = await get(task_id)
    if record is None:
        return None
    record.status = "AWAITING_INPUT"
    record.resolved_values = resolved_values
    record.pending_inputs = pending_inputs
    return await _persist(record)


async def set_completed(
    task_id: str,
    *,
    result,
    log_id: str | None = None,
) -> V2TemplateDraftTaskRecord | None:
    """Persist the DraftResponse + flip to COMPLETED."""
    record = await get(task_id)
    if record is None:
        return None
    record.status = "COMPLETED"
    record.result = result
    if log_id is not None:
        record.log_id = log_id
    return await _persist(record)


async def set_failed(task_id: str, error: str) -> V2TemplateDraftTaskRecord | None:
    """Persist the error string + flip to FAILED."""
    record = await get(task_id)
    if record is None:
        return None
    record.status = "FAILED"
    record.error = error
    return await _persist(record)


async def set_cancelled(task_id: str) -> V2TemplateDraftTaskRecord | None:
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
        # Best-effort: drop from the queue if it's parked there
        await r.lrem(_queue_key(record.user_id), 0, task_id)
        return True
    finally:
        await r.aclose()


# ─── User-scoped queries ───────────────────────────────────────────────


async def list_for_user(user_id: str) -> list[V2TemplateDraftTaskRecord]:
    """Return every task currently tracked for the user (active + recent terminal)."""
    r = make_async_redis()
    try:
        task_ids = await r.smembers(_user_tasks_key(user_id))
    finally:
        await r.aclose()

    records: list[V2TemplateDraftTaskRecord] = []
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


async def list_active_for_user(user_id: str) -> list[V2TemplateDraftTaskRecord]:
    """Return only the non-terminal tasks (used for snapshot + dedup checks)."""
    all_records = await list_for_user(user_id)
    return [r for r in all_records if r.status in ACTIVE_STATES]


async def count_active_for_user(user_id: str) -> int:
    """Fast count — used by the concurrency cap check."""
    return len(await list_active_for_user(user_id))


async def find_active_duplicate(
    *,
    user_id: str,
    case_id: str,
    template_id: str,
) -> V2TemplateDraftTaskRecord | None:
    """Return any non-terminal task for (user, case, template) — drives dedup 429."""
    for rec in await list_active_for_user(user_id):
        if rec.case_id == case_id and rec.template_id == template_id:
            return rec
    return None


# ─── Per-user FIFO queue (for the 20+ overflow) ────────────────────────


async def enqueue(task_id: str, user_id: str) -> int:
    """Park a task at the tail of the user's queue. Returns the queue size after push."""
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
    """If the user is under the cap AND has queued tasks, pop the oldest and return its task_id.

    Caller is responsible for flipping the record's status QUEUED→PENDING and
    kicking the taskiq job.
    """
    active = await count_active_for_user(user_id)
    if active >= MAX_CONCURRENT_TEMPLATE_DRAFTS:
        return None
    r = make_async_redis()
    try:
        return await r.lpop(_queue_key(user_id))
    finally:
        await r.aclose()


async def remove_from_queue(task_id: str, user_id: str) -> int:
    """Drop a specific task_id from the queue (cancellation of a QUEUED task)."""
    r = make_async_redis()
    try:
        return await r.lrem(_queue_key(user_id), 0, task_id)
    finally:
        await r.aclose()


# ─── JSON-safe helpers for AwaitingInputResponse payloads ──────────────


def serialize_pending_inputs(pending_inputs) -> dict:
    """Coerce the pipeline's pending_inputs (PendingInputEnvelope models) into JSON-safe dicts."""
    if pending_inputs is None:
        return {}
    if isinstance(pending_inputs, dict):
        return {
            k: (v.model_dump(mode="json") if hasattr(v, "model_dump") else v)
            for k, v in pending_inputs.items()
        }
    return json.loads(
        json.dumps(pending_inputs, default=lambda o: o.model_dump(mode="json") if hasattr(o, "model_dump") else str(o))
    )


def serialize_resolved_values(resolved_values) -> list:
    """Coerce ResolvedTemplateValue list into JSON-safe dicts."""
    if resolved_values is None:
        return []
    return [rv.model_dump(mode="json") if hasattr(rv, "model_dump") else rv for rv in resolved_values]


def serialize_children(children) -> list[dict]:
    """Coerce DraftChildResult list → list of BundleChildLog dicts for JSONB persistence."""
    out: list[dict] = []
    for c in children or []:
        out.append(
            BundleChildLog(
                template_id=c.template_id,
                template_name=c.template_name,
                companion_label=c.companion_label,
                r2_object_key=c.r2_object_key,
            ).model_dump()
        )
    return out
