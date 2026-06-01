"""Tests for `_compute_regenerate_diff` — partitions baseline vs new spec
into added / removed / preserved and classifies each removed entry's
reason (merged / ignored / unexpected) so the FE can render the right
annotation.

The helper is pure — no IO, no LLM. Each test wires synthetic baseline +
new spec + merges + ignored_texts and asserts the partition + reasons.
"""

from src.core.agents.types.spec import TemplateVariable
from src.core.components.engines.template.composer import (
    _compute_regenerate_diff,
)
from src.core.components.engines.template.schemas import MergeOperation


def _var(name: str, marker: str = "X", identifying: str | None = None) -> TemplateVariable:
    return TemplateVariable(
        template_variable=name,
        template_index=0,
        template_property_marker=marker,
        template_variable_string=f"[[{name}]]",
        template_identifying_text_match=identifying,
    )


def test_diff_partitions_added_removed_preserved():
    baseline = [_var("case_number"), _var("debtor_name")]
    new_spec = [_var("case_number"), _var("debtor_address")]

    diff = _compute_regenerate_diff(
        baseline=baseline,
        new_spec=new_spec,
        merges=[],
        ignored_texts=[],
    )

    assert diff.added == ["debtor_address"]
    assert [r.name for r in diff.removed] == ["debtor_name"]
    assert diff.preserved == ["case_number"]


def test_diff_classifies_removed_as_merged_when_in_merge_sources():
    baseline = [_var("case_no_short"), _var("case_no_long")]
    new_spec = [_var("case_number")]
    merges = [
        MergeOperation(source_variables=["case_no_short", "case_no_long"]),
    ]

    diff = _compute_regenerate_diff(
        baseline=baseline,
        new_spec=new_spec,
        merges=merges,
        ignored_texts=[],
    )

    by_name = {r.name: r for r in diff.removed}
    assert set(by_name) == {"case_no_short", "case_no_long"}
    assert by_name["case_no_short"].reason == "merged"
    assert by_name["case_no_short"].merged_into == "case_no_short_case_no_long"
    assert by_name["case_no_long"].reason == "merged"
    assert by_name["case_no_long"].merged_into == "case_no_short_case_no_long"


def test_diff_classifies_removed_as_ignored_when_identifying_text_overlaps():
    baseline = [
        _var(
            "clerk_block",
            identifying="Clerk, United States Bankruptcy Court Southern District of Florida",
        ),
    ]
    new_spec: list[TemplateVariable] = []
    ignored_texts = [
        "  CLERK, UNITED STATES BANKRUPTCY COURT  Southern District of Florida  ",
    ]

    diff = _compute_regenerate_diff(
        baseline=baseline,
        new_spec=new_spec,
        merges=[],
        ignored_texts=ignored_texts,
    )

    assert len(diff.removed) == 1
    assert diff.removed[0].name == "clerk_block"
    assert diff.removed[0].reason == "ignored"
    assert diff.removed[0].merged_into is None


def test_diff_classifies_removed_as_unexpected_otherwise():
    baseline = [_var("docket_title", identifying="DEBTOR'S MOTION TO MODIFY PLAN")]
    new_spec: list[TemplateVariable] = []

    diff = _compute_regenerate_diff(
        baseline=baseline,
        new_spec=new_spec,
        merges=[],
        ignored_texts=["something unrelated to the docket title"],
    )

    assert len(diff.removed) == 1
    assert diff.removed[0].name == "docket_title"
    assert diff.removed[0].reason == "unexpected"


def test_diff_returns_empty_lists_when_baseline_equals_new_spec():
    baseline = [_var("case_number"), _var("chapter")]
    new_spec = [_var("case_number"), _var("chapter")]

    diff = _compute_regenerate_diff(
        baseline=baseline,
        new_spec=new_spec,
        merges=[],
        ignored_texts=[],
    )

    assert diff.added == []
    assert diff.removed == []
    assert set(diff.preserved) == {"case_number", "chapter"}
