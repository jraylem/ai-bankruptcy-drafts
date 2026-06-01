"""Tests for the v2 composer-async event emitter (Redis Streams)."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from src.core.studio_v2.composer.async_run import events, state
from src.core.studio_v2.composer.async_run.schemas import V2ComposerTaskRecord


class _FakeAsyncRedis:
    def __init__(self) -> None:
        self.streams: dict[str, list[tuple[str, dict[str, str]]]] = {}
        self.expirations: dict[str, int] = {}
        self.next_id = 0

    async def xadd(self, key: str, fields: dict, *, maxlen: int, approximate: bool) -> str:
        self.next_id += 1
        entry_id = f"100-{self.next_id}"
        self.streams.setdefault(key, []).append((entry_id, fields))
        # Honor maxlen — keep only the last N entries.
        self.streams[key] = self.streams[key][-maxlen:]
        return entry_id

    async def expire(self, key: str, ttl: int) -> None:
        self.expirations[key] = ttl

    async def aclose(self) -> None:
        return None


@pytest.fixture
def fake_redis(monkeypatch) -> _FakeAsyncRedis:
    fake = _FakeAsyncRedis()
    monkeypatch.setattr(events, "make_async_redis", lambda *args, **kwargs: fake)
    return fake


@pytest.fixture
def fake_state(monkeypatch):
    """Stub `state.get` so emit() doesn't need a real Redis behind it."""
    records: dict[str, V2ComposerTaskRecord] = {}

    def _put(record: V2ComposerTaskRecord):
        records[record.task_id] = record

    async def _get(task_id: str):
        return records.get(task_id)

    monkeypatch.setattr(events.state, "get", _get)
    return _put


@pytest.mark.unit
async def test_emit_writes_event_and_refreshes_ttl(fake_redis, fake_state):
    now = datetime.now(timezone.utc)
    fake_state(V2ComposerTaskRecord(
        task_id="t1",
        user_id="u",
        kind="generate",
        template_name="X",
        status="RUNNING",
        created_at=now, updated_at=now,
    ))

    await events.emit("u", "t1", "status_changed")
    key = events.stream_key("u")
    assert key in fake_redis.streams
    entry_id, fields = fake_redis.streams[key][0]
    assert fields["event_type"] == "status_changed"
    payload = json.loads(fields["data"])
    assert payload["task_id"] == "t1"
    assert payload["status"] == "RUNNING"
    assert fake_redis.expirations[key] == events.STREAM_TTL_SECONDS


@pytest.mark.unit
async def test_emit_skips_when_task_missing(fake_redis, fake_state):
    # No record put — emit should noop, not write anything.
    await events.emit("u", "missing-task", "completed")
    assert fake_redis.streams == {}


@pytest.mark.unit
async def test_emit_removed_writes_lightweight_event(fake_redis):
    await events.emit_removed("u", "t-gone")
    key = events.stream_key("u")
    assert key in fake_redis.streams
    _, fields = fake_redis.streams[key][0]
    assert fields["event_type"] == "removed"
    assert "t-gone" in fields["data"]


@pytest.mark.unit
async def test_stream_key_per_user_isolation():
    assert events.stream_key("a") != events.stream_key("b")
    assert events.stream_key("a").startswith("core:composer:events:")
