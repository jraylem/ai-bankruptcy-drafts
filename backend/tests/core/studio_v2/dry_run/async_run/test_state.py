"""Tests for the v2 dry-run-async Redis state layer.

Mirrors `tests/core/studio_v2/composer/async_run/test_state.py` but
exercises the pause/resume CRUD paths that composer-async doesn't
have (set_awaiting_input + set_user_picks + set_completed) and skips
the upload-blob staging (dry-run has no binary IO).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from src.core.studio_v2.dry_run.async_run import state
from src.core.studio_v2.types.fields import TemplateSpecV2


# ─── Fake redis ────────────────────────────────────────────────────────


class _FakeAsyncRedis:
    """Minimal async-redis stand-in. Dry-run state is JSON-only so we
    don't need the binary-IO mode composer-async tests do."""

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
        before = len(bucket)
        self.lists[key] = [v for v in bucket if v != value]
        return before - len(self.lists[key])

    async def llen(self, key: str) -> int:
        return len(self.lists.get(key, []))

    async def aclose(self) -> None:
        return None


@pytest.fixture
def fake_redis(monkeypatch) -> _FakeAsyncRedis:
    backing = _FakeAsyncRedis()

    def _factory(*args, **kwargs):
        return backing

    monkeypatch.setattr(state, "make_async_redis", _factory)
    return backing


# ─── Fixtures ──────────────────────────────────────────────────────────


def _empty_spec() -> TemplateSpecV2:
    """Minimal valid spec for record-construction tests."""
    return TemplateSpecV2(template_id=uuid.uuid4(), fields=[])


# ─── create / get round-trips ──────────────────────────────────────────


@pytest.mark.unit
async def test_create_persists_record_and_indexes(fake_redis):
    spec = _empty_spec()
    rec = await state.create(
        user_id="user-1",
        firm_id="firm-A",
        template_id=str(spec.template_id),
        case_id="case-42",
        template_spec=spec,
        template_name="341(a) Meeting Notice",
        case_label="26-10700",
    )
    assert rec.status == "PENDING"
    assert rec.template_id == str(spec.template_id)
    assert rec.case_id == "case-42"
    assert rec.template_name == "341(a) Meeting Notice"

    fetched = await state.get(rec.task_id)
    assert fetched is not None and fetched.task_id == rec.task_id
    assert fetched.firm_id == "firm-A"
    assert rec.task_id in fake_redis.sets[state._user_tasks_key("user-1")]


@pytest.mark.unit
async def test_create_queued_status_when_over_cap(fake_redis):
    """Router enforces caps then passes status='QUEUED' through create."""
    rec = await state.create(
        user_id="u",
        firm_id=None,
        template_id="tpl",
        case_id="c",
        template_spec=_empty_spec(),
        status="QUEUED",
    )
    assert rec.status == "QUEUED"


@pytest.mark.unit
async def test_get_returns_none_for_missing_task(fake_redis):
    assert await state.get("nope") is None


# ─── status transitions ───────────────────────────────────────────────


@pytest.mark.unit
async def test_set_status_flips_field(fake_redis):
    rec = await state.create(
        user_id="u", firm_id=None, template_id="t", case_id="c",
        template_spec=_empty_spec(),
    )
    after = await state.set_status(rec.task_id, "RUNNING")
    assert after is not None and after.status == "RUNNING"


@pytest.mark.unit
async def test_set_awaiting_input_persists_pause_context(fake_redis):
    """Pause point: worker stashes resolved_values + pending_inputs so
    the FE can render the pick modal and a later /submit-input resume
    has everything it needs."""
    rec = await state.create(
        user_id="u", firm_id=None, template_id="t", case_id="c",
        template_spec=_empty_spec(),
    )
    after = await state.set_awaiting_input(
        rec.task_id,
        resolved_values=[],
        pending_inputs={"creditor": {"kind": "dropdown", "label": "Pick a creditor", "options": ["A", "B"], "raw_contexts": ["", ""]}},
    )
    assert after is not None
    assert after.status == "AWAITING_INPUT"
    assert after.resolved_values == []
    assert "creditor" in (after.pending_inputs or {})


@pytest.mark.unit
async def test_set_user_picks_flips_to_resuming_and_stores_picks(fake_redis):
    rec = await state.create(
        user_id="u", firm_id=None, template_id="t", case_id="c",
        template_spec=_empty_spec(),
    )
    await state.set_status(rec.task_id, "AWAITING_INPUT")
    after = await state.set_user_picks(
        rec.task_id,
        user_picks={"creditor": {"value": "Acme Bank"}},
        bundle_picks={"branch-1": "option-a"},
    )
    assert after is not None
    assert after.status == "RESUMING"
    assert after.user_picks == {"creditor": {"value": "Acme Bank"}}
    assert after.bundle_picks == {"branch-1": "option-a"}


@pytest.mark.unit
async def test_set_user_picks_keeps_existing_bundle_picks_when_omitted(fake_redis):
    """If /submit-input doesn't re-supply bundle_picks, the original
    pre-flight picks from /start stay in place."""
    rec = await state.create(
        user_id="u", firm_id=None, template_id="t", case_id="c",
        template_spec=_empty_spec(),
        bundle_picks={"branch-1": "original"},
    )
    await state.set_status(rec.task_id, "AWAITING_INPUT")
    after = await state.set_user_picks(
        rec.task_id, user_picks={}, bundle_picks=None,
    )
    assert after is not None
    assert after.bundle_picks == {"branch-1": "original"}


@pytest.mark.unit
async def test_set_completed_clears_pending_inputs(fake_redis):
    """Once the run is done, pending_inputs is stale — clear it so the
    SSE payload doesn't carry MBs of dead options."""
    from src.core.studio_v2.types.orchestration import DryRunResponseV2
    rec = await state.create(
        user_id="u", firm_id=None, template_id="t", case_id="c",
        template_spec=_empty_spec(),
    )
    await state.set_awaiting_input(
        rec.task_id, resolved_values=[], pending_inputs={"x": {"kind": "dropdown", "label": "X", "options": [], "raw_contexts": []}},
    )
    result = DryRunResponseV2(
        run_id=str(uuid.uuid4()),
        template_id="t",
        case_id="c",
        resolved_values=[],
        generated_doc_url="https://r2/x.docx",
        r2_object_key="dry_run/x.docx",
        unresolved=[],
        warnings=[],
        children=[],
    )
    after = await state.set_completed(rec.task_id, result=result)
    assert after is not None
    assert after.status == "COMPLETED"
    assert after.result is not None
    assert after.pending_inputs is None  # cleared


@pytest.mark.unit
async def test_set_failed_persists_error(fake_redis):
    rec = await state.create(
        user_id="u", firm_id=None, template_id="t", case_id="c",
        template_spec=_empty_spec(),
    )
    after = await state.set_failed(rec.task_id, "LLM timeout")
    assert after is not None
    assert after.status == "FAILED"
    assert after.error == "LLM timeout"


@pytest.mark.unit
async def test_set_cancelled_sets_flag_and_status(fake_redis):
    rec = await state.create(
        user_id="u", firm_id=None, template_id="t", case_id="c",
        template_spec=_empty_spec(),
    )
    after = await state.set_cancelled(rec.task_id)
    assert after is not None
    assert after.status == "CANCELLED"
    assert await state.is_cancelled(rec.task_id) is True


@pytest.mark.unit
async def test_is_cancelled_false_when_not_set(fake_redis):
    rec = await state.create(
        user_id="u", firm_id=None, template_id="t", case_id="c",
        template_spec=_empty_spec(),
    )
    assert await state.is_cancelled(rec.task_id) is False


# ─── queries + queue ──────────────────────────────────────────────────


@pytest.mark.unit
async def test_list_for_user_returns_newest_first(fake_redis):
    import asyncio
    rec1 = await state.create(
        user_id="u", firm_id=None, template_id="t", case_id="c",
        template_spec=_empty_spec(),
    )
    await asyncio.sleep(0.01)
    rec2 = await state.create(
        user_id="u", firm_id=None, template_id="t", case_id="c",
        template_spec=_empty_spec(),
    )
    out = await state.list_for_user("u")
    assert [r.task_id for r in out] == [rec2.task_id, rec1.task_id]


@pytest.mark.unit
async def test_list_active_for_user_filters_terminal(fake_redis):
    rec1 = await state.create(
        user_id="u", firm_id=None, template_id="t", case_id="c",
        template_spec=_empty_spec(),
    )
    rec2 = await state.create(
        user_id="u", firm_id=None, template_id="t", case_id="c",
        template_spec=_empty_spec(),
    )
    await state.set_status(rec2.task_id, "COMPLETED")
    active = await state.list_active_for_user("u")
    assert [r.task_id for r in active] == [rec1.task_id]


@pytest.mark.unit
async def test_list_active_includes_awaiting_input_and_resuming(fake_redis):
    """The pause-protocol states count as ACTIVE (still holding a slot)."""
    paused = await state.create(
        user_id="u", firm_id=None, template_id="t", case_id="c",
        template_spec=_empty_spec(),
    )
    resuming = await state.create(
        user_id="u", firm_id=None, template_id="t", case_id="c",
        template_spec=_empty_spec(),
    )
    await state.set_status(paused.task_id, "AWAITING_INPUT")
    await state.set_status(resuming.task_id, "RESUMING")
    active = await state.list_active_for_user("u")
    assert {r.task_id for r in active} == {paused.task_id, resuming.task_id}


@pytest.mark.unit
async def test_count_active_for_user(fake_redis):
    await state.create(
        user_id="u", firm_id=None, template_id="t", case_id="c",
        template_spec=_empty_spec(),
    )
    await state.create(
        user_id="u", firm_id=None, template_id="t", case_id="c",
        template_spec=_empty_spec(),
    )
    third = await state.create(
        user_id="u", firm_id=None, template_id="t", case_id="c",
        template_spec=_empty_spec(),
    )
    await state.set_status(third.task_id, "FAILED")
    assert await state.count_active_for_user("u") == 2


@pytest.mark.unit
async def test_enqueue_and_drain_queue(fake_redis):
    rec1 = await state.create(
        user_id="u", firm_id=None, template_id="t", case_id="c",
        template_spec=_empty_spec(), status="QUEUED",
    )
    rec2 = await state.create(
        user_id="u", firm_id=None, template_id="t", case_id="c",
        template_spec=_empty_spec(), status="QUEUED",
    )
    await state.enqueue(rec1.task_id, "u")
    await state.enqueue(rec2.task_id, "u")
    assert await state.queue_size("u") == 2
    popped = await state.drain_queue("u")
    # QUEUED records don't count toward active so drain succeeds
    assert popped == rec1.task_id


@pytest.mark.unit
async def test_drain_queue_returns_none_when_over_cap(fake_redis, monkeypatch):
    monkeypatch.setattr(state, "MAX_CONCURRENT_DRY_RUN_TASKS", 1)
    await state.create(
        user_id="u", firm_id=None, template_id="t", case_id="c",
        template_spec=_empty_spec(),
    )
    queued = await state.create(
        user_id="u", firm_id=None, template_id="t", case_id="c",
        template_spec=_empty_spec(), status="QUEUED",
    )
    await state.enqueue(queued.task_id, "u")
    assert await state.drain_queue("u") is None


@pytest.mark.unit
async def test_remove_from_queue_evicts_specific_task(fake_redis):
    rec = await state.create(
        user_id="u", firm_id=None, template_id="t", case_id="c",
        template_spec=_empty_spec(), status="QUEUED",
    )
    await state.enqueue(rec.task_id, "u")
    removed = await state.remove_from_queue(rec.task_id, "u")
    assert removed == 1
    assert await state.queue_size("u") == 0


@pytest.mark.unit
async def test_delete_removes_record_and_drops_indexes(fake_redis):
    rec = await state.create(
        user_id="u", firm_id=None, template_id="t", case_id="c",
        template_spec=_empty_spec(),
    )
    ok = await state.delete(rec.task_id)
    assert ok is True
    assert await state.get(rec.task_id) is None
    assert rec.task_id not in fake_redis.sets.get(state._user_tasks_key("u"), set())


@pytest.mark.unit
async def test_delete_missing_task_returns_false(fake_redis):
    assert await state.delete("missing") is False
