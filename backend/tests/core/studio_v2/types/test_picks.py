"""Tests for the 3 v2 pick wire types — round-trip, discrimination,
extra=forbid."""

import pytest
from pydantic import ValidationError, TypeAdapter

from src.core.studio_v2.types.picks import (
    MultiSelectPickV2,
    SingleValuePickV2,
    SupportingDocsPickV2,
    UserSelectionV2,
)


@pytest.mark.unit
def test_single_value_pick_round_trip():
    pick = SingleValuePickV2(value="Acme Bank — $1,200")
    assert pick.model_dump() == {"value": "Acme Bank — $1,200"}


@pytest.mark.unit
def test_single_value_pick_extra_forbid():
    with pytest.raises(ValidationError):
        SingleValuePickV2(value="x", bogus="nope")


@pytest.mark.unit
def test_multi_select_pick_defaults_empty():
    pick = MultiSelectPickV2()
    assert pick.picked_values == []


@pytest.mark.unit
def test_multi_select_pick_round_trip():
    pick = MultiSelectPickV2(picked_values=["A", "B", "C"])
    assert pick.model_dump() == {"picked_values": ["A", "B", "C"]}


@pytest.mark.unit
def test_supporting_docs_pick_with_files():
    pick = SupportingDocsPickV2(
        user_text="Income dropped after surgery",
        file_urls=[
            "https://r2/cases/abc/uploads/medical_bill.pdf",
            "https://r2/cases/abc/uploads/lost_wages.png",
        ],
    )
    assert len(pick.file_urls) == 2
    assert pick.user_text.startswith("Income dropped")


@pytest.mark.unit
def test_supporting_docs_pick_defaults_empty_files():
    pick = SupportingDocsPickV2(user_text="bare text")
    assert pick.file_urls == []


@pytest.mark.unit
@pytest.mark.parametrize(
    "raw,expected_type",
    [
        ({"value": "v"}, SingleValuePickV2),
        ({"picked_values": ["a", "b"]}, MultiSelectPickV2),
        ({"user_text": "t", "file_urls": []}, SupportingDocsPickV2),
    ],
)
def test_user_selection_union_dispatches_correctly(raw, expected_type):
    """The 3 pick types' fields are distinct enough that Pydantic picks
    the right one without a discriminator key."""
    adapter = TypeAdapter(UserSelectionV2)
    parsed = adapter.validate_python(raw)
    assert isinstance(parsed, expected_type)
