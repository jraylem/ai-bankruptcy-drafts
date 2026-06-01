"""Tests for the 7 v2 pending-envelope types."""

import pytest
from pydantic import TypeAdapter, ValidationError

from src.core.studio_v2.types.pending import (
    AttorneyRow,
    PendingAttorneyPickV2,
    PendingAuthorDateV2,
    PendingAuthorDocsV2,
    PendingAuthorTextV2,
    PendingChipV2,
    PendingDropdownV2,
    PendingMultiSelectV2,
    PendingUserInputV2,
)


@pytest.mark.unit
def test_dropdown_envelope():
    env = PendingDropdownV2(
        label="Pick the creditor",
        options=["Bank A", "Bank B"],
        raw_contexts=["chunk a", "chunk b"],
    )
    assert env.kind == "dropdown"
    assert len(env.options) == 2


@pytest.mark.unit
def test_chip_envelope_capped_at_three():
    """Chip envelope enforces ≤ 3 suggestions per the FE contract."""
    with pytest.raises(ValidationError):
        PendingChipV2(label="x", chips=["a", "b", "c", "d"])


@pytest.mark.unit
def test_multi_select_envelope_with_picks_bounds():
    env = PendingMultiSelectV2(
        label="Pick K creditors",
        options=["A", "B", "C"],
        min_picks=1,
        max_picks=2,
    )
    assert env.kind == "multi_select"
    assert env.min_picks == 1
    assert env.max_picks == 2


@pytest.mark.unit
def test_author_text_envelope():
    env = PendingAuthorTextV2(label="Type the narrative")
    assert env.kind == "author_text"
    assert env.placeholder is None


@pytest.mark.unit
def test_author_date_envelope_has_no_format_field():
    """Behavior Contract #6: date formatting is BE-only — `format` MUST
    NOT be on this envelope."""
    env = PendingAuthorDateV2(label="Pick the meeting date")
    assert env.kind == "author_date"
    payload = env.model_dump()
    assert "format" not in payload
    assert "date_format" not in payload


@pytest.mark.unit
def test_author_docs_envelope_defaults_accepted_types():
    env = PendingAuthorDocsV2(label="Attach supporting docs")
    assert env.kind == "author_docs"
    assert ".pdf" in env.accepted_file_types
    assert ".docx" in env.accepted_file_types


@pytest.mark.unit
def test_attorney_pick_envelope_single_vs_multi():
    single = PendingAttorneyPickV2(
        label="Pick the attorney",
        options=[AttorneyRow(id="a1", display_name="Chad", bar_number="123")],
        multi_select=False,
    )
    multi = PendingAttorneyPickV2(
        label="Pick attorneys",
        options=[
            AttorneyRow(id="a1", display_name="Chad"),
            AttorneyRow(id="a2", display_name="Pat"),
        ],
        multi_select=True,
    )
    assert single.kind == "attorney_pick"
    assert single.multi_select is False
    assert multi.multi_select is True


@pytest.mark.unit
@pytest.mark.parametrize(
    "raw,expected_kind",
    [
        ({"kind": "dropdown", "label": "x"}, "dropdown"),
        ({"kind": "chip", "label": "x"}, "chip"),
        ({"kind": "multi_select", "label": "x"}, "multi_select"),
        ({"kind": "author_text", "label": "x"}, "author_text"),
        ({"kind": "author_date", "label": "x"}, "author_date"),
        ({"kind": "author_docs", "label": "x"}, "author_docs"),
        ({"kind": "attorney_pick", "label": "x", "options": []}, "attorney_pick"),
    ],
)
def test_pending_union_discriminates_by_kind(raw, expected_kind):
    adapter = TypeAdapter(PendingUserInputV2)
    parsed = adapter.validate_python(raw)
    assert parsed.kind == expected_kind
