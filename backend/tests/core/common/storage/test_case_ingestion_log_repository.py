"""CaseIngestionLogRepository — record() swallows; cycle_summary aggregates."""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.core.common.storage.database.repositories.case_ingestion_log_repository import (
    ALL_OUTCOMES,
    CaseIngestionLogRepository,
)


class _FakeResult:
    def __init__(self, rows=None):
        self._rows = rows or []

    def all(self):
        return [SimpleNamespace(__iter__=lambda self: iter(r)) for r in self._rows]

    def scalars(self):
        return self

    def fetchall(self):
        return [SimpleNamespace(_mapping=r) for r in self._rows]


class _FakeSession:
    def __init__(self):
        self.added = []
        self.committed = 0
        self.executes: list[tuple] = []

    def add(self, instance):
        self.added.append(instance)

    async def commit(self):
        self.committed += 1

    async def execute(self, *args, **kwargs):
        self.executes.append((args, kwargs))
        return _FakeResult([])


def _install_fake_session(monkeypatch, fake: _FakeSession) -> None:
    @asynccontextmanager
    async def fake_ctx():
        yield fake

    monkeypatch.setattr(
        "src.core.common.storage.database.repositories.case_ingestion_log_repository."
        "BaseRepository._session",
        staticmethod(fake_ctx),
    )


# ─── record() ─────────────────────────────────────────────────────────


@pytest.mark.unit
async def test_record_inserts_row_with_outcome_fields(monkeypatch):
    fake = _FakeSession()
    _install_fake_session(monkeypatch, fake)

    await CaseIngestionLogRepository.record(
        firm_id="firm-1",
        cycle_id="cycle-uuid",
        gmail_message_id="msg-abc",
        case_number="8:26-bk-01330",
        case_name="Jane Q Debtor",
        court_district="FLSB",
        outcome="inserted",
        case_inbox_id="inbox-uuid",
        pdf_size_bytes=12345,
        elapsed_ms=480,
    )

    assert len(fake.added) == 1
    row = fake.added[0]
    assert row.firm_id == "firm-1"
    assert row.cycle_id == "cycle-uuid"
    assert row.gmail_message_id == "msg-abc"
    assert row.outcome == "inserted"
    assert row.case_inbox_id == "inbox-uuid"
    assert row.pdf_size_bytes == 12345
    assert row.elapsed_ms == 480
    assert fake.committed == 1


@pytest.mark.unit
async def test_record_swallows_db_exception(monkeypatch):
    """Observability code must NEVER raise into the cron loop."""
    @asynccontextmanager
    async def boom():
        raise RuntimeError("postgres unreachable")
        yield  # unreachable

    monkeypatch.setattr(
        "src.core.common.storage.database.repositories.case_ingestion_log_repository."
        "BaseRepository._session",
        staticmethod(boom),
    )
    # Should NOT raise.
    await CaseIngestionLogRepository.record(
        firm_id="firm-1", outcome="dead_link", error_message="link expired",
    )


@pytest.mark.unit
async def test_record_truncates_huge_error_message(monkeypatch):
    """Defensive: a multi-MB Python traceback shouldn't blow up the row."""
    fake = _FakeSession()
    _install_fake_session(monkeypatch, fake)

    big_err = "X" * 10_000
    await CaseIngestionLogRepository.record(
        firm_id="firm-1", outcome="r2_upload_failed", error_message=big_err,
    )
    assert len(fake.added[0].error_message) == 4000


# ─── canonical vocabulary ──────────────────────────────────────────────


@pytest.mark.unit
def test_all_outcomes_vocabulary():
    """Wire contract: any code branch in run_ingest_cycle must produce
    one of these strings. Updating this set requires updating the ingest
    code + admin queries together."""
    assert ALL_OUTCOMES == (
        "inserted",
        "gmail_dedup_skip",
        "fingerprint_dedup_skip",
        "dead_link",
        "r2_upload_failed",
        "db_insert_failed",
        "parse_error",
    )
