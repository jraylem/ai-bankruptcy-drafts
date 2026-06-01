"""Tests for CaseRepository.find_unfiled_match — the rapidfuzz-backed matcher.

The matcher is a two-step gate: SQL prefilter on (firm_id, ssn_last4,
status='unfiled'), then rapidfuzz.fuzz.WRatio over case_name with an
85% threshold. These tests stub the SQL step (the candidate list) and
exercise the scoring logic with real rapidfuzz calls so the threshold
calibration is verified against actual scores.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.core.common.storage.database.repositories import case_repository as cr_mod
from src.core.common.storage.database.repositories.case_repository import (
    CaseRepository,
    NAME_MATCH_THRESHOLD,
)


def _candidate(id: str, case_name: str) -> SimpleNamespace:
    """Build a candidate row in the shape find_unfiled_match expects.

    The repository's SQL query returns rows with .id and .case_name —
    SimpleNamespace mirrors that without dragging in real ORM."""
    return SimpleNamespace(id=id, case_name=case_name)


@pytest.fixture
def patch_session(monkeypatch):
    """Replace CaseRepository._session() so find_unfiled_match runs
    against a controllable fake. Returns a setter that installs the
    candidate list the SQL step would have returned."""
    candidates: list[SimpleNamespace] = []

    @asynccontextmanager
    async def fake_session_ctx():
        session = MagicMock()
        result = MagicMock()
        result.fetchall = MagicMock(return_value=candidates)

        async def fake_execute(stmt, params=None):
            return result

        session.execute = fake_execute
        yield session

    monkeypatch.setattr(CaseRepository, "_session", staticmethod(fake_session_ctx))

    def set_candidates(rows: list[SimpleNamespace]) -> None:
        candidates.clear()
        candidates.extend(rows)

    return set_candidates


@pytest.mark.unit
async def test_find_unfiled_match_returns_none_when_no_candidates(patch_session):
    """SSN prefilter returned no rows — no fuzzy scoring even attempted."""
    patch_session([])

    result = await CaseRepository.find_unfiled_match(
        firm_id="firm-1", ssn_last4="1879", case_name="Jane Doe",
    )
    assert result is None


@pytest.mark.unit
async def test_find_unfiled_match_returns_id_for_exact_name_match(patch_session):
    """Identical case_name → score=100, well above 85 threshold."""
    patch_session([_candidate("case-uuid-1", "Jane Doe")])

    result = await CaseRepository.find_unfiled_match(
        firm_id="firm-1", ssn_last4="1879", case_name="Jane Doe",
    )
    assert result == "case-uuid-1"


@pytest.mark.unit
async def test_find_unfiled_match_tolerates_middle_name_expansion(patch_session):
    """WRatio handles 'Jane Q Debtor' ↔ 'Jane Quentin Debtor' (~87) above 85%."""
    patch_session([_candidate("case-uuid-1", "Jane Quentin Debtor")])

    result = await CaseRepository.find_unfiled_match(
        firm_id="firm-1", ssn_last4="1879", case_name="Jane Q Debtor",
    )
    assert result == "case-uuid-1"


@pytest.mark.unit
async def test_find_unfiled_match_tolerates_middle_initial_addition(patch_session):
    """'Robert Smith' ↔ 'Robert J Smith' scores ~95 — comfortably above threshold."""
    patch_session([_candidate("case-uuid-1", "Robert J Smith")])

    result = await CaseRepository.find_unfiled_match(
        firm_id="firm-1", ssn_last4="1879", case_name="Robert Smith",
    )
    assert result == "case-uuid-1"


@pytest.mark.unit
async def test_find_unfiled_match_rejects_different_person(patch_session):
    """Same SSN (false positive in real life) but clearly different person —
    must reject under the 85% threshold so the matcher doesn't merge them."""
    patch_session([_candidate("case-uuid-1", "Robert J Smith")])

    result = await CaseRepository.find_unfiled_match(
        firm_id="firm-1", ssn_last4="1879", case_name="Jane Doe",
    )
    assert result is None


@pytest.mark.unit
async def test_find_unfiled_match_returns_highest_scoring_candidate(patch_session):
    """When SSN prefilter returns multiple, the highest-scoring one wins."""
    patch_session([
        _candidate("case-low", "Robert J Smith"),
        _candidate("case-high", "Jane Q Debtor"),
        _candidate("case-mid", "Jane Smith"),
    ])

    result = await CaseRepository.find_unfiled_match(
        firm_id="firm-1", ssn_last4="1879", case_name="Jane Q Debtor",
    )
    assert result == "case-high"


@pytest.mark.unit
async def test_find_unfiled_match_logs_warning_on_near_tie(patch_session, caplog):
    """Two candidates within NAME_TIE_BAND — ops needs to know.

    'Janet Q Debtor' scores 96.3 vs 'Jane Q Debtor', and 'Jane R Debtor'
    scores 92.3 vs 'Jane Q Debtor' — gap of 4, inside the 5-point band.
    """
    import logging
    caplog.set_level(logging.WARNING, logger=cr_mod.__name__)

    patch_session([
        _candidate("case-a", "Janet Q Debtor"),
        _candidate("case-b", "Jane R Debtor"),
    ])

    await CaseRepository.find_unfiled_match(
        firm_id="firm-1", ssn_last4="1879", case_name="Jane Q Debtor",
    )
    assert any("near-tie" in r.message for r in caplog.records)


@pytest.mark.unit
async def test_find_unfiled_match_handles_null_case_name_candidate(patch_session):
    """Defensive: a candidate row with case_name=NULL must not blow up the
    rapidfuzz call (it'd raise TypeError on None comparison)."""
    patch_session([_candidate("case-with-null", None)])

    result = await CaseRepository.find_unfiled_match(
        firm_id="firm-1", ssn_last4="1879", case_name="Jane Doe",
    )
    # NULL candidate scores 0 vs anything → below 85 threshold → None
    assert result is None


@pytest.mark.unit
def test_name_match_threshold_is_conservative():
    """Sanity-check the tuned constant. If someone drops this below ~70
    the matcher becomes a false-positive machine for similar surnames."""
    assert NAME_MATCH_THRESHOLD >= 80
