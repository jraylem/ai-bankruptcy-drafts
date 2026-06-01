"""Tests for the v2 composer-async Taskiq workers.

We don't run the actual Taskiq dispatch loop — we call the
underlying task implementations directly and assert the state +
event transitions. The actual composer work (`generate_template_v2`,
`regenerate_template_v2`) is mocked since the tasks are pure
orchestration wrappers around those services.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from src.core.studio_v2.composer.async_run import events, state, tasks
from src.core.studio_v2.composer.async_run.schemas import V2ComposerTaskRecord
from src.core.studio_v2.services.composer.schemas import (
    TemplateGenerateResponseV2,
    TemplateRegenerateDiffV2,
)


@pytest.fixture(autouse=True)
def patched_state_and_events(monkeypatch):
    """Replace state's redis client + cancel-check + events.emit with
    in-memory fakes so tests don't need a real Redis."""
    records: dict[str, V2ComposerTaskRecord] = {}
    cancelled_flags: set[str] = set()
    emitted: list[tuple[str, str, str]] = []
    drained_users: list[str] = []
    blobs: dict[str, bytes] = {}

    async def _get(task_id):
        return records.get(task_id)

    async def _set_status(task_id, status):
        rec = records.get(task_id)
        if rec is None:
            return None
        rec.status = status
        return rec

    async def _set_completed_generate(task_id, *, result, template_id):
        rec = records.get(task_id)
        if rec is None:
            return None
        rec.status = "COMPLETED"
        rec.generate_result = result
        rec.template_id = template_id
        return rec

    async def _set_completed_regenerate(task_id, *, result):
        rec = records.get(task_id)
        if rec is None:
            return None
        rec.status = "COMPLETED"
        rec.regenerate_result = result
        return rec

    async def _set_failed(task_id, error):
        rec = records.get(task_id)
        if rec is None:
            return None
        rec.status = "FAILED"
        rec.error = error
        return rec

    async def _is_cancelled(task_id):
        return task_id in cancelled_flags

    async def _drain_queue(user_id):
        drained_users.append(user_id)
        return None  # no next-queued task in these tests

    async def _fetch_blob(blob_key):
        return blobs.get(blob_key)

    async def _discard_blob(blob_key):
        blobs.pop(blob_key, None)

    async def _emit(user_id, task_id, event_type):
        emitted.append((user_id, task_id, event_type))

    monkeypatch.setattr(tasks.state, "get", _get)
    monkeypatch.setattr(tasks.state, "set_status", _set_status)
    monkeypatch.setattr(tasks.state, "set_completed_generate", _set_completed_generate)
    monkeypatch.setattr(tasks.state, "set_completed_regenerate", _set_completed_regenerate)
    monkeypatch.setattr(tasks.state, "set_failed", _set_failed)
    monkeypatch.setattr(tasks.state, "is_cancelled", _is_cancelled)
    monkeypatch.setattr(tasks.state, "drain_queue", _drain_queue)
    monkeypatch.setattr(tasks.state, "fetch_upload_blob", _fetch_blob)
    monkeypatch.setattr(tasks.state, "discard_upload_blob", _discard_blob)
    monkeypatch.setattr(tasks.events, "emit", _emit)

    return {
        "records": records,
        "cancelled": cancelled_flags,
        "emitted": emitted,
        "drained": drained_users,
        "blobs": blobs,
    }


def _make_record(**overrides) -> V2ComposerTaskRecord:
    now = datetime.now(timezone.utc)
    defaults = dict(
        task_id="task-1",
        user_id="user-1",
        firm_id="firm-A",
        kind="generate",
        template_name="My Template",
        template_role="single",
        original_filename="upload.docx",
        upload_blob_key="blob-1",
        status="PENDING",
        created_at=now,
        updated_at=now,
    )
    defaults.update(overrides)
    return V2ComposerTaskRecord(**defaults)


# ─── run_composer_generate ────────────────────────────────────────────


@pytest.mark.unit
async def test_generate_happy_path(patched_state_and_events):
    fixt = patched_state_and_events
    rec = _make_record()
    fixt["records"][rec.task_id] = rec
    fixt["blobs"]["blob-1"] = b"docx-bytes"

    fake_result = TemplateGenerateResponseV2(
        template_id="new-tpl",
        name="My Template",
        template_spec=[],
        original_doc_url="http://orig",
        template_doc_url="http://tmpl",
    )
    with patch.object(tasks, "parse_document_v2", new=AsyncMock(return_value=object())), \
         patch.object(tasks, "generate_template_v2", new=AsyncMock(return_value=fake_result)):
        await tasks._run_composer_generate_impl(
            task_id=rec.task_id, user_id="user-1", record=rec,
        )

    assert fixt["records"]["task-1"].status == "COMPLETED"
    assert fixt["records"]["task-1"].template_id == "new-tpl"
    events_seen = [e[2] for e in fixt["emitted"]]
    assert "status_changed" in events_seen
    assert "completed" in events_seen
    assert "blob-1" not in fixt["blobs"]  # discarded after consume
    assert "user-1" in fixt["drained"]


@pytest.mark.unit
async def test_generate_marks_failed_when_service_throws(patched_state_and_events):
    fixt = patched_state_and_events
    rec = _make_record()
    fixt["records"][rec.task_id] = rec
    fixt["blobs"]["blob-1"] = b"docx-bytes"

    with patch.object(tasks, "parse_document_v2", new=AsyncMock(return_value=object())), \
         patch.object(tasks, "generate_template_v2", new=AsyncMock(side_effect=RuntimeError("LLM down"))):
        await tasks._run_composer_generate_impl(
            task_id=rec.task_id, user_id="user-1", record=rec,
        )

    assert fixt["records"]["task-1"].status == "FAILED"
    assert "LLM down" in fixt["records"]["task-1"].error
    assert "failed" in [e[2] for e in fixt["emitted"]]
    assert "blob-1" not in fixt["blobs"]  # discarded even on failure


@pytest.mark.unit
async def test_generate_bails_when_blob_missing(patched_state_and_events):
    fixt = patched_state_and_events
    rec = _make_record(upload_blob_key="blob-not-staged")
    fixt["records"][rec.task_id] = rec

    await tasks._run_composer_generate_impl(
        task_id=rec.task_id, user_id="user-1", record=rec,
    )

    assert fixt["records"]["task-1"].status == "FAILED"
    assert "expired" in fixt["records"]["task-1"].error.lower()


@pytest.mark.unit
async def test_generate_bails_when_already_cancelled(patched_state_and_events):
    fixt = patched_state_and_events
    rec = _make_record()
    fixt["records"][rec.task_id] = rec
    fixt["cancelled"].add(rec.task_id)

    await tasks._run_composer_generate_impl(
        task_id=rec.task_id, user_id="user-1", record=rec,
    )

    # Cancelled tasks skip status change + LLM work, return immediately.
    assert fixt["records"]["task-1"].status == "PENDING"  # untouched
    assert fixt["emitted"] == []


@pytest.mark.unit
async def test_generate_drops_result_when_cancelled_mid_run(patched_state_and_events):
    fixt = patched_state_and_events
    rec = _make_record()
    fixt["records"][rec.task_id] = rec
    fixt["blobs"]["blob-1"] = b"docx-bytes"

    fake_result = TemplateGenerateResponseV2(
        template_id="new", name="x", template_spec=[],
        original_doc_url="o", template_doc_url="t",
    )

    # Cancel AFTER the work succeeds but before persist.
    async def _is_cancelled_late(task_id):
        # First call (at start) returns False; second call (post-LLM) returns True.
        _is_cancelled_late.calls = getattr(_is_cancelled_late, "calls", 0) + 1
        return _is_cancelled_late.calls > 1

    import pytest as _pytest
    with patch.object(tasks.state, "is_cancelled", new=_is_cancelled_late), \
         patch.object(tasks, "parse_document_v2", new=AsyncMock(return_value=object())), \
         patch.object(tasks, "generate_template_v2", new=AsyncMock(return_value=fake_result)):
        await tasks._run_composer_generate_impl(
            task_id=rec.task_id, user_id="user-1", record=rec,
        )

    assert fixt["records"]["task-1"].status == "RUNNING"  # NOT COMPLETED
    assert fixt["records"]["task-1"].generate_result is None  # not persisted


# ─── run_composer_regenerate ──────────────────────────────────────────


@pytest.mark.unit
async def test_regenerate_happy_path(patched_state_and_events):
    fixt = patched_state_and_events
    rec = _make_record(
        task_id="task-r1",
        kind="regenerate",
        template_id="tpl-existing",
        upload_blob_key=None,
        regeneration_instruction="don't extract firm address",
    )
    fixt["records"][rec.task_id] = rec

    fake_diff = TemplateRegenerateDiffV2(
        template_id="tpl-existing",
        inserted=[],
        updated=[],
        deleted=[],
        preserved_params=[],
        template_doc_url="http://t",
    )
    with patch.object(tasks, "regenerate_template_v2", new=AsyncMock(return_value=fake_diff)):
        await tasks._run_composer_regenerate_impl(
            task_id=rec.task_id, user_id="user-1", record=rec,
        )

    assert fixt["records"]["task-r1"].status == "COMPLETED"
    assert fixt["records"]["task-r1"].regenerate_result.template_id == "tpl-existing"
    assert "completed" in [e[2] for e in fixt["emitted"]]


@pytest.mark.unit
async def test_regenerate_bails_when_no_template_id(patched_state_and_events):
    fixt = patched_state_and_events
    rec = _make_record(
        task_id="task-r2", kind="regenerate", template_id=None, upload_blob_key=None,
    )
    fixt["records"][rec.task_id] = rec

    await tasks._run_composer_regenerate_impl(
        task_id=rec.task_id, user_id="user-1", record=rec,
    )

    assert fixt["records"]["task-r2"].status == "FAILED"
    assert "template_id" in fixt["records"]["task-r2"].error.lower()


@pytest.mark.unit
async def test_regenerate_marks_failed_when_service_throws(patched_state_and_events):
    fixt = patched_state_and_events
    rec = _make_record(
        task_id="task-r3", kind="regenerate", template_id="tpl-X", upload_blob_key=None,
    )
    fixt["records"][rec.task_id] = rec

    with patch.object(tasks, "regenerate_template_v2", new=AsyncMock(side_effect=RuntimeError("timeout"))):
        await tasks._run_composer_regenerate_impl(
            task_id=rec.task_id, user_id="user-1", record=rec,
        )

    assert fixt["records"]["task-r3"].status == "FAILED"
    assert "timeout" in fixt["records"]["task-r3"].error


# ─── _try_drain_user_queue ─────────────────────────────────────────────


@pytest.mark.unit
async def test_drain_pops_next_queued_and_kicks_generate(monkeypatch, patched_state_and_events):
    """When a QUEUED task is ready to run, _try_drain pops it, flips it
    PENDING, emits status_changed, and kicks the matching task worker."""
    fixt = patched_state_and_events
    queued = _make_record(task_id="q-1", status="QUEUED", kind="generate")
    fixt["records"][queued.task_id] = queued

    async def _drain(user_id):
        return queued.task_id

    monkeypatch.setattr(tasks.state, "drain_queue", _drain)
    fake_kiq = AsyncMock()
    monkeypatch.setattr(tasks.run_composer_generate, "kiq", fake_kiq)

    await tasks._try_drain_user_queue("user-1")

    assert fixt["records"]["q-1"].status == "PENDING"
    assert ("user-1", "q-1", "status_changed") in fixt["emitted"]
    fake_kiq.assert_awaited_once_with(task_id="q-1", user_id="user-1")


@pytest.mark.unit
async def test_drain_kicks_regenerate_worker_when_kind_matches(monkeypatch, patched_state_and_events):
    fixt = patched_state_and_events
    queued = _make_record(task_id="q-2", status="QUEUED", kind="regenerate", template_id="tpl-X")
    fixt["records"][queued.task_id] = queued

    async def _drain(user_id):
        return queued.task_id

    monkeypatch.setattr(tasks.state, "drain_queue", _drain)
    fake_kiq = AsyncMock()
    monkeypatch.setattr(tasks.run_composer_regenerate, "kiq", fake_kiq)

    await tasks._try_drain_user_queue("user-1")
    fake_kiq.assert_awaited_once_with(task_id="q-2", user_id="user-1")


@pytest.mark.unit
async def test_drain_is_noop_when_queue_empty(monkeypatch, patched_state_and_events):
    async def _drain(user_id):
        return None

    monkeypatch.setattr(tasks.state, "drain_queue", _drain)
    # Should not raise + no events.
    await tasks._try_drain_user_queue("user-1")
    assert patched_state_and_events["emitted"] == []


@pytest.mark.unit
async def test_drain_skips_when_record_vanished(monkeypatch, patched_state_and_events):
    """If drain_queue returns a task_id but the record has been deleted
    (TTL expired between drain and get), bail without kicking."""
    async def _drain(user_id):
        return "task-gone"

    monkeypatch.setattr(tasks.state, "drain_queue", _drain)
    fake_kiq = AsyncMock()
    monkeypatch.setattr(tasks.run_composer_generate, "kiq", fake_kiq)

    await tasks._try_drain_user_queue("user-1")
    fake_kiq.assert_not_called()
