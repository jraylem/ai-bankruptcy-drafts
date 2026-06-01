"""Tests for orchestration result types — shape, defaults, status discriminators."""

import pytest

from src.core.studio_v2.types.orchestration import (
    AwaitingInputResponseV2,
    BundleChildRunV2,
    DryRunResponseV2,
    FinalizedRunV2,
    InitialStagesResultV2,
    ParentBundleContextV2,
)
from src.core.studio_v2.types.pending import PendingAuthorTextV2
from src.core.studio_v2.types.resolution import ResolvedTemplateValueV2


@pytest.mark.unit
def test_initial_stages_result_no_pending():
    result = InitialStagesResultV2(
        all_resolved=[ResolvedTemplateValueV2(template_variable="x", value="ok")],
    )
    assert result.pending_inputs is None
    assert len(result.all_resolved) == 1


@pytest.mark.unit
def test_initial_stages_result_with_pending():
    pending = {"narrative": PendingAuthorTextV2(label="Write it")}
    result = InitialStagesResultV2(all_resolved=[], pending_inputs=pending)
    assert result.pending_inputs == pending


@pytest.mark.unit
def test_awaiting_input_response_status_literal():
    resp = AwaitingInputResponseV2(
        run_id="r1", template_id="t1", case_id="c1",
        pending_inputs={"x": PendingAuthorTextV2(label="x")},
    )
    assert resp.status == "awaiting_input"
    # template_spec is OMITTED for the draft path; the dry-run path echoes it.
    assert resp.template_spec is None


@pytest.mark.unit
def test_dry_run_response_status_literal():
    resp = DryRunResponseV2(
        run_id="r1", template_id="t1", case_id="c1",
        generated_doc_url="https://r2/x.docx",
        r2_object_key="cases/c1/dry_run/r1.docx",
    )
    assert resp.status == "completed"
    assert resp.children == []


@pytest.mark.unit
def test_finalized_run_round_trip():
    fin = FinalizedRunV2(
        resolved_values=[ResolvedTemplateValueV2(template_variable="x", value="v")],
        generated_doc_url="https://r2/x.docx",
        r2_object_key="cases/c/draft/r.docx",
        unresolved=["y"],
        warnings=["y had no extraction"],
    )
    assert fin.unresolved == ["y"]
    assert fin.filled_bytes is None


@pytest.mark.unit
def test_bundle_child_run_carries_finalized():
    fin = FinalizedRunV2(
        resolved_values=[],
        generated_doc_url="https://r2/c.docx",
        r2_object_key="k",
    )
    child = BundleChildRunV2(
        template_id="t-c",
        template_name="cos w/ hearing",
        companion_label="Service",
        finalized=fin,
    )
    assert child.template_name == "cos w/ hearing"
    assert child.finalized.r2_object_key == "k"


@pytest.mark.unit
def test_parent_bundle_context_mutable_slots():
    ctx = ParentBundleContextV2(
        resolved_values={"debtor_name": "Jane Doe"},
        draft_text="parent draft text",
    )
    # Slot configurations should be replaceable per companion in the loop.
    ctx.slot_configurations = {"x": object()}
    assert "x" in ctx.slot_configurations
