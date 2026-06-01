"""Direct tests for the chat repositories — mocked session boundary.

These verify the right SQL is built / the right path is taken on race
conditions. We don't reach a real Postgres; the session helper is
swapped for a programmable fake.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.core.common.storage.database.repositories.case_session_message_repository import (
    CaseSessionMessageRepository,
)
from src.core.common.storage.database.repositories.case_session_repository import (
    CaseSessionRepository,
)


class _FakeResult:
    """Mimic the parts of `Result`/`Row` the repos consume."""

    def __init__(self, rows: list[dict] | None = None, scalar: int | None = None):
        self._rows = rows or []
        self._scalar = scalar

    def fetchone(self):
        if not self._rows:
            return None
        return SimpleNamespace(_mapping=self._rows[0])

    def fetchall(self):
        return [SimpleNamespace(_mapping=r) for r in self._rows]

    def scalar(self):
        return self._scalar


class _FakeSession:
    """Records every `execute` and replays scripted results."""

    def __init__(self, scripted_results: list[_FakeResult]):
        self._scripted = list(scripted_results)
        self.executes: list[tuple[str, dict]] = []
        self.committed = 0
        self.rolled_back = 0

    async def execute(self, stmt, params=None):
        self.executes.append((str(stmt), params or {}))
        if not self._scripted:
            return _FakeResult()
        return self._scripted.pop(0)

    async def commit(self):
        self.committed += 1

    async def rollback(self):
        self.rolled_back += 1


def _install_fake_session(monkeypatch, target_module: str, fake: _FakeSession):
    @asynccontextmanager
    async def fake_ctx():
        yield fake

    monkeypatch.setattr(
        f"{target_module}.BaseRepository._session",
        staticmethod(fake_ctx),
    )


# ─── CaseSessionRepository ────────────────────────────────────────────


@pytest.mark.unit
async def test_get_or_create_returns_existing_when_present(monkeypatch):
    existing_row = {
        "id": "sess-x",
        "case_id": "26_10700",
        "user_id": "user-1",
        "title": "Chat",
        "created_at": None,
        "updated_at": None,
        "is_active": True,
    }
    fake = _FakeSession([_FakeResult(rows=[existing_row])])
    _install_fake_session(
        monkeypatch,
        "src.core.common.storage.database.repositories.case_session_repository",
        fake,
    )
    session, created = await CaseSessionRepository.get_or_create(
        user_id="user-1", case_id="26_10700",
    )
    assert session.id == "sess-x"
    # Existing row → created flag is False so callers can skip the
    # cold-path `list_by_session` lookup.
    assert created is False
    # No INSERT issued when row already existed.
    assert all("INSERT" not in stmt for stmt, _ in fake.executes)


@pytest.mark.unit
async def test_get_or_create_inserts_when_missing(monkeypatch):
    new_row = {
        "id": "freshly-inserted",
        "case_id": "26_10700",
        "user_id": "user-1",
        "title": "Chat",
        "created_at": None,
        "updated_at": None,
        "is_active": True,
    }
    fake = _FakeSession([
        _FakeResult(rows=[]),               # initial SELECT — nothing
        _FakeResult(rows=[]),               # INSERT execute
        _FakeResult(rows=[new_row]),        # post-insert SELECT
    ])
    _install_fake_session(
        monkeypatch,
        "src.core.common.storage.database.repositories.case_session_repository",
        fake,
    )
    session, created = await CaseSessionRepository.get_or_create(
        user_id="user-1", case_id="26_10700",
    )
    assert session.id == "freshly-inserted"
    # INSERT succeeded with no IntegrityError → created=True. Callers
    # use this flag to skip the wasted cold-path `list_by_session` lookup.
    assert created is True
    insert_stmts = [stmt for stmt, _ in fake.executes if "INSERT INTO case_sessions" in stmt]
    assert insert_stmts
    # is_active = TRUE must be explicit on the INSERT so the row is
    # visible to the `WHERE is_active = true` filter on every read path
    # and counts toward the partial unique index.
    assert "is_active" in insert_stmts[0]
    assert "TRUE" in insert_stmts[0]


@pytest.mark.unit
async def test_get_returns_none_for_missing(monkeypatch):
    fake = _FakeSession([_FakeResult(rows=[])])
    _install_fake_session(
        monkeypatch,
        "src.core.common.storage.database.repositories.case_session_repository",
        fake,
    )
    out = await CaseSessionRepository.get("nope")
    assert out is None


@pytest.mark.unit
async def test_get_returns_session_when_present(monkeypatch):
    row = {
        "id": "sess-1",
        "case_id": "26_10700",
        "user_id": "user-1",
        "title": "Chat",
        "created_at": None,
        "updated_at": None,
        "is_active": True,
    }
    fake = _FakeSession([_FakeResult(rows=[row])])
    _install_fake_session(
        monkeypatch,
        "src.core.common.storage.database.repositories.case_session_repository",
        fake,
    )
    out = await CaseSessionRepository.get("sess-1")
    assert out is not None and out.id == "sess-1"


@pytest.mark.unit
async def test_update_title_calls_update_then_get(monkeypatch):
    row = {
        "id": "sess-1",
        "case_id": "26_10700",
        "user_id": "user-1",
        "title": "Renamed",
        "created_at": None,
        "updated_at": None,
        "is_active": True,
    }
    fake = _FakeSession([
        _FakeResult(rows=[]),      # UPDATE
        _FakeResult(rows=[row]),  # get() SELECT
    ])
    _install_fake_session(
        monkeypatch,
        "src.core.common.storage.database.repositories.case_session_repository",
        fake,
    )
    out = await CaseSessionRepository.update_title("sess-1", "Renamed")
    assert out is not None
    assert out.title == "Renamed"
    assert any("UPDATE case_sessions SET title" in stmt for stmt, _ in fake.executes)


@pytest.mark.unit
async def test_soft_delete_issues_update(monkeypatch):
    fake = _FakeSession([_FakeResult(rows=[])])
    _install_fake_session(
        monkeypatch,
        "src.core.common.storage.database.repositories.case_session_repository",
        fake,
    )
    ok = await CaseSessionRepository.soft_delete("sess-1")
    assert ok is True
    assert any("is_active = false" in stmt for stmt, _ in fake.executes)


# ─── CaseSessionMessageRepository ────────────────────────────────────


@pytest.mark.unit
async def test_append_assigns_monotonic_sequence_and_returns_row(monkeypatch):
    new_row = {
        "id": "abc",
        "case_session_id": "sess-1",
        "sequence_number": 7,
        "role": "user",
        "content": "hi",
        "thinking": None,
        "tool_calls": None,
        "tool_call_id": None,
        "created_at": None,
        "is_active": True,
    }
    fake = _FakeSession([
        _FakeResult(scalar=7),       # MAX(seq)+1 = 7
        _FakeResult(rows=[]),        # INSERT
        _FakeResult(rows=[]),        # UPDATE case_sessions.updated_at
        _FakeResult(rows=[new_row]),  # post-insert SELECT
    ])
    _install_fake_session(
        monkeypatch,
        "src.core.common.storage.database.repositories.case_session_message_repository",
        fake,
    )

    out = await CaseSessionMessageRepository.append(
        case_session_id="sess-1", role="user", content="hi",
    )
    assert out.sequence_number == 7
    assert fake.committed == 1
    # Message rows must also persist as is_active = TRUE so future
    # is_active-aware filters don't drop them.
    insert_stmts = [
        stmt for stmt, _ in fake.executes
        if "INSERT INTO case_session_messages" in stmt
    ]
    assert insert_stmts
    assert "is_active" in insert_stmts[0]
    assert "TRUE" in insert_stmts[0]


@pytest.mark.unit
async def test_append_serializes_tool_calls_to_jsonb(monkeypatch):
    fake = _FakeSession([
        _FakeResult(scalar=1),
        _FakeResult(rows=[]),
        _FakeResult(rows=[]),
        _FakeResult(rows=[{
            "id": "abc", "case_session_id": "s", "sequence_number": 1,
            "role": "assistant", "content": "", "thinking": None,
            "tool_calls": None, "tool_call_id": None, "created_at": None, "is_active": True,
        }]),
    ])
    _install_fake_session(
        monkeypatch,
        "src.core.common.storage.database.repositories.case_session_message_repository",
        fake,
    )
    await CaseSessionMessageRepository.append(
        case_session_id="s", role="assistant", content="",
        tool_calls=[{"id": "c1", "name": "case_vector_search", "input": {"q": "x"}}],
    )
    # Find the INSERT execute and confirm tool_calls is JSON-serialized.
    insert_calls = [params for stmt, params in fake.executes if "INSERT INTO case_session_messages" in stmt]
    assert insert_calls
    tool_calls_json = insert_calls[0]["tool_calls"]
    assert isinstance(tool_calls_json, str)
    parsed = json.loads(tool_calls_json)
    assert parsed[0]["name"] == "case_vector_search"


@pytest.mark.unit
async def test_append_rejects_invalid_role():
    with pytest.raises(ValueError):
        await CaseSessionMessageRepository.append(
            case_session_id="s", role="moderator", content="x",
        )


@pytest.mark.unit
async def test_list_by_session_returns_ordered_rows(monkeypatch):
    rows = [
        {
            "id": "m1", "case_session_id": "s", "sequence_number": 1,
            "role": "user", "content": "hi", "thinking": None,
            "tool_calls": None, "tool_call_id": None, "created_at": None,
            "is_active": True,
        },
        {
            "id": "m2", "case_session_id": "s", "sequence_number": 2,
            "role": "assistant", "content": "hello", "thinking": None,
            "tool_calls": None, "tool_call_id": None, "created_at": None,
            "is_active": True,
        },
    ]
    fake = _FakeSession([_FakeResult(rows=rows)])
    _install_fake_session(
        monkeypatch,
        "src.core.common.storage.database.repositories.case_session_message_repository",
        fake,
    )
    out = await CaseSessionMessageRepository.list_by_session(case_session_id="s")
    assert [m.id for m in out] == ["m1", "m2"]


@pytest.mark.unit
async def test_list_by_session_with_before_sequence_uses_paged_query(monkeypatch):
    fake = _FakeSession([_FakeResult(rows=[])])
    _install_fake_session(
        monkeypatch,
        "src.core.common.storage.database.repositories.case_session_message_repository",
        fake,
    )
    await CaseSessionMessageRepository.list_by_session(
        case_session_id="s", limit=10, before_sequence=42,
    )
    stmt = fake.executes[0][0]
    params = fake.executes[0][1]
    assert "sequence_number < :before" in stmt
    assert params["before"] == 42
