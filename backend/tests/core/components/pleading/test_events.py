"""Tests for the v2 pleading SSE event emitter.

Two paths to cover:
- `emit(user_id, task_id, event_type)` loads the record from state and
  `XADD`s a typed payload to the per-user Redis Stream.
- `emit_removed(user_id, task_id)` writes a lightweight removal sentinel
  used when a record is DELETE-dismissed (the record itself is already gone).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from src.core.components.pleading import events as events_module
from src.core.components.pleading.schemas import V2TemplateDraftTaskRecord


class _FakeStream:
    """Tracks every XADD + EXPIRE call so tests can assert on them."""

    def __init__(self) -> None:
        self.xadds: list[dict] = []
        self.expires: list[tuple[str, int]] = []
        self.closed = False

    async def xadd(self, key: str, fields: dict, *, maxlen=None, approximate=None) -> str:
        entry_id = f"id-{len(self.xadds) + 1}"
        self.xadds.append(
            {"key": key, "fields": fields, "maxlen": maxlen, "approximate": approximate, "entry_id": entry_id}
        )
        return entry_id

    async def expire(self, key: str, ttl: int) -> None:
        self.expires.append((key, ttl))

    async def aclose(self) -> None:
        self.closed = True


def _make_record(**overrides) -> V2TemplateDraftTaskRecord:
    now = datetime.now(timezone.utc)
    base = {
        "task_id": "task-1",
        "user_id": "user-1",
        "case_id": "26_10700",
        "template_id": "tpl",
        "template_name": "Motion to Extend",
        "status": "DRAFTING",
        "bundle_picks": None,
        "created_at": now,
        "updated_at": now,
    }
    base.update(overrides)
    return V2TemplateDraftTaskRecord(**base)


# ─── emit ──────────────────────────────────────────────────────────────


@pytest.mark.unit
async def test_emit_writes_xadd_with_event_type_and_payload(monkeypatch):
    fake = _FakeStream()
    monkeypatch.setattr(events_module, "make_async_redis", lambda *a, **kw: fake)

    record = _make_record()

    async def _get(task_id):
        assert task_id == "task-1"
        return record

    monkeypatch.setattr(events_module.state, "get", _get)

    await events_module.emit("user-1", "task-1", "status_changed")

    assert len(fake.xadds) == 1
    call = fake.xadds[0]
    assert call["key"] == "core:pleading:events:user-1"
    assert call["fields"]["event_type"] == "status_changed"
    # Payload is the JSON-serialized FE-facing response.
    payload = json.loads(call["fields"]["data"])
    assert payload["task_id"] == "task-1"
    assert payload["status"] == "DRAFTING"
    # MAXLEN ~ 500 — bounded ring buffer.
    assert call["maxlen"] == events_module.STREAM_MAXLEN
    assert call["approximate"] is True
    # Sliding TTL on the stream key.
    assert (call["key"], events_module.STREAM_TTL_SECONDS) in fake.expires
    # Connection released.
    assert fake.closed is True


@pytest.mark.unit
async def test_emit_skips_when_record_missing(monkeypatch, caplog):
    fake = _FakeStream()
    monkeypatch.setattr(events_module, "make_async_redis", lambda *a, **kw: fake)

    async def _get(task_id):
        return None

    monkeypatch.setattr(events_module.state, "get", _get)

    await events_module.emit("user-1", "vanished", "status_changed")

    # No XADD, no EXPIRE — and crucially no exception bubbling up. The worker
    # should keep marching forward even if a stale state.get returns None.
    assert fake.xadds == []
    assert fake.expires == []


@pytest.mark.unit
async def test_emit_uses_per_user_stream_key():
    """The stream-key prefix is part of the FE/BE contract — the SSE generator
    in sse.py tails the same key, so a typo would silently break delivery."""
    assert events_module.stream_key("user-42") == "core:pleading:events:user-42"


# ─── emit_removed ──────────────────────────────────────────────────────


@pytest.mark.unit
async def test_emit_removed_writes_a_minimal_xadd(monkeypatch):
    fake = _FakeStream()
    monkeypatch.setattr(events_module, "make_async_redis", lambda *a, **kw: fake)

    await events_module.emit_removed("user-7", "task-9")

    assert len(fake.xadds) == 1
    call = fake.xadds[0]
    assert call["key"] == "core:pleading:events:user-7"
    assert call["fields"]["event_type"] == "removed"
    payload = json.loads(call["fields"]["data"])
    assert payload == {"task_id": "task-9"}
    assert call["maxlen"] == events_module.STREAM_MAXLEN
    assert (call["key"], events_module.STREAM_TTL_SECONDS) in fake.expires
    assert fake.closed is True
