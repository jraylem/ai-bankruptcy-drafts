"""Tests for the ATTORNEYS guard in _handle_constants.

The reserved ATTORNEYS reference_data row holds structured JSON (the
attorney roster) — returning its raw value via the generic CONSTANTS
handler would leak JSON into drafts. _handle_constants must short-
circuit to None (and NOT hit the DB) for reserved structured short_codes.
"""

from unittest.mock import AsyncMock

import pytest

from src.core.agents.context import _handle_constants
from src.core.agents.types.sources import ConstantsSourceParams, FieldSource
from src.core.common.storage.database import ReferenceDataRepository
from tests.core.factories import make_template_field


@pytest.mark.unit
async def test_handle_constants_short_circuits_on_attorneys_short_code(monkeypatch):
    repo_get = AsyncMock()
    monkeypatch.setattr(ReferenceDataRepository, "get", repo_get)

    field = make_template_field(
        source=FieldSource.CONSTANTS,
        source_params=ConstantsSourceParams(short_code="ATTORNEYS"),
    )

    result = await _handle_constants(field, _ctx=None)

    assert result is None
    repo_get.assert_not_called()  # structured guard short-circuits before DB fetch


@pytest.mark.unit
async def test_handle_constants_still_fetches_for_normal_short_code(monkeypatch):
    class _FakeRef:
        value = "Van Horn Law Group, P.A."

    repo_get = AsyncMock(return_value=_FakeRef())
    monkeypatch.setattr(ReferenceDataRepository, "get", repo_get)

    field = make_template_field(
        source=FieldSource.CONSTANTS,
        source_params=ConstantsSourceParams(short_code="FIRM_NAME"),
    )

    result = await _handle_constants(field, _ctx=None)

    assert result == "Van Horn Law Group, P.A."
    repo_get.assert_awaited_once_with("FIRM_NAME")
