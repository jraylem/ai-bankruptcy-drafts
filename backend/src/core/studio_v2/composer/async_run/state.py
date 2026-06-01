"""Redis-backed CRUD for V2 composer task records.

Mirrors `src/core/components/pleading/state.py` 1:1 for a simpler
state machine (no AWAITING_INPUT, no EXISTING_FOUND, no resume).

Key families per user:
- `core:composer:task:{task_id}` — JSON-serialized `V2ComposerTaskRecord` (TTL 7200s)
- `core:composer:user_tasks:{user_id}` — Set of active task_ids for the user
- `core:composer:queue:{user_id}` — List (FIFO queue) of task_ids waiting for a slot
- `core:composer:task:{task_id}:cancelled` — sentinel "1" string set by /cancel
- `core:composer:upload:{blob_key}` — staged docx bytes for the worker to fetch (TTL 7200s)

Concurrency caps:
- `MAX_CONCURRENT_COMPOSER_TASKS = 10` — beyond this, /start enqueues with status=QUEUED
- `MAX_QUEUED_COMPOSER_TASKS = 50` — hard absolute cap, /start returns 429 above this

Caps are LOWER than pleading's because composer is more expensive
(TemplateAgentV2 is a long-prompt LLM call AND the result lands in
Postgres + R2). Keeps a single firm from monopolizing the worker
during a bulk template-upload session.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from src.tasks.redis_client import make_async_redis

from .schemas import (
    ACTIVE_STATES,
    V2ComposerTaskKind,
    V2ComposerTaskRecord,
    V2ComposerTaskStatus,
)

logger = logging.getLogger(__name__)

# ─── Key prefixes + TTLs ───────────────────────────────────────────────

TASK_KEY_PREFIX = "core:composer:task:"
USER_TASKS_KEY_PREFIX = "core:composer:user_tasks:"
USER_QUEUE_KEY_PREFIX = "core:composer:queue:"
CANCEL_FLAG_SUFFIX = ":cancelled"
UPLOAD_BLOB_KEY_PREFIX = "core:composer:upload:"

TASK_TTL_SECONDS = 7200
UPLOAD_TTL_SECONDS = 7200

# ─── Concurrency caps ──────────────────────────────────────────────────

MAX_CONCURRENT_COMPOSER_TASKS = 10
MAX_QUEUED_COMPOSER_TASKS = 50


def _task_key(task_id: str) -> str:
    return f"{TASK_KEY_PREFIX}{task_id}"


def _user_tasks_key(user_id: str) -> str:
    return f"{USER_TASKS_KEY_PREFIX}{user_id}"


def _queue_key(user_id: str) -> str:
    return f"{USER_QUEUE_KEY_PREFIX}{user_id}"


def _cancel_flag_key(task_id: str) -> str:
    return f"{TASK_KEY_PREFIX}{task_id}{CANCEL_FLAG_SUFFIX}"


def _upload_blob_key(blob_key: str) -> str:
    return f"{UPLOAD_BLOB_KEY_PREFIX}{blob_key}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ─── Upload blob staging ───────────────────────────────────────────────


async def stage_upload_blob(file_content: bytes) -> str:
    """Park raw docx bytes in Redis so the worker can fetch them on
    dispatch. Returns a short blob_key the task record stores; the
    worker calls `fetch_upload_blob(blob_key)` to retrieve the bytes
    and `discard_upload_blob` once consumed.

    Why Redis vs Taskiq payload: Taskiq message size is bounded; a
    multi-MB docx would either fail or be expensive to serialize on
    every retry. Redis BLOB + TTL keeps the worker dispatch lean.

    `decode_responses=False` because the value is binary docx bytes.
    """
    blob_key = uuid.uuid4().hex
    r = make_async_redis(decode_responses=False)
    try:
        await r.setex(_upload_blob_key(blob_key), UPLOAD_TTL_SECONDS, file_content)
    finally:
        await r.aclose()
    return blob_key


async def fetch_upload_blob(blob_key: str) -> bytes | None:
    """Worker-side: retrieve the staged docx bytes for this task.

    Uses `decode_responses=False` because the value is binary docx
    bytes — decode_responses=True would try UTF-8 the response and
    blow up on the docx ZIP header.
    """
    r = make_async_redis(decode_responses=False)
    try:
        return await r.get(_upload_blob_key(blob_key))
    finally:
        await r.aclose()


async def discard_upload_blob(blob_key: str) -> None:
    """Worker-side: delete the staged blob after successful consumption."""
    r = make_async_redis()
    try:
        await r.delete(_upload_blob_key(blob_key))
    finally:
        await r.aclose()


# ─── Internal: persist a record ────────────────────────────────────────


async def _persist(record: V2ComposerTaskRecord) -> V2ComposerTaskRecord:
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
    kind: V2ComposerTaskKind,
    template_name: str = "",
    template_id: str | None = None,
    template_role: str = "single",
    original_filename: str = "",
    ignored_texts: list[str] | None = None,
    merges: list | None = None,
    regeneration_instruction: str | None = None,
    upload_blob_key: str | None = None,
    status: V2ComposerTaskStatus = "PENDING",
) -> V2ComposerTaskRecord:
    """Create a new composer task record. Status defaults to PENDING;
    callers may pass `QUEUED` when the user is over the concurrency cap."""
    now = _now()
    record = V2ComposerTaskRecord(
        task_id=str(uuid.uuid4()),
        user_id=user_id,
        firm_id=firm_id,
        kind=kind,
        template_name=template_name,
        template_id=template_id,
        template_role=template_role,
        original_filename=original_filename,
        ignored_texts=ignored_texts,
        merges=merges,
        regeneration_instruction=regeneration_instruction,
        upload_blob_key=upload_blob_key,
        status=status,
        created_at=now,
        updated_at=now,
    )
    return await _persist(record)


async def get(task_id: str) -> V2ComposerTaskRecord | None:
    r = make_async_redis()
    try:
        raw = await r.get(_task_key(task_id))
        if raw is None:
            return None
        return V2ComposerTaskRecord.model_validate_json(raw)
    finally:
        await r.aclose()


async def set_status(task_id: str, status: V2ComposerTaskStatus) -> V2ComposerTaskRecord | None:
    record = await get(task_id)
    if record is None:
        return None
    record.status = status
    return await _persist(record)


async def set_completed_generate(
    task_id: str, *, result, template_id: str,
) -> V2ComposerTaskRecord | None:
    """Worker-side: persist a generate-template completion."""
    record = await get(task_id)
    if record is None:
        return None
    record.status = "COMPLETED"
    record.generate_result = result
    record.template_id = template_id
    return await _persist(record)


async def set_completed_regenerate(
    task_id: str, *, result,
) -> V2ComposerTaskRecord | None:
    """Worker-side: persist a regenerate-template completion."""
    record = await get(task_id)
    if record is None:
        return None
    record.status = "COMPLETED"
    record.regenerate_result = result
    return await _persist(record)


async def set_failed(task_id: str, error: str) -> V2ComposerTaskRecord | None:
    record = await get(task_id)
    if record is None:
        return None
    record.status = "FAILED"
    record.error = error
    return await _persist(record)


async def set_cancelled(task_id: str) -> V2ComposerTaskRecord | None:
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
        if record.upload_blob_key:
            await r.delete(_upload_blob_key(record.upload_blob_key))
        return True
    finally:
        await r.aclose()


# ─── User-scoped queries ───────────────────────────────────────────────


async def list_for_user(user_id: str) -> list[V2ComposerTaskRecord]:
    """Return every task currently tracked for the user (active + terminal)."""
    r = make_async_redis()
    try:
        task_ids = await r.smembers(_user_tasks_key(user_id))
    finally:
        await r.aclose()

    records: list[V2ComposerTaskRecord] = []
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


async def list_active_for_user(user_id: str) -> list[V2ComposerTaskRecord]:
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
    if active >= MAX_CONCURRENT_COMPOSER_TASKS:
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
