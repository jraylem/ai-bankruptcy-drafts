"""Tests for the v2 pleading Redis state layer.

`state.py` is the source of truth for in-flight task records (the Redis hash),
the per-user active-set (Redis Set), the per-user FIFO queue (Redis List) and
the cancel flag. Wrong serialization or wrong key prefix would silently break
the whole pipeline.

The tests use a small in-memory fake redis (no fakeredis dep, no docker)
matching the surface state.py actually calls — `setex`/`get`/`expire`/
`sadd`/`smembers`/`srem`/`delete`/`rpush`/`lpop`/`lrem`/`llen`/`aclose`.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.core.components.pleading import state
from src.core.components.pleading.schemas import V2TemplateDraftTaskRecord


# ─── Fake redis ────────────────────────────────────────────────────────


class _FakeAsyncRedis:
    """Minimal async-redis stand-in. Holds three flat dicts: scalar strings,
    sets, lists. Mirrors `aredis.Redis` only for the methods state.py uses."""

    def __init__(self) -> None:
        self.strings: dict[str, str] = {}
        self.sets: dict[str, set[str]] = {}
        self.lists: dict[str, list[str]] = {}
        self.ttls: dict[str, int] = {}

    async def setex(self, key: str, ttl: int, value: str) -> None:
        self.strings[key] = value
        self.ttls[key] = ttl

    async def get(self, key: str) -> str | None:
        return self.strings.get(key)

    async def expire(self, key: str, ttl: int) -> None:
        self.ttls[key] = ttl

    async def sadd(self, key: str, *values: str) -> int:
        bucket = self.sets.setdefault(key, set())
        added = 0
        for v in values:
            if v not in bucket:
                bucket.add(v)
                added += 1
        return added

    async def smembers(self, key: str) -> set[str]:
        return set(self.sets.get(key, set()))

    async def srem(self, key: str, *values: str) -> int:
        bucket = self.sets.get(key)
        if not bucket:
            return 0
        removed = 0
        for v in values:
            if v in bucket:
                bucket.discard(v)
                removed += 1
        return removed

    async def delete(self, *keys: str) -> int:
        removed = 0
        for k in keys:
            if k in self.strings:
                self.strings.pop(k, None)
                self.ttls.pop(k, None)
                removed += 1
            if k in self.sets:
                self.sets.pop(k, None)
                removed += 1
            if k in self.lists:
                self.lists.pop(k, None)
                removed += 1
        return removed

    async def rpush(self, key: str, *values: str) -> int:
        bucket = self.lists.setdefault(key, [])
        bucket.extend(values)
        return len(bucket)

    async def lpop(self, key: str) -> str | None:
        bucket = self.lists.get(key)
        if not bucket:
            return None
        return bucket.pop(0)

    async def lrem(self, key: str, count: int, value: str) -> int:
        bucket = self.lists.get(key)
        if not bucket:
            return 0
        # state.py only uses count=0 — remove all matching.
        before = len(bucket)
        self.lists[key] = [v for v in bucket if v != value]
        return before - len(self.lists[key])

    async def llen(self, key: str) -> int:
        return len(self.lists.get(key, []))

    async def aclose(self) -> None:
        return None


@pytest.fixture
def fake_redis(monkeypatch) -> _FakeAsyncRedis:
    """A single shared fake redis for the whole test — every state.py call
    site gets back the same instance so writes round-trip into reads."""
    fake = _FakeAsyncRedis()
    monkeypatch.setattr(state, "make_async_redis", lambda *args, **kwargs: fake)
    return fake


# ─── create / get round-trips ──────────────────────────────────────────


@pytest.mark.unit
async def test_create_persists_and_indexes_the_record(fake_redis):
    rec = await state.create(
        user_id="user-1",
        case_id="26_10700",
        template_id="tpl-A",
        template_name="Motion to Extend",
        bundle_picks={"0": "Yes"},
    )
    assert rec.status == "PENDING"  # default
    assert rec.task_id  # uuid was assigned

    fetched = await state.get(rec.task_id)
    assert fetched is not None
    assert fetched.task_id == rec.task_id
    assert fetched.template_id == "tpl-A"
    # The task is indexed under the user's active-set key.
    assert rec.task_id in fake_redis.sets[state._user_tasks_key("user-1")]


@pytest.mark.unit
async def test_get_returns_none_for_unknown_task(fake_redis):
    assert await state.get("missing-task-id") is None


@pytest.mark.unit
async def test_create_accepts_queued_status_for_overflow(fake_redis):
    rec = await state.create(
        user_id="user-1",
        case_id="case",
        template_id="tpl",
        status="QUEUED",
    )
    assert rec.status == "QUEUED"


# ─── status transitions ───────────────────────────────────────────────


@pytest.mark.unit
async def test_set_status_flips_field_and_persists(fake_redis):
    rec = await state.create(user_id="u", case_id="c", template_id="tpl")
    after = await state.set_status(rec.task_id, "DRAFTING")
    assert after is not None
    assert after.status == "DRAFTING"
    refetched = await state.get(rec.task_id)
    assert refetched is not None and refetched.status == "DRAFTING"


@pytest.mark.unit
async def test_set_status_on_missing_returns_none(fake_redis):
    assert await state.set_status("nope", "DRAFTING") is None


@pytest.mark.unit
async def test_attach_log_id_stamps_record(fake_redis):
    rec = await state.create(user_id="u", case_id="c", template_id="tpl")
    after = await state.attach_log_id(rec.task_id, "log-99")
    assert after is not None and after.log_id == "log-99"


@pytest.mark.unit
async def test_set_existing_found_writes_existing_log_id(fake_redis):
    rec = await state.create(user_id="u", case_id="c", template_id="tpl")
    after = await state.set_existing_found(rec.task_id, existing_log_id="log-x")
    assert after is not None
    assert after.status == "EXISTING_FOUND"
    assert after.existing_log_id == "log-x"


@pytest.mark.unit
async def test_set_awaiting_input_persists_pause_payload(fake_redis):
    rec = await state.create(user_id="u", case_id="c", template_id="tpl")
    after = await state.set_awaiting_input(
        rec.task_id,
        resolved_values=[{"property_name": "x", "value": "v", "reasoning": "r", "confidence": "high"}],
        pending_inputs={"x": {"kind": "dropdown", "label": "Pick", "options": ["a", "b"]}},
    )
    assert after is not None
    assert after.status == "AWAITING_INPUT"
    assert after.pending_inputs is not None and "x" in after.pending_inputs
    assert after.resolved_values and after.resolved_values[0]["value"] == "v"


@pytest.mark.unit
async def test_set_completed_stores_log_id_and_status(fake_redis):
    rec = await state.create(user_id="u", case_id="c", template_id="tpl")
    after = await state.set_completed(rec.task_id, result=None, log_id="log-c")
    assert after is not None
    assert after.status == "COMPLETED"
    assert after.log_id == "log-c"


@pytest.mark.unit
async def test_set_failed_stores_error(fake_redis):
    rec = await state.create(user_id="u", case_id="c", template_id="tpl")
    after = await state.set_failed(rec.task_id, "boom")
    assert after is not None
    assert after.status == "FAILED"
    assert after.error == "boom"


# ─── cancellation ─────────────────────────────────────────────────────


@pytest.mark.unit
async def test_set_cancelled_flips_status_and_sets_flag(fake_redis):
    rec = await state.create(user_id="u", case_id="c", template_id="tpl")
    assert (await state.is_cancelled(rec.task_id)) is False
    after = await state.set_cancelled(rec.task_id)
    assert after is not None and after.status == "CANCELLED"
    assert (await state.is_cancelled(rec.task_id)) is True


@pytest.mark.unit
async def test_delete_drops_record_index_and_flags(fake_redis):
    rec = await state.create(user_id="u", case_id="c", template_id="tpl")
    await state.set_cancelled(rec.task_id)
    deleted = await state.delete(rec.task_id)
    assert deleted is True
    # The record is gone, the user-set entry is gone, the cancel flag is gone.
    assert await state.get(rec.task_id) is None
    assert rec.task_id not in fake_redis.sets.get(state._user_tasks_key("u"), set())
    assert state._cancel_flag_key(rec.task_id) not in fake_redis.strings


@pytest.mark.unit
async def test_delete_returns_false_when_record_missing(fake_redis):
    assert (await state.delete("not-a-task")) is False


# ─── user-scoped queries ──────────────────────────────────────────────


@pytest.mark.unit
async def test_list_for_user_returns_all_records_sorted_recent_first(fake_redis):
    older = await state.create(user_id="u", case_id="c1", template_id="tpl")
    newer = await state.create(user_id="u", case_id="c2", template_id="tpl")
    rows = await state.list_for_user("u")
    assert [r.task_id for r in rows] == [newer.task_id, older.task_id]


@pytest.mark.unit
async def test_list_for_user_evicts_stale_index_entries(fake_redis):
    rec = await state.create(user_id="u", case_id="c", template_id="tpl")
    # Simulate TTL eviction: the per-task key is gone but the user-set still points at it.
    del fake_redis.strings[state._task_key(rec.task_id)]
    fake_redis.ttls.pop(state._task_key(rec.task_id), None)
    rows = await state.list_for_user("u")
    assert rows == []
    # The stale entry was removed from the set.
    assert rec.task_id not in fake_redis.sets[state._user_tasks_key("u")]


@pytest.mark.unit
async def test_list_active_for_user_filters_out_terminal_states(fake_redis):
    active = await state.create(user_id="u", case_id="c", template_id="tpl")
    completed = await state.create(user_id="u", case_id="c", template_id="tpl-2")
    await state.set_completed(completed.task_id, result=None)
    active_rows = await state.list_active_for_user("u")
    ids = {r.task_id for r in active_rows}
    assert active.task_id in ids
    assert completed.task_id not in ids


@pytest.mark.unit
async def test_count_active_for_user_matches_list_size(fake_redis):
    await state.create(user_id="u", case_id="c", template_id="tpl-A")
    await state.create(user_id="u", case_id="c", template_id="tpl-B")
    assert (await state.count_active_for_user("u")) == 2


@pytest.mark.unit
async def test_find_active_duplicate_matches_user_case_template_triple(fake_redis):
    a = await state.create(user_id="u", case_id="case-1", template_id="tpl-X")
    # A different template on the same case is not a duplicate.
    await state.create(user_id="u", case_id="case-1", template_id="tpl-Y")
    # A terminal version of the same triple is also not a duplicate.
    done = await state.create(user_id="u", case_id="case-1", template_id="tpl-Z")
    await state.set_completed(done.task_id, result=None)

    dup = await state.find_active_duplicate(user_id="u", case_id="case-1", template_id="tpl-X")
    assert dup is not None and dup.task_id == a.task_id

    miss = await state.find_active_duplicate(user_id="u", case_id="case-1", template_id="tpl-Z")
    assert miss is None  # terminal doesn't count


# ─── queue (per-user FIFO overflow) ──────────────────────────────────


@pytest.mark.unit
async def test_enqueue_and_queue_size(fake_redis):
    size = await state.enqueue("task-1", "u")
    assert size == 1
    size = await state.enqueue("task-2", "u")
    assert size == 2
    assert (await state.queue_size("u")) == 2


@pytest.mark.unit
async def test_drain_queue_returns_none_when_at_capacity(fake_redis, monkeypatch):
    # Lock the cap to 1 so just one record saturates active.
    monkeypatch.setattr(state, "MAX_CONCURRENT_TEMPLATE_DRAFTS", 1)
    await state.create(user_id="u", case_id="c", template_id="tpl")
    await state.enqueue("queued-1", "u")
    drained = await state.drain_queue("u")
    assert drained is None  # active count >= cap, no pop


@pytest.mark.unit
async def test_drain_queue_pops_fifo_when_capacity_available(fake_redis, monkeypatch):
    monkeypatch.setattr(state, "MAX_CONCURRENT_TEMPLATE_DRAFTS", 5)
    await state.enqueue("queued-1", "u")
    await state.enqueue("queued-2", "u")
    first = await state.drain_queue("u")
    assert first == "queued-1"
    second = await state.drain_queue("u")
    assert second == "queued-2"
    assert (await state.drain_queue("u")) is None  # empty


@pytest.mark.unit
async def test_remove_from_queue_drops_specific_entry(fake_redis):
    await state.enqueue("a", "u")
    await state.enqueue("b", "u")
    await state.enqueue("c", "u")
    removed = await state.remove_from_queue("b", "u")
    assert removed == 1
    assert fake_redis.lists[state._queue_key("u")] == ["a", "c"]


# ─── serialization helpers ────────────────────────────────────────────


class _Dumpable:
    """Stand-in for any Pydantic model with `.model_dump(mode="json")`."""

    def __init__(self, payload: dict[str, Any]):
        self._payload = payload

    def model_dump(self, mode: str | None = None) -> dict[str, Any]:
        return dict(self._payload)


@pytest.mark.unit
def test_serialize_pending_inputs_dumps_pydantic_envelope():
    pending = {
        "x": _Dumpable({"kind": "dropdown", "options": ["a", "b"]}),
        "y": {"kind": "user_input_plain_text", "label": "Free text"},
    }
    out = state.serialize_pending_inputs(pending)
    assert out["x"]["kind"] == "dropdown"
    assert out["y"]["label"] == "Free text"


@pytest.mark.unit
def test_serialize_pending_inputs_handles_none():
    assert state.serialize_pending_inputs(None) == {}


@pytest.mark.unit
def test_serialize_resolved_values_dumps_each_entry():
    raw = [_Dumpable({"property_name": "x", "value": "V", "reasoning": "r", "confidence": "high"})]
    out = state.serialize_resolved_values(raw)
    assert out == [{"property_name": "x", "value": "V", "reasoning": "r", "confidence": "high"}]


@pytest.mark.unit
def test_serialize_resolved_values_none_returns_empty():
    assert state.serialize_resolved_values(None) == []


class _ChildLike:
    """Matches the surface state.serialize_children iterates over — fields read by attribute."""

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


@pytest.mark.unit
def test_serialize_children_packs_bundle_child_logs():
    out = state.serialize_children([
        _ChildLike(
            template_id="tpl-child",
            template_name="Cover Sheet",
            companion_label="Always",
            r2_object_key="cases/c/draft/child.docx",
        ),
    ])
    assert out == [
        {
            "template_id": "tpl-child",
            "template_name": "Cover Sheet",
            "companion_label": "Always",
            "r2_object_key": "cases/c/draft/child.docx",
        }
    ]


@pytest.mark.unit
def test_serialize_children_falsy_returns_empty():
    assert state.serialize_children(None) == []
    assert state.serialize_children([]) == []
