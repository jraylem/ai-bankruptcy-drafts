"""Tests for the v2 dry-run-async router.

Direct async invocation of the route handlers — bypasses FastAPI's
TestClient + auth wiring. Covers queue caps, ownership, status flips,
event emissions, and the AWAITING_INPUT → submit-input → RESUMING
pause/resume protocol composer-async doesn't have.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from src.core.studio_v2.dry_run.async_run import router as router_mod
from src.core.studio_v2.dry_run.async_run import state
from src.core.studio_v2.dry_run.async_run.schemas import (
    StartDryRunRequest,
    SubmitInputRequest,
    V2DryRunTaskRecord,
)
from src.core.studio_v2.types.fields import TemplateSpecV2
from src.core.studio_v2.types.picks import SingleValuePickV2


@pytest.fixture(autouse=True)
def patched_state_and_kicks(monkeypatch):
    records: dict[str, V2DryRunTaskRecord] = {}
    queue: list[str] = []
    emitted: list[tuple[str, str, str]] = []
    next_task_id = {"i": 0}

    async def _create(**kwargs):
        next_task_id["i"] += 1
        tid = f"task-{next_task_id['i']}"
        now = datetime.now(timezone.utc)
        rec = V2DryRunTaskRecord(
            task_id=tid,
            user_id=kwargs.get("user_id"),
            firm_id=kwargs.get("firm_id"),
            template_id=kwargs.get("template_id"),
            case_id=kwargs.get("case_id"),
            template_name=kwargs.get("template_name", ""),
            case_label=kwargs.get("case_label", ""),
            template_spec=kwargs.get("template_spec"),
            bundle_picks=kwargs.get("bundle_picks"),
            bundle_role=kwargs.get("bundle_role"),
            bundle_companions=kwargs.get("bundle_companions"),
            status=kwargs.get("status", "PENDING"),
            created_at=now,
            updated_at=now,
        )
        records[tid] = rec
        return rec

    async def _get(task_id):
        return records.get(task_id)

    async def _enqueue(task_id, user_id):
        queue.append(task_id)
        return len(queue)

    async def _count_active(user_id):
        return sum(
            1
            for r in records.values()
            if r.user_id == user_id
            and r.status in ("PENDING", "RUNNING", "QUEUED", "AWAITING_INPUT", "RESUMING")
        )

    async def _queue_size(user_id):
        return len(queue)

    async def _set_cancelled(task_id):
        rec = records.get(task_id)
        if rec is None:
            return None
        rec.status = "CANCELLED"
        return rec

    async def _remove_from_queue(task_id, user_id):
        try:
            queue.remove(task_id)
            return 1
        except ValueError:
            return 0

    async def _set_user_picks(task_id, *, user_picks, bundle_picks=None):
        rec = records.get(task_id)
        if rec is None:
            return None
        rec.user_picks = user_picks
        if bundle_picks is not None:
            rec.bundle_picks = bundle_picks
        rec.status = "RESUMING"
        return rec

    async def _delete(task_id):
        return records.pop(task_id, None) is not None

    async def _list_for_user(user_id):
        return [r for r in records.values() if r.user_id == user_id]

    async def _emit(user_id, task_id, event_type):
        emitted.append((user_id, task_id, event_type))

    async def _emit_removed(user_id, task_id):
        emitted.append((user_id, task_id, "removed"))

    monkeypatch.setattr(router_mod.state, "create", _create)
    monkeypatch.setattr(router_mod.state, "get", _get)
    monkeypatch.setattr(router_mod.state, "enqueue", _enqueue)
    monkeypatch.setattr(router_mod.state, "count_active_for_user", _count_active)
    monkeypatch.setattr(router_mod.state, "queue_size", _queue_size)
    monkeypatch.setattr(router_mod.state, "set_cancelled", _set_cancelled)
    monkeypatch.setattr(router_mod.state, "remove_from_queue", _remove_from_queue)
    monkeypatch.setattr(router_mod.state, "set_user_picks", _set_user_picks)
    monkeypatch.setattr(router_mod.state, "delete", _delete)
    monkeypatch.setattr(router_mod.state, "list_for_user", _list_for_user)
    monkeypatch.setattr(router_mod.events, "emit", _emit)
    monkeypatch.setattr(router_mod.events, "emit_removed", _emit_removed)

    fake_initial_kiq = AsyncMock()
    fake_resume_kiq = AsyncMock()
    monkeypatch.setattr(router_mod.run_dry_run_initial, "kiq", fake_initial_kiq)
    monkeypatch.setattr(router_mod.run_dry_run_resume, "kiq", fake_resume_kiq)

    return {
        "records": records,
        "queue": queue,
        "emitted": emitted,
        "initial_kiq": fake_initial_kiq,
        "resume_kiq": fake_resume_kiq,
    }


@pytest.fixture(autouse=True)
def patched_repos(monkeypatch):
    """Default fixtures: template + case exist. Tests that need 404
    behavior re-patch these inline."""
    fake_template = SimpleNamespace(id="tpl", name="My Template")
    fake_case = SimpleNamespace(id="case-X", case_number="26-10700")
    monkeypatch.setattr(
        router_mod.TemplatesV2Repository,
        "get",
        AsyncMock(return_value=fake_template),
    )
    monkeypatch.setattr(
        router_mod.CaseRepository, "get", AsyncMock(return_value=fake_case),
    )


def _make_user(user_id: str = "user-1", firm_id: str | None = "firm-A"):
    return SimpleNamespace(id=user_id, firm_id=firm_id)


def _make_start_req(
    template_id: str = "tpl",
    case_id: str = "case-X",
) -> StartDryRunRequest:
    return StartDryRunRequest(
        template_id=template_id,
        case_id=case_id,
        template_spec=TemplateSpecV2(template_id=uuid.uuid4(), fields=[]),
    )


# ─── start_dry_run ────────────────────────────────────────────────────


@pytest.mark.unit
async def test_start_dry_run_returns_pending_and_kicks_initial(patched_state_and_kicks):
    fixt = patched_state_and_kicks
    user = _make_user()
    response = await router_mod.start_dry_run(req=_make_start_req(), user=user)
    assert response.status == "PENDING"
    assert response.task_id == "task-1"
    fixt["initial_kiq"].assert_awaited_once_with(task_id="task-1", user_id="user-1")
    assert ("user-1", "task-1", "status_changed") in fixt["emitted"]


@pytest.mark.unit
async def test_start_dry_run_404_when_template_missing(monkeypatch, patched_state_and_kicks):
    monkeypatch.setattr(
        router_mod.TemplatesV2Repository,
        "get",
        AsyncMock(return_value=None),
    )
    user = _make_user()
    with pytest.raises(HTTPException) as exc:
        await router_mod.start_dry_run(req=_make_start_req(), user=user)
    assert exc.value.status_code == 404
    assert "Template" in exc.value.detail


@pytest.mark.unit
async def test_start_dry_run_404_when_case_missing(monkeypatch, patched_state_and_kicks):
    monkeypatch.setattr(
        router_mod.CaseRepository, "get", AsyncMock(return_value=None),
    )
    user = _make_user()
    with pytest.raises(HTTPException) as exc:
        await router_mod.start_dry_run(req=_make_start_req(), user=user)
    assert exc.value.status_code == 404
    assert "Case" in exc.value.detail


@pytest.mark.unit
async def test_start_dry_run_queues_when_over_cap(monkeypatch, patched_state_and_kicks):
    monkeypatch.setattr(state, "MAX_CONCURRENT_DRY_RUN_TASKS", 0)
    fixt = patched_state_and_kicks
    user = _make_user()
    response = await router_mod.start_dry_run(req=_make_start_req(), user=user)
    assert response.status == "QUEUED"
    assert response.task_id in fixt["queue"]
    fixt["initial_kiq"].assert_not_called()


@pytest.mark.unit
async def test_start_dry_run_429_when_queue_full(monkeypatch, patched_state_and_kicks):
    monkeypatch.setattr(state, "MAX_CONCURRENT_DRY_RUN_TASKS", 0)
    monkeypatch.setattr(state, "MAX_QUEUED_DRY_RUN_TASKS", 0)
    user = _make_user()
    with pytest.raises(HTTPException) as exc:
        await router_mod.start_dry_run(req=_make_start_req(), user=user)
    assert exc.value.status_code == 429
    assert exc.value.detail["code"] == "QUEUE_FULL"


# ─── submit_input ─────────────────────────────────────────────────────


@pytest.mark.unit
async def test_submit_input_flips_to_resuming_and_kicks_resume(patched_state_and_kicks):
    fixt = patched_state_and_kicks
    user = _make_user()
    start = await router_mod.start_dry_run(req=_make_start_req(), user=user)
    # Manually flip status to AWAITING_INPUT to satisfy submit's gate.
    fixt["records"][start.task_id].status = "AWAITING_INPUT"

    submit = await router_mod.submit_input(
        task_id=start.task_id,
        req=SubmitInputRequest(user_picks={"creditor": SingleValuePickV2(value="Acme")}),
        user=user,
    )
    assert submit.status == "RESUMING"
    fixt["resume_kiq"].assert_awaited_once_with(
        task_id=start.task_id, user_id="user-1",
    )


@pytest.mark.unit
async def test_submit_input_409_when_not_awaiting(patched_state_and_kicks):
    fixt = patched_state_and_kicks
    user = _make_user()
    start = await router_mod.start_dry_run(req=_make_start_req(), user=user)
    # Still PENDING — submit should refuse.
    assert fixt["records"][start.task_id].status == "PENDING"
    with pytest.raises(HTTPException) as exc:
        await router_mod.submit_input(
            task_id=start.task_id,
            req=SubmitInputRequest(user_picks={}),
            user=user,
        )
    assert exc.value.status_code == 409


@pytest.mark.unit
async def test_submit_input_404_when_not_owned(patched_state_and_kicks):
    fixt = patched_state_and_kicks
    user_a = _make_user("user-A")
    user_b = _make_user("user-B")
    start = await router_mod.start_dry_run(req=_make_start_req(), user=user_a)
    with pytest.raises(HTTPException) as exc:
        await router_mod.submit_input(
            task_id=start.task_id,
            req=SubmitInputRequest(user_picks={}),
            user=user_b,
        )
    assert exc.value.status_code == 404


# ─── cancel + delete + list + get ─────────────────────────────────────


@pytest.mark.unit
async def test_cancel_task_marks_cancelled_and_emits(patched_state_and_kicks):
    fixt = patched_state_and_kicks
    user = _make_user()
    start = await router_mod.start_dry_run(req=_make_start_req(), user=user)
    cancelled = await router_mod.cancel_task(task_id=start.task_id, user=user)
    assert cancelled.status == "CANCELLED"
    assert ("user-1", start.task_id, "cancelled") in fixt["emitted"]


@pytest.mark.unit
async def test_cancel_task_noop_when_terminal(patched_state_and_kicks):
    fixt = patched_state_and_kicks
    user = _make_user()
    start = await router_mod.start_dry_run(req=_make_start_req(), user=user)
    fixt["records"][start.task_id].status = "COMPLETED"
    cancelled = await router_mod.cancel_task(task_id=start.task_id, user=user)
    assert cancelled.status == "COMPLETED"


@pytest.mark.unit
async def test_cancel_task_404_when_not_owned(patched_state_and_kicks):
    user_a = _make_user("user-A")
    user_b = _make_user("user-B")
    start = await router_mod.start_dry_run(req=_make_start_req(), user=user_a)
    with pytest.raises(HTTPException) as exc:
        await router_mod.cancel_task(task_id=start.task_id, user=user_b)
    assert exc.value.status_code == 404


@pytest.mark.unit
async def test_delete_task_removes_and_emits(patched_state_and_kicks):
    fixt = patched_state_and_kicks
    user = _make_user()
    start = await router_mod.start_dry_run(req=_make_start_req(), user=user)
    result = await router_mod.delete_task(task_id=start.task_id, user=user)
    assert result == {"removed": True, "task_id": start.task_id}
    assert ("user-1", start.task_id, "removed") in fixt["emitted"]


@pytest.mark.unit
async def test_list_user_tasks_returns_caller_records(patched_state_and_kicks):
    user = _make_user()
    r1 = await router_mod.start_dry_run(req=_make_start_req(), user=user)
    r2 = await router_mod.start_dry_run(req=_make_start_req(), user=user)
    listed = await router_mod.list_user_tasks(user=user)
    assert {t.task_id for t in listed} == {r1.task_id, r2.task_id}


@pytest.mark.unit
async def test_get_task_returns_owned(patched_state_and_kicks):
    user = _make_user()
    start = await router_mod.start_dry_run(req=_make_start_req(), user=user)
    fetched = await router_mod.get_task(task_id=start.task_id, user=user)
    assert fetched.task_id == start.task_id


@pytest.mark.unit
async def test_get_task_404_when_not_owned(patched_state_and_kicks):
    user_a = _make_user("user-A")
    user_b = _make_user("user-B")
    start = await router_mod.start_dry_run(req=_make_start_req(), user=user_a)
    with pytest.raises(HTTPException) as exc:
        await router_mod.get_task(task_id=start.task_id, user=user_b)
    assert exc.value.status_code == 404
