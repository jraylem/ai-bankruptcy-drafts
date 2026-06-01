"""Tests for the v2 dry-run-async Taskiq workers.

Mirrors `tests/core/studio_v2/composer/async_run/test_tasks.py` but
exercises the pause/resume protocol (AWAITING_INPUT branch + resume
worker) that composer-async doesn't have. The actual pipeline work
(`execute_dry_run_v2`, `resume_dry_run_v2`) is mocked since the
tasks are pure orchestration wrappers around those services.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from src.core.studio_v2.dry_run.async_run import tasks
from src.core.studio_v2.dry_run.async_run.schemas import V2DryRunTaskRecord
from src.core.studio_v2.types.fields import TemplateSpecV2
from src.core.studio_v2.types.orchestration import (
    AwaitingInputResponseV2,
    DryRunResponseV2,
)


@pytest.fixture(autouse=True)
def patched_state_and_events(monkeypatch):
    """In-memory fakes for the state + events surfaces the tasks use."""
    records: dict[str, V2DryRunTaskRecord] = {}
    cancelled_flags: set[str] = set()
    emitted: list[tuple[str, str, str]] = []
    drained_users: list[str] = []
    set_completed_results: list = []

    async def _get(task_id):
        return records.get(task_id)

    async def _set_status(task_id, status):
        rec = records.get(task_id)
        if rec is None:
            return None
        rec.status = status
        return rec

    async def _set_awaiting_input(task_id, *, resolved_values, pending_inputs):
        rec = records.get(task_id)
        if rec is None:
            return None
        rec.status = "AWAITING_INPUT"
        rec.resolved_values = resolved_values
        rec.pending_inputs = pending_inputs
        return rec

    async def _set_completed(task_id, *, result):
        rec = records.get(task_id)
        if rec is None:
            return None
        rec.status = "COMPLETED"
        rec.result = result
        rec.pending_inputs = None
        set_completed_results.append(result)
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
        return None

    async def _emit(user_id, task_id, event_type):
        emitted.append((user_id, task_id, event_type))

    monkeypatch.setattr(tasks.state, "get", _get)
    monkeypatch.setattr(tasks.state, "set_status", _set_status)
    monkeypatch.setattr(tasks.state, "set_awaiting_input", _set_awaiting_input)
    monkeypatch.setattr(tasks.state, "set_completed", _set_completed)
    monkeypatch.setattr(tasks.state, "set_failed", _set_failed)
    monkeypatch.setattr(tasks.state, "is_cancelled", _is_cancelled)
    monkeypatch.setattr(tasks.state, "drain_queue", _drain_queue)
    monkeypatch.setattr(tasks.events, "emit", _emit)

    return {
        "records": records,
        "cancelled": cancelled_flags,
        "emitted": emitted,
        "drained": drained_users,
        "completed_results": set_completed_results,
    }


def _make_record(**overrides) -> V2DryRunTaskRecord:
    now = datetime.now(timezone.utc)
    defaults = dict(
        task_id="task-1",
        user_id="user-1",
        firm_id="firm-A",
        template_id="tpl",
        case_id="case-X",
        template_name="My Template",
        case_label="C-1",
        status="PENDING",
        template_spec=TemplateSpecV2(template_id=uuid.uuid4(), fields=[]),
        created_at=now,
        updated_at=now,
    )
    defaults.update(overrides)
    return V2DryRunTaskRecord(**defaults)


def _completed_response() -> DryRunResponseV2:
    return DryRunResponseV2(
        run_id=str(uuid.uuid4()),
        template_id="tpl",
        case_id="case-X",
        resolved_values=[],
        generated_doc_url="https://r2/x.docx",
        r2_object_key="dry_run/x.docx",
        unresolved=[],
        warnings=[],
        children=[],
    )


def _awaiting_response() -> AwaitingInputResponseV2:
    return AwaitingInputResponseV2(
        run_id=str(uuid.uuid4()),
        template_id="tpl",
        case_id="case-X",
        resolved_values=[],
        pending_inputs={},
    )


# ─── run_dry_run_initial ──────────────────────────────────────────────


@pytest.mark.unit
async def test_initial_no_pause_completes_in_one_pass(patched_state_and_events):
    """Pipeline returns DryRunResponseV2 directly — set_completed fires,
    completed event emits, queue drains."""
    fixt = patched_state_and_events
    rec = _make_record()
    fixt["records"][rec.task_id] = rec
    result = _completed_response()

    with patch.object(tasks, "execute_dry_run_v2", new=AsyncMock(return_value=result)):
        await tasks._run_dry_run_initial_impl(
            task_id=rec.task_id, user_id="user-1", record=rec,
        )

    assert fixt["records"]["task-1"].status == "COMPLETED"
    events_seen = [e[2] for e in fixt["emitted"]]
    assert "status_changed" in events_seen
    assert "completed" in events_seen
    assert "user-1" in fixt["drained"]


@pytest.mark.unit
async def test_initial_pause_at_awaiting_input(patched_state_and_events):
    """Pipeline returns AwaitingInputResponseV2 — set_awaiting_input
    fires, awaiting_input event emits, queue is NOT drained (slot
    still held)."""
    fixt = patched_state_and_events
    rec = _make_record()
    fixt["records"][rec.task_id] = rec
    awaiting = _awaiting_response()

    with patch.object(tasks, "execute_dry_run_v2", new=AsyncMock(return_value=awaiting)):
        await tasks._run_dry_run_initial_impl(
            task_id=rec.task_id, user_id="user-1", record=rec,
        )

    assert fixt["records"]["task-1"].status == "AWAITING_INPUT"
    events_seen = [e[2] for e in fixt["emitted"]]
    assert "awaiting_input" in events_seen
    # Slot still held while user is picking — do NOT drain.
    assert fixt["drained"] == []


@pytest.mark.unit
async def test_initial_marks_failed_when_service_throws(patched_state_and_events):
    fixt = patched_state_and_events
    rec = _make_record()
    fixt["records"][rec.task_id] = rec

    with patch.object(
        tasks,
        "execute_dry_run_v2",
        new=AsyncMock(side_effect=RuntimeError("Gmail tool error")),
    ):
        await tasks._run_dry_run_initial_impl(
            task_id=rec.task_id, user_id="user-1", record=rec,
        )

    assert fixt["records"]["task-1"].status == "FAILED"
    assert "Gmail" in fixt["records"]["task-1"].error
    assert "failed" in [e[2] for e in fixt["emitted"]]
    # Failed task releases the slot.
    assert "user-1" in fixt["drained"]


@pytest.mark.unit
async def test_initial_bails_when_already_cancelled(patched_state_and_events):
    fixt = patched_state_and_events
    rec = _make_record()
    fixt["records"][rec.task_id] = rec
    fixt["cancelled"].add(rec.task_id)

    await tasks._run_dry_run_initial_impl(
        task_id=rec.task_id, user_id="user-1", record=rec,
    )

    # Cancelled tasks skip work + don't transition state.
    assert fixt["records"]["task-1"].status == "PENDING"
    assert fixt["emitted"] == []


@pytest.mark.unit
async def test_initial_drops_result_when_cancelled_mid_run(patched_state_and_events):
    """Cancel between LLM completing + persist — result is discarded."""
    fixt = patched_state_and_events
    rec = _make_record()
    fixt["records"][rec.task_id] = rec
    result = _completed_response()

    async def _is_cancelled_late(task_id):
        _is_cancelled_late.calls = getattr(_is_cancelled_late, "calls", 0) + 1
        return _is_cancelled_late.calls > 1

    with patch.object(tasks.state, "is_cancelled", new=_is_cancelled_late), \
         patch.object(tasks, "execute_dry_run_v2", new=AsyncMock(return_value=result)):
        await tasks._run_dry_run_initial_impl(
            task_id=rec.task_id, user_id="user-1", record=rec,
        )

    # RUNNING was set when the worker started, but COMPLETED is NOT
    # persisted because cancel raced in.
    assert fixt["records"]["task-1"].status == "RUNNING"
    assert fixt["records"]["task-1"].result is None
    assert "user-1" in fixt["drained"]


# ─── run_dry_run_resume ───────────────────────────────────────────────


@pytest.mark.unit
async def test_resume_happy_path(patched_state_and_events):
    fixt = patched_state_and_events
    rec = _make_record(
        task_id="r-1",
        status="RESUMING",
        resolved_values=[],
        pending_inputs={},
        user_picks={"creditor": {"value": "Acme"}},
    )
    fixt["records"][rec.task_id] = rec
    result = _completed_response()

    with patch.object(tasks, "resume_dry_run_v2", new=AsyncMock(return_value=result)):
        await tasks._run_dry_run_resume_impl(
            task_id=rec.task_id, user_id="user-1", record=rec,
        )

    assert fixt["records"]["r-1"].status == "COMPLETED"
    assert "completed" in [e[2] for e in fixt["emitted"]]
    assert "user-1" in fixt["drained"]


@pytest.mark.unit
async def test_resume_bails_when_picks_missing(patched_state_and_events):
    """Resume without user_picks/resolved_values on the record is a
    programmer error — fail cleanly."""
    fixt = patched_state_and_events
    rec = _make_record(task_id="r-2", status="RESUMING")  # no picks set
    fixt["records"][rec.task_id] = rec

    await tasks._run_dry_run_resume_impl(
        task_id=rec.task_id, user_id="user-1", record=rec,
    )

    assert fixt["records"]["r-2"].status == "FAILED"
    assert "missing" in fixt["records"]["r-2"].error.lower()


@pytest.mark.unit
async def test_resume_marks_failed_when_service_throws(patched_state_and_events):
    fixt = patched_state_and_events
    rec = _make_record(
        task_id="r-3",
        status="RESUMING",
        resolved_values=[],
        pending_inputs={},
        user_picks={"x": {"value": "y"}},
    )
    fixt["records"][rec.task_id] = rec

    with patch.object(
        tasks,
        "resume_dry_run_v2",
        new=AsyncMock(side_effect=RuntimeError("heal agent crashed")),
    ):
        await tasks._run_dry_run_resume_impl(
            task_id=rec.task_id, user_id="user-1", record=rec,
        )

    assert fixt["records"]["r-3"].status == "FAILED"
    assert "heal" in fixt["records"]["r-3"].error.lower()


@pytest.mark.unit
async def test_resume_bails_when_already_cancelled(patched_state_and_events):
    fixt = patched_state_and_events
    rec = _make_record(
        task_id="r-4",
        status="RESUMING",
        resolved_values=[],
        pending_inputs={},
        user_picks={"x": {"value": "y"}},
    )
    fixt["records"][rec.task_id] = rec
    fixt["cancelled"].add(rec.task_id)

    await tasks._run_dry_run_resume_impl(
        task_id=rec.task_id, user_id="user-1", record=rec,
    )

    # Cancelled — skip work + no events.
    assert fixt["records"]["r-4"].status == "RESUMING"
    assert fixt["emitted"] == []


@pytest.mark.unit
async def test_resume_drops_result_when_cancelled_mid_run(patched_state_and_events):
    fixt = patched_state_and_events
    rec = _make_record(
        task_id="r-5",
        status="RESUMING",
        resolved_values=[],
        pending_inputs={},
        user_picks={"x": {"value": "y"}},
    )
    fixt["records"][rec.task_id] = rec
    result = _completed_response()

    async def _is_cancelled_late(task_id):
        _is_cancelled_late.calls = getattr(_is_cancelled_late, "calls", 0) + 1
        return _is_cancelled_late.calls > 1

    with patch.object(tasks.state, "is_cancelled", new=_is_cancelled_late), \
         patch.object(tasks, "resume_dry_run_v2", new=AsyncMock(return_value=result)):
        await tasks._run_dry_run_resume_impl(
            task_id=rec.task_id, user_id="user-1", record=rec,
        )

    assert fixt["records"]["r-5"].status == "RESUMING"
    assert fixt["records"]["r-5"].result is None


# ─── _try_drain_user_queue ─────────────────────────────────────────────


@pytest.mark.unit
async def test_drain_pops_next_queued_and_kicks_initial(monkeypatch, patched_state_and_events):
    """Drain always kicks the initial worker — queued tasks haven't
    started yet, so they always go through run_dry_run_initial."""
    fixt = patched_state_and_events
    queued = _make_record(task_id="q-1", status="QUEUED")
    fixt["records"][queued.task_id] = queued

    async def _drain(user_id):
        return queued.task_id

    monkeypatch.setattr(tasks.state, "drain_queue", _drain)
    fake_kiq = AsyncMock()
    monkeypatch.setattr(tasks.run_dry_run_initial, "kiq", fake_kiq)

    await tasks._try_drain_user_queue("user-1")

    assert fixt["records"]["q-1"].status == "PENDING"
    assert ("user-1", "q-1", "status_changed") in fixt["emitted"]
    fake_kiq.assert_awaited_once_with(task_id="q-1", user_id="user-1")


@pytest.mark.unit
async def test_drain_noop_when_queue_empty(monkeypatch, patched_state_and_events):
    async def _drain(user_id):
        return None

    monkeypatch.setattr(tasks.state, "drain_queue", _drain)
    await tasks._try_drain_user_queue("user-1")
    assert patched_state_and_events["emitted"] == []


@pytest.mark.unit
async def test_drain_skips_when_record_vanished(monkeypatch, patched_state_and_events):
    async def _drain(user_id):
        return "task-gone"

    monkeypatch.setattr(tasks.state, "drain_queue", _drain)
    fake_kiq = AsyncMock()
    monkeypatch.setattr(tasks.run_dry_run_initial, "kiq", fake_kiq)

    await tasks._try_drain_user_queue("user-1")
    fake_kiq.assert_not_called()


# ─── Decorated wrappers — cost_attribution context ─────────────────────


@pytest.mark.unit
async def test_run_dry_run_initial_no_record_returns_silently(patched_state_and_events):
    """If the task was deleted between enqueue + dispatch, the wrapper
    should noop instead of raising."""
    # No record put for "ghost"
    await tasks.run_dry_run_initial(task_id="ghost", user_id="user-1")
    # No exceptions, no events
    assert patched_state_and_events["emitted"] == []


@pytest.mark.unit
async def test_run_dry_run_resume_no_record_returns_silently(patched_state_and_events):
    await tasks.run_dry_run_resume(task_id="ghost", user_id="user-1")
    assert patched_state_and_events["emitted"] == []
