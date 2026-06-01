"""Tests for the v2 dry-run-async event emitter (Redis Streams)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import pytest

from src.core.studio_v2.dry_run.async_run import events
from src.core.studio_v2.dry_run.async_run.schemas import V2DryRunTaskRecord
from src.core.studio_v2.types.fields import TemplateSpecV2


class _FakeAsyncRedis:
    def __init__(self) -> None:
        self.streams: dict[str, list[tuple[str, dict[str, str]]]] = {}
        self.expirations: dict[str, int] = {}
        self.next_id = 0

    async def xadd(self, key: str, fields: dict, *, maxlen: int, approximate: bool) -> str:
        self.next_id += 1
        entry_id = f"100-{self.next_id}"
        self.streams.setdefault(key, []).append((entry_id, fields))
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
    records: dict[str, V2DryRunTaskRecord] = {}

    def _put(record: V2DryRunTaskRecord):
        records[record.task_id] = record

    async def _get(task_id: str):
        return records.get(task_id)

    monkeypatch.setattr(events.state, "get", _get)
    return _put


def _make_record(**overrides) -> V2DryRunTaskRecord:
    now = datetime.now(timezone.utc)
    base = dict(
        task_id="t1",
        user_id="u",
        template_id="tpl",
        case_id="c1",
        template_name="X",
        case_label="C-1",
        status="RUNNING",
        template_spec=TemplateSpecV2(template_id=uuid.uuid4(), fields=[]),
        created_at=now,
        updated_at=now,
    )
    base.update(overrides)
    return V2DryRunTaskRecord(**base)


@pytest.mark.unit
async def test_emit_writes_event_and_refreshes_ttl(fake_redis, fake_state):
    fake_state(_make_record(task_id="t1", status="RUNNING"))

    await events.emit("u", "t1", "status_changed")
    key = events.stream_key("u")
    assert key in fake_redis.streams
    _, fields = fake_redis.streams[key][0]
    assert fields["event_type"] == "status_changed"
    payload = json.loads(fields["data"])
    assert payload["task_id"] == "t1"
    assert payload["status"] == "RUNNING"
    assert fake_redis.expirations[key] == events.STREAM_TTL_SECONDS


@pytest.mark.unit
async def test_emit_awaiting_input_event_type(fake_redis, fake_state):
    """The pause/resume event type composer-async doesn't have."""
    fake_state(_make_record(task_id="t2", status="AWAITING_INPUT"))
    await events.emit("u", "t2", "awaiting_input")
    key = events.stream_key("u")
    _, fields = fake_redis.streams[key][0]
    assert fields["event_type"] == "awaiting_input"


@pytest.mark.unit
async def test_emit_skips_when_task_missing(fake_redis, fake_state):
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
    assert events.stream_key("a").startswith("core:dry_run:events:")
