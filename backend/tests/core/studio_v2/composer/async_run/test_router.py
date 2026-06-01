"""Tests for the v2 composer-async router.

We call the route handlers directly as async functions (passing a
mock User + UploadFile) so we don't have to wrestle with FastAPI's
TestClient + auth dependency injection. The route logic is what we
care about — queue caps, dedup, status flips, event emissions.
"""

from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException, UploadFile

from src.core.studio_v2.composer.async_run import router as router_mod
from src.core.studio_v2.composer.async_run import state
from src.core.studio_v2.composer.async_run.schemas import (
    StartRegenerateRequest,
    V2ComposerTaskRecord,
)


@pytest.fixture(autouse=True)
def patched_state_and_kicks(monkeypatch):
    """Stub state + the worker `.kiq()` calls so route handlers don't
    actually enqueue Taskiq messages."""
    records: dict[str, V2ComposerTaskRecord] = {}
    queue: list[str] = []
    emitted: list[tuple[str, str, str]] = []
    blobs: dict[str, bytes] = {}
    kicks: list[tuple[str, str]] = []  # (kind, task_id)

    next_task_id = {"i": 0}

    async def _create(**kwargs):
        next_task_id["i"] += 1
        tid = f"task-{next_task_id['i']}"
        now = datetime.now(timezone.utc)
        rec = V2ComposerTaskRecord(
            task_id=tid,
            user_id=kwargs.get("user_id"),
            firm_id=kwargs.get("firm_id"),
            kind=kwargs.get("kind"),
            template_name=kwargs.get("template_name", ""),
            template_id=kwargs.get("template_id"),
            template_role=kwargs.get("template_role", "single"),
            original_filename=kwargs.get("original_filename", ""),
            ignored_texts=kwargs.get("ignored_texts"),
            merges=kwargs.get("merges"),
            regeneration_instruction=kwargs.get("regeneration_instruction"),
            upload_blob_key=kwargs.get("upload_blob_key"),
            status=kwargs.get("status", "PENDING"),
            created_at=now, updated_at=now,
        )
        records[tid] = rec
        return rec

    async def _get(task_id):
        return records.get(task_id)

    async def _stage(content):
        blobs[f"blob-{len(blobs)}"] = content
        return f"blob-{len(blobs)-1}"

    async def _enqueue(task_id, user_id):
        queue.append(task_id)
        return len(queue)

    async def _count_active(user_id):
        return sum(1 for r in records.values() if r.user_id == user_id and r.status in ("PENDING", "RUNNING", "QUEUED"))

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
    monkeypatch.setattr(router_mod.state, "stage_upload_blob", _stage)
    monkeypatch.setattr(router_mod.state, "enqueue", _enqueue)
    monkeypatch.setattr(router_mod.state, "count_active_for_user", _count_active)
    monkeypatch.setattr(router_mod.state, "queue_size", _queue_size)
    monkeypatch.setattr(router_mod.state, "set_cancelled", _set_cancelled)
    monkeypatch.setattr(router_mod.state, "remove_from_queue", _remove_from_queue)
    monkeypatch.setattr(router_mod.state, "delete", _delete)
    monkeypatch.setattr(router_mod.state, "list_for_user", _list_for_user)
    monkeypatch.setattr(router_mod.events, "emit", _emit)
    monkeypatch.setattr(router_mod.events, "emit_removed", _emit_removed)

    # Worker-kick stubs — record but don't dispatch.
    fake_generate_kiq = AsyncMock()
    fake_regenerate_kiq = AsyncMock()
    monkeypatch.setattr(router_mod.run_composer_generate, "kiq", fake_generate_kiq)
    monkeypatch.setattr(router_mod.run_composer_regenerate, "kiq", fake_regenerate_kiq)

    return {
        "records": records,
        "queue": queue,
        "emitted": emitted,
        "blobs": blobs,
        "generate_kiq": fake_generate_kiq,
        "regenerate_kiq": fake_regenerate_kiq,
    }


def _make_user(user_id: str = "user-1", firm_id: str | None = "firm-A"):
    return SimpleNamespace(id=user_id, firm_id=firm_id)


def _make_upload(content: bytes = b"docx-bytes", filename: str = "x.docx") -> UploadFile:
    return UploadFile(filename=filename, file=BytesIO(content))


# ─── start_generate ────────────────────────────────────────────────────


@pytest.mark.unit
async def test_start_generate_returns_202_and_kicks_worker(patched_state_and_kicks):
    fixt = patched_state_and_kicks
    user = _make_user()
    response = await router_mod.start_generate(
        user=user,
        file=_make_upload(),
        template_name="My Template",
        template_role="single",
    )
    assert response.status == "PENDING"
    assert response.task_id == "task-1"
    fixt["generate_kiq"].assert_awaited_once_with(task_id="task-1", user_id="user-1")
    # status_changed event fires immediately
    assert ("user-1", "task-1", "status_changed") in fixt["emitted"]


@pytest.mark.unit
async def test_start_generate_rejects_invalid_role(patched_state_and_kicks):
    user = _make_user()
    with pytest.raises(HTTPException) as exc:
        await router_mod.start_generate(
            user=user,
            file=_make_upload(),
            template_name="t",
            template_role="banana",
        )
    assert exc.value.status_code == 400


@pytest.mark.unit
async def test_start_generate_rejects_empty_upload(patched_state_and_kicks):
    user = _make_user()
    with pytest.raises(HTTPException) as exc:
        await router_mod.start_generate(
            user=user,
            file=_make_upload(content=b""),
            template_name="t",
        )
    assert exc.value.status_code == 400


@pytest.mark.unit
async def test_start_generate_queues_when_over_concurrent_cap(monkeypatch, patched_state_and_kicks):
    monkeypatch.setattr(state, "MAX_CONCURRENT_COMPOSER_TASKS", 0)
    fixt = patched_state_and_kicks
    user = _make_user()
    response = await router_mod.start_generate(
        user=user,
        file=_make_upload(),
        template_name="t",
    )
    assert response.status == "QUEUED"
    assert response.task_id in fixt["queue"]
    # Worker NOT kicked when queued.
    fixt["generate_kiq"].assert_not_called()


@pytest.mark.unit
async def test_start_generate_429_when_queue_full(monkeypatch, patched_state_and_kicks):
    monkeypatch.setattr(state, "MAX_CONCURRENT_COMPOSER_TASKS", 0)
    monkeypatch.setattr(state, "MAX_QUEUED_COMPOSER_TASKS", 0)
    user = _make_user()
    with pytest.raises(HTTPException) as exc:
        await router_mod.start_generate(
            user=user,
            file=_make_upload(),
            template_name="t",
        )
    assert exc.value.status_code == 429
    assert exc.value.detail["code"] == "QUEUE_FULL"


# ─── start_regenerate ─────────────────────────────────────────────────


@pytest.mark.unit
async def test_start_regenerate_returns_202_and_kicks(patched_state_and_kicks):
    fixt = patched_state_and_kicks
    user = _make_user()
    with patch.object(router_mod.TemplatesV2Repository, "get", new=AsyncMock(
        return_value=SimpleNamespace(template_id="tpl-X", name="My Tmpl"),
    )):
        response = await router_mod.start_regenerate(
            req=StartRegenerateRequest(template_id="tpl-X"),
            user=user,
        )
    assert response.status == "PENDING"
    fixt["regenerate_kiq"].assert_awaited_once_with(
        task_id=response.task_id, user_id="user-1",
    )


@pytest.mark.unit
async def test_start_regenerate_404_when_template_missing(patched_state_and_kicks):
    user = _make_user()
    with patch.object(router_mod.TemplatesV2Repository, "get", new=AsyncMock(return_value=None)):
        with pytest.raises(HTTPException) as exc:
            await router_mod.start_regenerate(
                req=StartRegenerateRequest(template_id="missing"),
                user=user,
            )
    assert exc.value.status_code == 404


# ─── cancel + delete + list + get ─────────────────────────────────────


@pytest.mark.unit
async def test_cancel_task_marks_cancelled_and_emits(patched_state_and_kicks):
    fixt = patched_state_and_kicks
    user = _make_user()
    response = await router_mod.start_generate(
        user=user,
        file=_make_upload(),
        template_name="t",
    )
    cancelled = await router_mod.cancel_task(task_id=response.task_id, user=user)
    assert cancelled.status == "CANCELLED"
    assert ("user-1", response.task_id, "cancelled") in fixt["emitted"]


@pytest.mark.unit
async def test_cancel_task_is_noop_when_terminal(patched_state_and_kicks):
    fixt = patched_state_and_kicks
    user = _make_user()
    response = await router_mod.start_generate(
        user=user,
        file=_make_upload(),
        template_name="t",
    )
    fixt["records"][response.task_id].status = "COMPLETED"
    cancelled = await router_mod.cancel_task(task_id=response.task_id, user=user)
    assert cancelled.status == "COMPLETED"  # untouched


@pytest.mark.unit
async def test_cancel_task_404_when_not_owned(patched_state_and_kicks):
    fixt = patched_state_and_kicks
    user_a = _make_user("user-A")
    user_b = _make_user("user-B")
    response = await router_mod.start_generate(
        user=user_a,
        file=_make_upload(),
        template_name="t",
    )
    with pytest.raises(HTTPException) as exc:
        await router_mod.cancel_task(task_id=response.task_id, user=user_b)
    assert exc.value.status_code == 404


@pytest.mark.unit
async def test_delete_task_removes_and_emits(patched_state_and_kicks):
    fixt = patched_state_and_kicks
    user = _make_user()
    response = await router_mod.start_generate(
        user=user,
        file=_make_upload(),
        template_name="t",
    )
    result = await router_mod.delete_task(task_id=response.task_id, user=user)
    assert result == {"removed": True, "task_id": response.task_id}
    assert ("user-1", response.task_id, "removed") in fixt["emitted"]


@pytest.mark.unit
async def test_list_user_tasks_returns_caller_records(patched_state_and_kicks):
    user = _make_user()
    r1 = await router_mod.start_generate(user=user, file=_make_upload(), template_name="t1")
    r2 = await router_mod.start_generate(user=user, file=_make_upload(), template_name="t2")
    listed = await router_mod.list_user_tasks(user=user)
    assert {t.task_id for t in listed} == {r1.task_id, r2.task_id}


@pytest.mark.unit
async def test_get_task_returns_owned(patched_state_and_kicks):
    user = _make_user()
    response = await router_mod.start_generate(
        user=user,
        file=_make_upload(),
        template_name="t",
    )
    fetched = await router_mod.get_task(task_id=response.task_id, user=user)
    assert fetched.task_id == response.task_id
