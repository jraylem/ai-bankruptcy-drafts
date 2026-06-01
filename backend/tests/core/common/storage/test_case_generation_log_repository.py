"""Direct tests for `CaseGenerationLogRepository.list_for_case_all_users`.

The cross-user variant is what the chat agent's `list_drafted_motions`
tool calls. We pin its SQL shape + return-mapping with a fake session
boundary (no real Postgres) since the repo module has no other tests
asserting that contract.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from src.core.common.storage.database.repositories.case_generation_log_repository import (
    CaseGenerationLogRepository,
)


class _FakeResult:
    def __init__(self, rows: list[dict] | None = None):
        self._rows = rows or []

    def fetchall(self):
        return [SimpleNamespace(_mapping=r) for r in self._rows]


class _FakeSession:
    def __init__(self, scripted: list[_FakeResult]):
        self._scripted = list(scripted)
        self.executes: list[tuple[str, dict]] = []

    async def execute(self, stmt, params=None):
        self.executes.append((str(stmt), params or {}))
        return self._scripted.pop(0) if self._scripted else _FakeResult()

    async def commit(self):
        pass

    async def rollback(self):
        pass


def _install_fake_session(monkeypatch, fake: _FakeSession) -> None:
    @asynccontextmanager
    async def fake_ctx():
        yield fake

    monkeypatch.setattr(
        "src.core.common.storage.database.repositories.case_generation_log_repository."
        "BaseRepository._session",
        staticmethod(fake_ctx),
    )


def _row(
    *,
    id: str,
    user_id: str,
    case_id: str = "26_10700",
    draft_template_id: str = "t1",
    template_name: str = "Motion to Extend Stay",
    status: str = "COMPLETED",
    task_id: str | None = None,
    r2_object_key: str | None = None,
    children: list | None = None,
    error: str | None = None,
    created_at=None,
    updated_at=None,
):
    return {
        "id": id,
        "user_id": user_id,
        "case_id": case_id,
        "draft_template_id": draft_template_id,
        "template_name": template_name,
        "status": status,
        "task_id": task_id,
        "r2_object_key": r2_object_key,
        "children": children,
        "error": error,
        "created_at": created_at,
        "updated_at": updated_at,
    }


# ─── list_for_case_all_users ──────────────────────────────────────────


@pytest.mark.unit
async def test_returns_logs_from_multiple_users_for_same_case(monkeypatch):
    rows = [
        _row(id="log-a", user_id="alice", template_name="Motion to Extend Stay"),
        _row(id="log-b", user_id="bob",   template_name="Motion to Modify Plan"),
    ]
    fake = _FakeSession([_FakeResult(rows=rows)])
    _install_fake_session(monkeypatch, fake)

    logs = await CaseGenerationLogRepository.list_for_case_all_users(
        case_id="26_10700", limit=50,
    )

    assert {l.user_id for l in logs} == {"alice", "bob"}
    assert {l.template_name for l in logs} == {
        "Motion to Extend Stay",
        "Motion to Modify Plan",
    }

    # WHERE clause is case-scoped only — no user_id binding.
    stmt, params = fake.executes[0]
    assert "WHERE case_id = :case_id" in stmt
    assert "user_id" not in stmt  # critical: the cross-user variant
    assert params["case_id"] == "26_10700"
    assert params["limit"] == 50


@pytest.mark.unit
async def test_empty_when_case_has_no_logs(monkeypatch):
    fake = _FakeSession([_FakeResult(rows=[])])
    _install_fake_session(monkeypatch, fake)

    logs = await CaseGenerationLogRepository.list_for_case_all_users(
        case_id="nonexistent_case",
    )
    assert logs == []


@pytest.mark.unit
async def test_passes_default_limit_when_not_provided(monkeypatch):
    fake = _FakeSession([_FakeResult(rows=[])])
    _install_fake_session(monkeypatch, fake)

    await CaseGenerationLogRepository.list_for_case_all_users(
        case_id="26_10700",
    )
    _, params = fake.executes[0]
    assert params["limit"] == 100  # default per the method signature
