"""Tests for plan_bundle_v2 + run_bundle_v2.

plan_bundle_v2 is pure — covered with direct unit tests.

run_bundle_v2 has DB / R2 / LLM dependencies — patched so we exercise
the orchestration logic (companion ordering, hard-fail on missing
templates / wrong role / pending inputs, child output prefix shape)
without external calls.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from src.core.studio_v2.orchestration.bundling import (
    _PlannedChildV2,
    plan_bundle_v2,
    run_bundle_v2,
)
from src.core.studio_v2.types.bundling import (
    BranchCompanion,
    BranchOption,
    FixedCompanion,
    LiteralSlotConfig,
    ParentVariableSlotConfig,
    TemplateConfigV2,
    TemplateRole,
)
from src.core.studio_v2.types.orchestration import (
    BundleChildRunV2,
    FinalizedRunV2,
    InitialStagesResultV2,
)
from src.core.studio_v2.types.resolution import ResolvedTemplateValueV2


# ─── plan_bundle_v2 ──────────────────────────────────────────────────


@pytest.mark.unit
def test_plan_bundle_fixed_companion_schedules():
    companions = [
        FixedCompanion(
            id="comp-1", label="Cover sheet",
            child_template_id="tpl-cs",
            slot_configurations={
                "debtor": ParentVariableSlotConfig(parent_variable="debtor_name"),
            },
        ),
    ]
    planned = plan_bundle_v2(companions, bundle_picks=None)
    assert len(planned) == 1
    assert planned[0].template_id == "tpl-cs"
    assert planned[0].companion_label == "Cover sheet"
    assert "debtor" in planned[0].slot_configurations


@pytest.mark.unit
def test_plan_bundle_fixed_companion_missing_child_template_400():
    companions = [
        FixedCompanion(id="comp-1", label="Cover sheet", child_template_id=None),
    ]
    with pytest.raises(HTTPException) as exc:
        plan_bundle_v2(companions, bundle_picks=None)
    assert exc.value.status_code == 400
    assert "child_template_id" in str(exc.value.detail)


@pytest.mark.unit
def test_plan_bundle_branch_companion_with_matching_pick():
    branch = BranchCompanion(
        id="comp-b", label="Notice variant",
        question="With or without hearing?",
        options=[
            BranchOption(id="opt-h", option_label="With hearing",
                         child_template_id="tpl-nh"),
            BranchOption(id="opt-nh", option_label="No hearing",
                         child_template_id="tpl-nnh"),
        ],
    )
    planned = plan_bundle_v2([branch], bundle_picks={"comp-b": "opt-h"})
    assert len(planned) == 1
    assert planned[0].template_id == "tpl-nh"
    assert "With hearing" in planned[0].companion_label


@pytest.mark.unit
def test_plan_bundle_branch_missing_pick_400():
    branch = BranchCompanion(
        id="comp-b", label="x", question="?",
        options=[BranchOption(id="opt-1", option_label="A", child_template_id="t1")],
    )
    with pytest.raises(HTTPException) as exc:
        plan_bundle_v2([branch], bundle_picks=None)
    assert exc.value.status_code == 400
    assert "requires a bundle pick" in str(exc.value.detail)


@pytest.mark.unit
def test_plan_bundle_branch_invalid_pick_id_400():
    branch = BranchCompanion(
        id="comp-b", label="x", question="?",
        options=[BranchOption(id="opt-1", option_label="A", child_template_id="t1")],
    )
    with pytest.raises(HTTPException) as exc:
        plan_bundle_v2([branch], bundle_picks={"comp-b": "does-not-exist"})
    assert exc.value.status_code == 400
    assert "no option with id" in str(exc.value.detail)


@pytest.mark.unit
def test_plan_bundle_branch_option_missing_child_template_400():
    branch = BranchCompanion(
        id="comp-b", label="x", question="?",
        options=[BranchOption(id="opt-1", option_label="A", child_template_id=None)],
    )
    with pytest.raises(HTTPException) as exc:
        plan_bundle_v2([branch], bundle_picks={"comp-b": "opt-1"})
    assert exc.value.status_code == 400
    assert "child_template_id" in str(exc.value.detail)


@pytest.mark.unit
def test_plan_bundle_preserves_companion_order():
    companions = [
        FixedCompanion(id="a", label="A", child_template_id="ta"),
        FixedCompanion(id="b", label="B", child_template_id="tb"),
        FixedCompanion(id="c", label="C", child_template_id="tc"),
    ]
    planned = plan_bundle_v2(companions, bundle_picks=None)
    assert [p.template_id for p in planned] == ["ta", "tb", "tc"]


@pytest.mark.unit
def test_plan_bundle_mixed_fixed_and_branch():
    companions = [
        FixedCompanion(id="fix-1", label="Cover", child_template_id="t-cov"),
        BranchCompanion(
            id="br-1", label="Notice", question="?",
            options=[
                BranchOption(id="o1", option_label="With", child_template_id="t-w"),
                BranchOption(id="o2", option_label="Without", child_template_id="t-wo"),
            ],
        ),
    ]
    planned = plan_bundle_v2(companions, bundle_picks={"br-1": "o2"})
    assert [p.template_id for p in planned] == ["t-cov", "t-wo"]


# ─── run_bundle_v2 ──────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_bundle_returns_empty_when_not_master():
    """A SINGLE-role parent has no companions to run; should no-op."""
    config = TemplateConfigV2(role=TemplateRole.SINGLE)
    out = await run_bundle_v2(
        case=object(),
        parent_resolved_values=[],
        parent_filled_bytes=b"\x00",
        parent_config=config,
        bundle_picks=None,
        output_prefix="dry_run/r-1",
    )
    assert out == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_bundle_returns_empty_when_no_companions():
    config = TemplateConfigV2(role=TemplateRole.MASTER, companions=[])
    out = await run_bundle_v2(
        case=object(),
        parent_resolved_values=[],
        parent_filled_bytes=b"\x00",
        parent_config=config,
        bundle_picks=None,
        output_prefix="dry_run/r-1",
    )
    assert out == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_bundle_orchestrates_single_child_end_to_end():
    """Patch _resolve_and_finalize_child_v2 and confirm it's invoked
    per planned companion with the right parent_resolved_map +
    parent_draft_text."""
    config = TemplateConfigV2(
        role=TemplateRole.MASTER,
        companions=[
            FixedCompanion(id="c1", label="Cover", child_template_id="t-cs"),
        ],
    )
    parent_resolved = [
        ResolvedTemplateValueV2(template_variable="debtor_name", value="Jane Doe"),
        ResolvedTemplateValueV2(template_variable="empty_var", value=""),
    ]

    captured_calls: list[dict] = []

    async def fake_child(*, case, child_plan, parent_resolved_map, parent_draft_text, output_prefix):
        captured_calls.append({
            "template_id": child_plan.template_id,
            "parent_resolved_map": parent_resolved_map,
            "parent_draft_text": parent_draft_text,
            "output_prefix": output_prefix,
        })
        return BundleChildRunV2(
            template_id=child_plan.template_id,
            template_name="cs",
            companion_label=child_plan.companion_label,
            finalized=FinalizedRunV2(
                resolved_values=[],
                generated_doc_url="https://r2/child.docx",
                r2_object_key="key",
            ),
        )

    with patch(
        "src.core.studio_v2.orchestration.bundling._resolve_and_finalize_child_v2",
        new=AsyncMock(side_effect=fake_child),
    ), patch(
        "src.core.studio_v2.orchestration.bundling.DocxTemplateService.extract_all_text",
        return_value="parent draft prose",
    ):
        out = await run_bundle_v2(
            case=SimpleNamespace(id="case-1"),
            parent_resolved_values=parent_resolved,
            parent_filled_bytes=b"\x00",
            parent_config=config,
            bundle_picks=None,
            output_prefix="dry_run/r-1",
        )
    assert len(out) == 1
    assert out[0].template_id == "t-cs"

    # parent_resolved_map drops empty values per spec.
    assert captured_calls[0]["parent_resolved_map"] == {"debtor_name": "Jane Doe"}
    assert captured_calls[0]["parent_draft_text"] == "parent draft prose"
    assert captured_calls[0]["output_prefix"] == "dry_run/r-1"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_bundle_runs_children_in_parallel():
    """Mock _resolve_and_finalize_child_v2 with a slow sleep; confirm
    total wall time < sum-of-sleeps (proves parallel execution)."""
    import asyncio
    import time

    config = TemplateConfigV2(
        role=TemplateRole.MASTER,
        companions=[
            FixedCompanion(id="c1", label="A", child_template_id="ta"),
            FixedCompanion(id="c2", label="B", child_template_id="tb"),
            FixedCompanion(id="c3", label="C", child_template_id="tc"),
        ],
    )

    async def slow_child(**kwargs):
        await asyncio.sleep(0.1)
        return BundleChildRunV2(
            template_id=kwargs["child_plan"].template_id,
            template_name="x",
            companion_label="x",
            finalized=FinalizedRunV2(
                resolved_values=[], generated_doc_url="x", r2_object_key="x",
            ),
        )

    with patch(
        "src.core.studio_v2.orchestration.bundling._resolve_and_finalize_child_v2",
        new=AsyncMock(side_effect=slow_child),
    ), patch(
        "src.core.studio_v2.orchestration.bundling.DocxTemplateService.extract_all_text",
        return_value="",
    ):
        t0 = time.monotonic()
        out = await run_bundle_v2(
            case=SimpleNamespace(id="case-1"),
            parent_resolved_values=[], parent_filled_bytes=b"",
            parent_config=config, bundle_picks=None,
            output_prefix="dry_run/r-1",
        )
        elapsed = time.monotonic() - t0

    # If sequential: 0.3s. If parallel: ~0.1s. Give generous margin.
    assert elapsed < 0.25
    assert len(out) == 3
    # asyncio.gather preserves input order.
    assert [c.template_id for c in out] == ["ta", "tb", "tc"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_bundle_hard_fails_when_child_template_missing():
    config = TemplateConfigV2(
        role=TemplateRole.MASTER,
        companions=[FixedCompanion(id="c1", label="x", child_template_id="missing")],
    )
    with patch(
        "src.core.studio_v2.orchestration.bundling.TemplatesV2Repository.get",
        new=AsyncMock(return_value=None),
    ), patch(
        "src.core.studio_v2.orchestration.bundling.DocxTemplateService.extract_all_text",
        return_value="",
    ):
        with pytest.raises(HTTPException) as exc:
            await run_bundle_v2(
                case=SimpleNamespace(id="case-1"),
                parent_resolved_values=[], parent_filled_bytes=b"",
                parent_config=config, bundle_picks=None,
                output_prefix="dry_run/r-1",
            )
    assert exc.value.status_code == 404


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_bundle_hard_fails_when_child_role_not_part_of_packet():
    config = TemplateConfigV2(
        role=TemplateRole.MASTER,
        companions=[FixedCompanion(id="c1", label="x", child_template_id="t1")],
    )
    bad_child = SimpleNamespace(
        id="t1", name="x",
        config={"role": "single", "companions": []},
    )
    with patch(
        "src.core.studio_v2.orchestration.bundling.TemplatesV2Repository.get",
        new=AsyncMock(return_value=bad_child),
    ), patch(
        "src.core.studio_v2.orchestration.bundling.DocxTemplateService.extract_all_text",
        return_value="",
    ):
        with pytest.raises(HTTPException) as exc:
            await run_bundle_v2(
                case=SimpleNamespace(id="case-1"),
                parent_resolved_values=[], parent_filled_bytes=b"",
                parent_config=config, bundle_picks=None,
                output_prefix="dry_run/r-1",
            )
    assert exc.value.status_code == 400
    assert "part_of_packet" in str(exc.value.detail)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_bundle_hard_fails_when_child_surfaces_pending_inputs():
    """The save-time validator is the primary gate; this runtime
    check is defense in depth."""
    from src.core.studio_v2.types.pending import PendingAuthorTextV2

    _CHILD_TPL = "00000000-0000-0000-0000-000000000099"
    config = TemplateConfigV2(
        role=TemplateRole.MASTER,
        companions=[FixedCompanion(id="c1", label="x", child_template_id=_CHILD_TPL)],
    )
    child_row = SimpleNamespace(
        id=_CHILD_TPL, name="child",
        config={"role": "part_of_packet", "companions": []},
    )
    # ORM row stub for the child's only field — a SAFE source so the
    # validator doesn't catch it, exercising the runtime check.
    safe_field = SimpleNamespace(
        id="00000000-0000-0000-0000-000000000001",
        template_id="00000000-0000-0000-0000-000000000099",
        template_variable="x",
        template_property_marker=None,
        template_property_marker_aliases=[],
        template_identifying_text_match=None,
        description=None,
        template_index=0,
        params={"source": "current_date"},
    )
    with patch(
        "src.core.studio_v2.orchestration.bundling.TemplatesV2Repository.get",
        new=AsyncMock(return_value=child_row),
    ), patch(
        "src.core.studio_v2.repositories.TemplateFieldsV2Repository.list_for_template",
        new=AsyncMock(return_value=[safe_field]),
    ), patch(
        "src.core.studio_v2.orchestration.bundling.r2_service.download_file",
        new=AsyncMock(return_value=b"\x00"),
    ), patch(
        "src.core.studio_v2.orchestration.bundling.run_initial_stages_v2",
        new=AsyncMock(return_value=InitialStagesResultV2(
            all_resolved=[],
            pending_inputs={"x": PendingAuthorTextV2(label="x")},
        )),
    ), patch(
        "src.core.studio_v2.orchestration.bundling.DocxTemplateService.extract_all_text",
        return_value="",
    ):
        with pytest.raises(HTTPException) as exc:
            await run_bundle_v2(
                case=SimpleNamespace(id="case-1"),
                parent_resolved_values=[], parent_filled_bytes=b"",
                parent_config=config, bundle_picks=None,
                output_prefix="dry_run/r-1",
            )
    assert exc.value.status_code == 500
    assert "COMPANION_SURFACED_PENDING_INPUTS" in str(exc.value.detail)
