"""Tests for `delete_template_by_id` warn-then-force behavior.

Covers the new safety gate that scans for parent templates whose
bundle_companions reference the deletion target. Default behavior (force=False)
raises 409 when references exist; force=True cascade-cleans referencing
parents before soft-deleting.

Repository calls are mocked via monkeypatch.setattr with AsyncMock — these
tests focus on the orchestration in crud.py, not the SQL underneath.
"""

from unittest.mock import AsyncMock
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from src.core.common.storage.database import DraftTemplateRepository
from src.core.components.engines.template.crud import (
    _companion_labels_referencing_child,
    delete_template_by_id,
)


def _row(template_id: str, name: str, bundle_companions=None) -> SimpleNamespace:
    """Stand-in for a DraftTemplate ORM row. Tests only read .id, .name,
    .bundle_companions, so a namespace is enough."""
    return SimpleNamespace(
        id=template_id,
        name=name,
        bundle_companions=bundle_companions,
    )


@pytest.mark.unit
async def test_delete_raises_404_when_template_missing(monkeypatch):
    monkeypatch.setattr(
        DraftTemplateRepository, "get", AsyncMock(return_value=None),
    )

    with pytest.raises(HTTPException) as ei:
        await delete_template_by_id("does-not-exist")
    assert ei.value.status_code == 404


@pytest.mark.unit
async def test_delete_works_without_references_keeps_current_behavior(monkeypatch):
    """Control case — no parent references the child, force defaults to
    False, delete proceeds with empty cleaned_parents (wire-compatible
    with pre-change callers)."""
    monkeypatch.setattr(
        DraftTemplateRepository, "get",
        AsyncMock(return_value=_row("child-1", "Cover Sheet")),
    )
    monkeypatch.setattr(
        DraftTemplateRepository, "find_parents_referencing_child",
        AsyncMock(return_value=[]),
    )
    delete_mock = AsyncMock(return_value=True)
    monkeypatch.setattr(DraftTemplateRepository, "delete", delete_mock)

    result = await delete_template_by_id("child-1")

    assert result.success is True
    assert result.id == "child-1"
    assert result.cleaned_parents == []
    delete_mock.assert_awaited_once_with("child-1")


@pytest.mark.unit
async def test_delete_raises_409_when_referenced_and_force_is_false(monkeypatch):
    """A FixedBundleCompanion in a parent references the doomed child.
    Default force=False must raise 409 with the parent listed and NOT
    flip is_active=false."""
    monkeypatch.setattr(
        DraftTemplateRepository, "get",
        AsyncMock(return_value=_row("child-1", "Cover Sheet")),
    )
    monkeypatch.setattr(
        DraftTemplateRepository, "find_parents_referencing_child",
        AsyncMock(return_value=[
            _row(
                "parent-A", "Motion to Waive",
                bundle_companions=[
                    {"kind": "fixed", "label": "Cover", "child_template_id": "child-1"},
                ],
            ),
        ]),
    )
    delete_mock = AsyncMock(return_value=True)
    monkeypatch.setattr(DraftTemplateRepository, "delete", delete_mock)

    with pytest.raises(HTTPException) as ei:
        await delete_template_by_id("child-1", force=False)

    assert ei.value.status_code == 409
    detail = ei.value.detail
    assert "Motion to Waive" not in detail["message"]  # parent name only in list, not message
    assert len(detail["referencing_parents"]) == 1
    parent = detail["referencing_parents"][0]
    assert parent["template_id"] == "parent-A"
    assert parent["name"] == "Motion to Waive"
    assert parent["companion_labels"] == ["Cover"]
    # Critically: delete() must NOT have been called on the conflict path.
    delete_mock.assert_not_awaited()


@pytest.mark.unit
async def test_delete_409_surfaces_branch_companion_match(monkeypatch):
    """A BranchBundleCompanion option points at the child. The 409 should
    list the branch companion's label too (not its inner option labels)."""
    monkeypatch.setattr(
        DraftTemplateRepository, "get",
        AsyncMock(return_value=_row("child-1", "Notice of Hearing")),
    )
    monkeypatch.setattr(
        DraftTemplateRepository, "find_parents_referencing_child",
        AsyncMock(return_value=[
            _row(
                "parent-B", "Pleading X",
                bundle_companions=[
                    {
                        "kind": "branch",
                        "label": "Hearing required?",
                        "question": "Includes a Notice of Hearing?",
                        "options": [
                            {"label": "Yes", "child_template_id": "child-1", "slot_configurations": {}},
                            {"label": "No", "child_template_id": "child-other", "slot_configurations": {}},
                        ],
                    },
                ],
            ),
        ]),
    )
    monkeypatch.setattr(DraftTemplateRepository, "delete", AsyncMock(return_value=True))

    with pytest.raises(HTTPException) as ei:
        await delete_template_by_id("child-1", force=False)

    assert ei.value.status_code == 409
    parents = ei.value.detail["referencing_parents"]
    assert parents[0]["companion_labels"] == ["Hearing required?"]


@pytest.mark.unit
async def test_delete_force_cascade_cleans_then_soft_deletes(monkeypatch):
    """force=True: each referencing parent gets its bundle_companions
    pruned (via the repository), then the target is soft-deleted. The
    response carries cleaned_parents."""
    monkeypatch.setattr(
        DraftTemplateRepository, "get",
        AsyncMock(return_value=_row("child-1", "Cover Sheet")),
    )
    monkeypatch.setattr(
        DraftTemplateRepository, "find_parents_referencing_child",
        AsyncMock(return_value=[
            _row("parent-A", "Motion to Waive"),
            _row("parent-B", "Pleading X"),
        ]),
    )
    prune_mock = AsyncMock(side_effect=[["Cover"], ["Hearing required?"]])
    monkeypatch.setattr(
        DraftTemplateRepository, "prune_companion_references_for_child", prune_mock,
    )
    delete_mock = AsyncMock(return_value=True)
    monkeypatch.setattr(DraftTemplateRepository, "delete", delete_mock)

    result = await delete_template_by_id("child-1", force=True)

    assert result.success is True
    assert result.id == "child-1"
    assert len(result.cleaned_parents) == 2

    cleaned_a, cleaned_b = result.cleaned_parents
    assert cleaned_a.template_id == "parent-A"
    assert cleaned_a.name == "Motion to Waive"
    assert cleaned_a.removed_companion_labels == ["Cover"]
    assert cleaned_b.template_id == "parent-B"
    assert cleaned_b.removed_companion_labels == ["Hearing required?"]

    # Both prune calls happened (one per parent) BEFORE delete fired.
    assert prune_mock.await_count == 2
    delete_mock.assert_awaited_once_with("child-1")


# ─── _companion_labels_referencing_child — branch coverage ─────────────


@pytest.mark.unit
def test_companion_labels_empty_when_no_companions():
    assert _companion_labels_referencing_child(None, "child-1") == []
    assert _companion_labels_referencing_child([], "child-1") == []


@pytest.mark.unit
def test_companion_labels_skips_non_matching_fixed_companion():
    """Fixed companion that points at a DIFFERENT child must not show up."""
    companions = [
        {"kind": "fixed", "label": "Cover", "child_template_id": "child-other"},
    ]
    assert _companion_labels_referencing_child(companions, "child-1") == []


@pytest.mark.unit
def test_companion_labels_skips_branch_with_no_matching_option():
    """Branch companion where NO option points at the target must not match."""
    companions = [
        {
            "kind": "branch",
            "label": "Hearing required?",
            "options": [
                {"label": "Yes", "child_template_id": "child-x"},
                {"label": "No", "child_template_id": "child-y"},
            ],
        },
    ]
    assert _companion_labels_referencing_child(companions, "child-1") == []


@pytest.mark.unit
def test_companion_labels_handles_unknown_kind_gracefully():
    """Future companion kinds (or malformed entries) shouldn't break the
    scan — they're skipped silently."""
    companions = [
        {"kind": "unknown_future_kind", "label": "Weird", "child_template_id": "child-1"},
        {"kind": "fixed", "label": "Real Match", "child_template_id": "child-1"},
    ]
    assert _companion_labels_referencing_child(companions, "child-1") == ["Real Match"]


@pytest.mark.unit
def test_companion_labels_collects_multiple_matches_in_order():
    """Multiple matching companions in one parent → all labels in
    document order."""
    companions = [
        {"kind": "fixed", "label": "First", "child_template_id": "child-1"},
        {"kind": "fixed", "label": "Other", "child_template_id": "child-other"},
        {
            "kind": "branch",
            "label": "Second branch",
            "options": [
                {"label": "Yes", "child_template_id": "child-1"},
                {"label": "No", "child_template_id": "child-other"},
            ],
        },
    ]
    assert _companion_labels_referencing_child(companions, "child-1") == [
        "First", "Second branch",
    ]


# ─── _filter_companions_for_child — pure prune logic ───────────────────


from src.core.common.storage.database.repositories.draft_template_repository import (  # noqa: E402
    _filter_companions_for_child,
)


@pytest.mark.unit
def test_filter_drops_matching_fixed_companion():
    """Fixed companion that points at the doomed child → dropped; non-
    matching siblings preserved verbatim."""
    keep = {"kind": "fixed", "label": "Keep", "child_template_id": "child-keep"}
    drop = {"kind": "fixed", "label": "Drop", "child_template_id": "child-1"}
    pruned, labels = _filter_companions_for_child([keep, drop], "child-1")
    assert pruned == [keep]
    assert labels == ["Drop"]


@pytest.mark.unit
def test_filter_drops_branch_when_options_would_fall_below_min_length():
    """BranchBundleCompanion requires options.length >= 2. If filtering
    leaves only 1 option, the entire branch must be dropped (can't save
    a malformed companion)."""
    branch = {
        "kind": "branch",
        "label": "Hearing?",
        "options": [
            {"label": "Yes", "child_template_id": "child-1"},
            {"label": "No", "child_template_id": "child-2"},
        ],
    }
    pruned, labels = _filter_companions_for_child([branch], "child-1")
    assert pruned == []
    assert labels == ["Hearing?"]


@pytest.mark.unit
def test_filter_keeps_branch_with_option_removed_when_min_length_satisfied():
    """3-option branch loses the matching option but keeps the other 2 →
    survives with the remaining options."""
    branch = {
        "kind": "branch",
        "label": "Three-way",
        "options": [
            {"label": "A", "child_template_id": "child-A"},
            {"label": "B", "child_template_id": "child-1"},  # target
            {"label": "C", "child_template_id": "child-C"},
        ],
    }
    pruned, labels = _filter_companions_for_child([branch], "child-1")
    assert len(pruned) == 1
    assert pruned[0]["kind"] == "branch"
    assert [o["label"] for o in pruned[0]["options"]] == ["A", "C"]
    assert labels == ["Three-way"]


@pytest.mark.unit
def test_filter_leaves_branch_untouched_when_no_option_matches():
    """Branch where no option references the doomed child → unchanged,
    no label recorded."""
    branch = {
        "kind": "branch",
        "label": "Unrelated",
        "options": [
            {"label": "X", "child_template_id": "child-X"},
            {"label": "Y", "child_template_id": "child-Y"},
        ],
    }
    pruned, labels = _filter_companions_for_child([branch], "child-1")
    assert pruned == [branch]
    assert labels == []


@pytest.mark.unit
def test_filter_passes_through_unknown_kind():
    """Future / malformed companion kinds we don't understand → pass
    through unchanged. Conservative: better to leave them than drop."""
    weird = {"kind": "future_kind", "label": "?", "child_template_id": "child-1"}
    pruned, labels = _filter_companions_for_child([weird], "child-1")
    assert pruned == [weird]
    assert labels == []


@pytest.mark.unit
def test_filter_returns_empty_when_every_companion_matches():
    """When the doomed child is the only thing every companion referenced,
    the filter returns an empty list — the signal the repository uses to
    demote the parent's bundle_role from 'parent' back to 'standalone'
    (otherwise the Studio shows a misleading Parent badge with nothing
    to bundle).
    """
    companions = [
        {"kind": "fixed", "label": "Cover", "child_template_id": "child-1"},
        {
            "kind": "branch",
            "label": "Hearing required?",
            "options": [
                {"label": "Yes", "child_template_id": "child-1"},
                {"label": "No", "child_template_id": "child-1"},
            ],
        },
    ]
    pruned, labels = _filter_companions_for_child(companions, "child-1")
    assert pruned == []  # nothing survives — repo will demote role
    assert labels == ["Cover", "Hearing required?"]
