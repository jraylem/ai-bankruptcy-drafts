"""Pure-function tests for the re-extract diff classification logic.

The DB-mutating wrapper (`re_extract_diff_apply`) needs a session to
test meaningfully; the classification it routes through
(`classify_re_extract_diff`) is pure and lives in the same module.
These tests cover the cases the user-visible "what changed" panel
will render: inserted (new vars from the agent), updated (kept vars
whose wizard params survive), deleted (paralegal merged or ignored).
"""

import pytest

from src.core.studio_v2.repositories.template_fields_v2 import (
    ReExtractDiff,
    classify_re_extract_diff,
)


@pytest.mark.unit
def test_classify_no_changes():
    inserted, updated, deleted = classify_re_extract_diff(
        existing_names={"debtor_name", "case_number"},
        new_names={"debtor_name", "case_number"},
    )
    assert inserted == []
    assert updated == ["case_number", "debtor_name"]
    assert deleted == []


@pytest.mark.unit
def test_classify_all_new():
    inserted, updated, deleted = classify_re_extract_diff(
        existing_names=set(),
        new_names={"debtor_name", "case_number"},
    )
    assert inserted == ["case_number", "debtor_name"]
    assert updated == []
    assert deleted == []


@pytest.mark.unit
def test_classify_all_deleted():
    inserted, updated, deleted = classify_re_extract_diff(
        existing_names={"debtor_name", "case_number"},
        new_names=set(),
    )
    assert inserted == []
    assert updated == []
    assert deleted == ["case_number", "debtor_name"]


@pytest.mark.unit
def test_classify_merge_scenario():
    """Paralegal merges claim_no_short + claim_no_long into case_number.

    Diff: drop the two source vars, insert the merged one.
    """
    inserted, updated, deleted = classify_re_extract_diff(
        existing_names={"debtor_name", "claim_no_short", "claim_no_long"},
        new_names={"debtor_name", "case_number"},
    )
    assert inserted == ["case_number"]
    assert updated == ["debtor_name"]
    assert deleted == ["claim_no_long", "claim_no_short"]


@pytest.mark.unit
def test_classify_ignore_text_scenario():
    """Paralegal asks to ignore the firm-letterhead block — vars in
    that block drop; everything else preserved."""
    inserted, updated, deleted = classify_re_extract_diff(
        existing_names={"debtor_name", "attorney_name", "firm_address"},
        new_names={"debtor_name"},
    )
    assert inserted == []
    assert updated == ["debtor_name"]
    assert deleted == ["attorney_name", "firm_address"]


@pytest.mark.unit
def test_classify_agent_spotted_new_var():
    """Agent spots a new variable on re-extract (e.g. a section_341 date
    that wasn't in the original spec).
    """
    inserted, updated, deleted = classify_re_extract_diff(
        existing_names={"debtor_name", "case_number"},
        new_names={"debtor_name", "case_number", "section_341_meeting_date"},
    )
    assert inserted == ["section_341_meeting_date"]
    assert updated == ["case_number", "debtor_name"]
    assert deleted == []


@pytest.mark.unit
def test_re_extract_diff_pydantic_round_trip():
    diff = ReExtractDiff(
        inserted=["a", "b"],
        updated=["c"],
        deleted=["d", "e"],
    )
    raw = diff.model_dump_json()
    restored = ReExtractDiff.model_validate_json(raw)
    assert restored.inserted == ["a", "b"]
    assert restored.updated == ["c"]
    assert restored.deleted == ["d", "e"]


@pytest.mark.unit
def test_re_extract_diff_defaults():
    diff = ReExtractDiff()
    assert diff.inserted == []
    assert diff.updated == []
    assert diff.deleted == []
