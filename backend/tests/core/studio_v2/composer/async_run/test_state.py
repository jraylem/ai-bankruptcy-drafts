"""Tests for the v2 composer-async Redis state layer.

Mirrors `tests/core/components/pleading/test_state.py` with a small
in-memory fake redis that supports both decoded-string AND raw-bytes
modes (the composer's upload blob staging needs binary IO).
"""

from __future__ import annotations

import pytest

from src.core.studio_v2.composer.async_run import state


# ─── Fake redis ────────────────────────────────────────────────────────


class _FakeAsyncRedis:
    """Minimal async-redis stand-in. Honors `decode_responses` so the
    binary upload-blob path (decode_responses=False) can round-trip
    bytes while the string-only path round-trips str."""

    def __init__(self, decode_responses: bool = True) -> None:
        self.decode_responses = decode_responses
        self.strings: dict[str, str | bytes] = {}
        self.sets: dict[str, set[str]] = {}
        self.lists: dict[str, list[str]] = {}
        self.ttls: dict[str, int] = {}

    async def setex(self, key: str, ttl: int, value: str | bytes) -> None:
        self.strings[key] = value
        self.ttls[key] = ttl

    async def get(self, key: str) -> str | bytes | None:
        v = self.strings.get(key)
        if v is None:
            return None
        if self.decode_responses and isinstance(v, bytes):
            return v.decode()
        if not self.decode_responses and isinstance(v, str):
            return v.encode()
        return v

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
    """Shared fake redis — both the decoded-string and bytes paths go
    through the same backing storage so an upload-staged blob can be
    fetched back from the bytes-mode client.
    """
    backing = _FakeAsyncRedis(decode_responses=True)
    bytes_view = _FakeAsyncRedis(decode_responses=False)
    bytes_view.strings = backing.strings
    bytes_view.sets = backing.sets
    bytes_view.lists = backing.lists
    bytes_view.ttls = backing.ttls

    def _factory(*args, **kwargs):
        if kwargs.get("decode_responses") is False:
            return bytes_view
        return backing

    monkeypatch.setattr(state, "make_async_redis", _factory)
    return backing


# ─── create / get round-trips ──────────────────────────────────────────


@pytest.mark.unit
async def test_create_generate_record_persists_and_indexes(fake_redis):
    rec = await state.create(
        user_id="user-1",
        firm_id="firm-A",
        kind="generate",
        template_name="My Template",
        template_role="single",
        original_filename="upload.docx",
        upload_blob_key="blob-abc",
    )
    assert rec.status == "PENDING"
    assert rec.kind == "generate"
    assert rec.upload_blob_key == "blob-abc"

    fetched = await state.get(rec.task_id)
    assert fetched is not None and fetched.task_id == rec.task_id
    assert fetched.firm_id == "firm-A"
    assert rec.task_id in fake_redis.sets[state._user_tasks_key("user-1")]


@pytest.mark.unit
async def test_create_regenerate_record(fake_redis):
    rec = await state.create(
        user_id="u",
        firm_id=None,
        kind="regenerate",
        template_id="tpl-X",
        regeneration_instruction="Skip the firm address",
    )
    assert rec.kind == "regenerate"
    assert rec.template_id == "tpl-X"
    assert rec.regeneration_instruction == "Skip the firm address"


@pytest.mark.unit
async def test_get_returns_none_for_missing_task(fake_redis):
    assert await state.get("nope") is None


# ─── status transitions ───────────────────────────────────────────────


@pytest.mark.unit
async def test_set_status_flips_field(fake_redis):
    rec = await state.create(user_id="u", firm_id=None, kind="generate")
    after = await state.set_status(rec.task_id, "RUNNING")
    assert after is not None and after.status == "RUNNING"


@pytest.mark.unit
async def test_set_completed_generate_persists_result_and_template_id(fake_redis):
    from src.core.studio_v2.services.composer.schemas import TemplateGenerateResponseV2
    rec = await state.create(user_id="u", firm_id=None, kind="generate")
    fake_result = TemplateGenerateResponseV2(
        template_id="new-tpl",
        name="t",
        template_spec=[],
        original_doc_url="http://x",
        template_doc_url="http://y",
    )
    after = await state.set_completed_generate(
        rec.task_id, result=fake_result, template_id="new-tpl",
    )
    assert after is not None
    assert after.status == "COMPLETED"
    assert after.template_id == "new-tpl"
    assert after.generate_result.template_id == "new-tpl"


@pytest.mark.unit
async def test_set_failed_persists_error(fake_redis):
    rec = await state.create(user_id="u", firm_id=None, kind="generate")
    after = await state.set_failed(rec.task_id, "LLM timeout")
    assert after is not None
    assert after.status == "FAILED"
    assert after.error == "LLM timeout"


@pytest.mark.unit
async def test_set_cancelled_sets_flag_and_status(fake_redis):
    rec = await state.create(user_id="u", firm_id=None, kind="generate")
    after = await state.set_cancelled(rec.task_id)
    assert after is not None
    assert after.status == "CANCELLED"
    assert await state.is_cancelled(rec.task_id) is True


@pytest.mark.unit
async def test_is_cancelled_false_when_not_set(fake_redis):
    rec = await state.create(user_id="u", firm_id=None, kind="generate")
    assert await state.is_cancelled(rec.task_id) is False


# ─── upload blob staging ──────────────────────────────────────────────


@pytest.mark.unit
async def test_stage_and_fetch_upload_blob_round_trip(fake_redis):
    payload = b"PK\x03\x04 fake docx bytes \x00\xa3"
    blob_key = await state.stage_upload_blob(payload)
    assert blob_key  # non-empty hex

    fetched = await state.fetch_upload_blob(blob_key)
    assert fetched == payload


@pytest.mark.unit
async def test_discard_upload_blob_removes_it(fake_redis):
    blob_key = await state.stage_upload_blob(b"data")
    await state.discard_upload_blob(blob_key)
    assert await state.fetch_upload_blob(blob_key) is None


# ─── queries + queue ──────────────────────────────────────────────────


@pytest.mark.unit
async def test_list_for_user_returns_newest_first(fake_redis):
    import asyncio
    rec1 = await state.create(user_id="u", firm_id=None, kind="generate", template_name="t1")
    await asyncio.sleep(0.01)
    rec2 = await state.create(user_id="u", firm_id=None, kind="generate", template_name="t2")
    out = await state.list_for_user("u")
    assert [r.task_id for r in out] == [rec2.task_id, rec1.task_id]


@pytest.mark.unit
async def test_list_active_for_user_filters_terminal(fake_redis):
    rec1 = await state.create(user_id="u", firm_id=None, kind="generate")
    rec2 = await state.create(user_id="u", firm_id=None, kind="generate")
    await state.set_status(rec2.task_id, "COMPLETED")
    active = await state.list_active_for_user("u")
    assert [r.task_id for r in active] == [rec1.task_id]


@pytest.mark.unit
async def test_count_active_for_user(fake_redis):
    await state.create(user_id="u", firm_id=None, kind="generate")
    await state.create(user_id="u", firm_id=None, kind="generate")
    third = await state.create(user_id="u", firm_id=None, kind="generate")
    await state.set_status(third.task_id, "FAILED")
    assert await state.count_active_for_user("u") == 2


@pytest.mark.unit
async def test_enqueue_and_drain_queue(fake_redis):
    rec1 = await state.create(user_id="u", firm_id=None, kind="generate")
    rec2 = await state.create(user_id="u", firm_id=None, kind="generate")
    await state.enqueue(rec1.task_id, "u")
    await state.enqueue(rec2.task_id, "u")
    assert await state.queue_size("u") == 2
    # drain pops oldest first
    popped = await state.drain_queue("u")
    assert popped == rec1.task_id


@pytest.mark.unit
async def test_drain_queue_returns_none_when_over_cap(fake_redis, monkeypatch):
    """When active count >= MAX_CONCURRENT, drain returns None so the
    QUEUED task stays parked."""
    monkeypatch.setattr(state, "MAX_CONCURRENT_COMPOSER_TASKS", 1)
    active = await state.create(user_id="u", firm_id=None, kind="generate")  # PENDING (active)
    queued = await state.create(user_id="u", firm_id=None, kind="generate", status="QUEUED")
    await state.enqueue(queued.task_id, "u")
    assert await state.drain_queue("u") is None


@pytest.mark.unit
async def test_remove_from_queue_evicts_specific_task(fake_redis):
    rec = await state.create(user_id="u", firm_id=None, kind="generate", status="QUEUED")
    await state.enqueue(rec.task_id, "u")
    removed = await state.remove_from_queue(rec.task_id, "u")
    assert removed == 1
    assert await state.queue_size("u") == 0


@pytest.mark.unit
async def test_delete_removes_record_and_drops_indexes(fake_redis):
    rec = await state.create(
        user_id="u", firm_id=None, kind="generate", upload_blob_key="blob-1",
    )
    await state.stage_upload_blob(b"data")  # populate something so delete exercises blob path too
    ok = await state.delete(rec.task_id)
    assert ok is True
    assert await state.get(rec.task_id) is None
    assert rec.task_id not in fake_redis.sets.get(state._user_tasks_key("u"), set())


@pytest.mark.unit
async def test_delete_missing_task_returns_false(fake_redis):
    assert await state.delete("missing") is False
