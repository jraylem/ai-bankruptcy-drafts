"""Tests for _derive_short_code and _ensure_unique_short_code."""

from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from src.core.common.storage.database import ReferenceDataRepository
from src.core.components.reference_data.service import (
    _derive_short_code,
    _ensure_unique_short_code,
)


# ─── _derive_short_code ───────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.parametrize(
    "name, expected",
    [
        ("Firm Phone", "FIRM_PHONE"),
        ("firm phone", "FIRM_PHONE"),               # case normalized
        ("Firm Phone #1", "FIRM_PHONE_1"),          # non-alnum collapsed
        ("Réferénce", "REFERENCE"),                 # ASCII-folded
        ("  leading-trailing  ", "LEADING_TRAILING"),
        ("Multi___Underscores", "MULTI_UNDERSCORES"),
    ],
)
def test_derive_short_code_happy_paths(name, expected):
    assert _derive_short_code(name) == expected


@pytest.mark.unit
@pytest.mark.parametrize("bad", ["   ", "@#$", "—", ""])
def test_derive_short_code_rejects_unusable_inputs(bad):
    with pytest.raises(HTTPException) as exc:
        _derive_short_code(bad)
    assert exc.value.status_code == 400
    assert "Could not derive a short_code" in exc.value.detail


# ─── _ensure_unique_short_code ────────────────────────────────────────


@pytest.mark.unit
async def test_unique_when_no_collision(monkeypatch):
    """No existing row with this short_code → return candidate unchanged."""
    monkeypatch.setattr(ReferenceDataRepository, "get", AsyncMock(return_value=None))

    result = await _ensure_unique_short_code("FIRM_PHONE")

    assert result == "FIRM_PHONE"


@pytest.mark.unit
async def test_unique_suffixes_on_first_collision(monkeypatch):
    """Candidate exists, candidate_2 doesn't → use candidate_2."""
    existing = {"FIRM_PHONE"}

    async def fake_get(short_code: str):
        return object() if short_code in existing else None

    monkeypatch.setattr(ReferenceDataRepository, "get", fake_get)

    result = await _ensure_unique_short_code("FIRM_PHONE")

    assert result == "FIRM_PHONE_2"


@pytest.mark.unit
async def test_unique_suffixes_through_multiple_collisions(monkeypatch):
    """Both candidate and candidate_2 exist → use candidate_3."""
    existing = {"FIRM_PHONE", "FIRM_PHONE_2"}

    async def fake_get(short_code: str):
        return object() if short_code in existing else None

    monkeypatch.setattr(ReferenceDataRepository, "get", fake_get)

    result = await _ensure_unique_short_code("FIRM_PHONE")

    assert result == "FIRM_PHONE_3"


@pytest.mark.unit
async def test_unique_lookup_called_with_suffix_candidates(monkeypatch):
    """Sanity: we hit the repo with the expected candidate names in order."""
    queried: list[str] = []
    existing = {"FIRM_PHONE"}

    async def fake_get(short_code: str):
        queried.append(short_code)
        return object() if short_code in existing else None

    monkeypatch.setattr(ReferenceDataRepository, "get", fake_get)

    result = await _ensure_unique_short_code("FIRM_PHONE")

    assert result == "FIRM_PHONE_2"
    assert queried == ["FIRM_PHONE", "FIRM_PHONE_2"]
