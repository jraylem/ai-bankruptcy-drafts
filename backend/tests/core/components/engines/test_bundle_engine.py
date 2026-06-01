"""Tests for the bundling orchestrator (Phase 2).

Covers:
  - `plan_bundle`: schedules fixed companions, requires picks for branches,
    rejects unknown labels.
  - `run_bundle`: builds ParentBundleContext correctly, schedules each
    planned child, finalizes per-child, and surfaces a 500 if a child
    surfaces user-input pauses (Phase 2 constraint violation).

External seams (R2, repository, build_agent_config, run_initial_stages,
finalize_run) are mocked so the tests assert orchestration behavior
without standing up the full pipeline.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from src.core.agents.orchestration import bundling as bundling_module
from src.core.agents.orchestration.bundling import (
    BundleChildRun,
    plan_bundle,
    run_bundle,
)
from src.core.agents.orchestration.finalizer import FinalizedRun
from src.core.agents.types.bundling import (
    BranchBundleCompanion,
    BranchOption,
    FixedBundleCompanion,
    LiteralSlotConfig,
    ParentVariableSlotConfig,
)
from src.core.agents.types.resolution import ResolvedTemplateValue
from tests.core.factories import make_agent_config


# ─── plan_bundle ───────────────────────────────────────────────────────


@pytest.mark.unit
def test_plan_bundle_schedules_fixed_companion_without_pick():
    fixed = FixedBundleCompanion(
        label="Cover Sheet",
        child_template_id="tpl_cover",
        slot_configurations={
            "case_number": ParentVariableSlotConfig(parent_variable="case_number"),
        },
    )

    planned = plan_bundle([fixed], bundle_picks=None)

    assert len(planned) == 1
    assert planned[0].template_id == "tpl_cover"
    assert planned[0].companion_label == "Cover Sheet"
    assert "case_number" in planned[0].slot_configurations


@pytest.mark.unit
def test_plan_bundle_routes_branch_to_picked_option():
    branch = BranchBundleCompanion(
        label="Certificate of Service",
        question="Includes a Notice of Hearing?",
        options=[
            BranchOption(label="Yes", child_template_id="tpl_cos_with_hearing"),
            BranchOption(label="No", child_template_id="tpl_cos_no_hearing"),
        ],
    )

    planned = plan_bundle([branch], bundle_picks={"0": "No"})

    assert len(planned) == 1
    assert planned[0].template_id == "tpl_cos_no_hearing"
    assert "No" in planned[0].companion_label
    assert "Certificate of Service" in planned[0].companion_label


@pytest.mark.unit
def test_plan_bundle_raises_when_branch_pick_missing():
    branch = BranchBundleCompanion(
        label="Cert of Service",
        question="Hearing?",
        options=[
            BranchOption(label="Yes", child_template_id="a"),
            BranchOption(label="No", child_template_id="b"),
        ],
    )
    with pytest.raises(HTTPException) as exc:
        plan_bundle([branch], bundle_picks={})
    assert exc.value.status_code == 400
    assert "Cert of Service" in exc.value.detail


@pytest.mark.unit
def test_plan_bundle_raises_on_unknown_pick_label():
    branch = BranchBundleCompanion(
        label="Cert of Service",
        question="Hearing?",
        options=[
            BranchOption(label="Yes", child_template_id="a"),
            BranchOption(label="No", child_template_id="b"),
        ],
    )
    with pytest.raises(HTTPException) as exc:
        plan_bundle([branch], bundle_picks={"0": "Maybe"})
    assert exc.value.status_code == 400
    assert "Maybe" in exc.value.detail


@pytest.mark.unit
def test_plan_bundle_handles_mixed_companions():
    fixed = FixedBundleCompanion(label="A", child_template_id="tpl_a")
    branch = BranchBundleCompanion(
        label="B",
        question="?",
        options=[
            BranchOption(label="Y", child_template_id="tpl_y"),
            BranchOption(label="N", child_template_id="tpl_n"),
        ],
    )

    planned = plan_bundle([fixed, branch], bundle_picks={"1": "Y"})

    assert [p.template_id for p in planned] == ["tpl_a", "tpl_y"]


# ─── run_bundle ────────────────────────────────────────────────────────


def _mock_child_row(template_id: str, *, role: str = "child_only", template_spec=None):
    """SimpleNamespace mimicking the columns DraftTemplateRepository.get returns."""
    return SimpleNamespace(
        id=template_id,
        name=f"Child {template_id}",
        bundle_role=role,
        bundle_companions=None,
        template_spec=template_spec or [{"template_variable": "x", "template_index": 0}],
        agent_config=None,
    )


def _install_run_bundle_mocks(monkeypatch, *, child_role="child_only"):
    """Mock everything run_bundle calls except plan_bundle (which is pure)."""
    repo_get = AsyncMock(return_value=_mock_child_row("tpl_child", role=child_role))
    download = AsyncMock(return_value=b"%DOCX-child-template")
    build_cfg = AsyncMock(return_value=make_agent_config(template_id="tpl_child", fields=[]))
    run_initial = AsyncMock(return_value=SimpleNamespace(
        all_resolved=[ResolvedTemplateValue.high_confidence("x", "X", "ok")],
        pending_inputs=None,
    ))
    finalize = AsyncMock(return_value=FinalizedRun(
        resolved_values=[ResolvedTemplateValue.high_confidence("x", "X", "ok")],
        generated_doc_url="https://r2/child.docx",
        r2_object_key="cases/case_id/draft/child.docx",
        unresolved=[],
        warnings=[],
        filled_bytes=b"%DOCX-filled-child",
    ))

    monkeypatch.setattr(
        bundling_module.DraftTemplateRepository, "get", repo_get,
    )
    monkeypatch.setattr(bundling_module.r2_service, "download_file", download)
    monkeypatch.setattr(bundling_module, "run_initial_stages", run_initial)
    monkeypatch.setattr(bundling_module, "finalize_run", finalize)

    # build_agent_config is imported lazily inside the function — patch
    # the composer module so the deferred import resolves to our mock.
    import src.core.components.engines.template.composer as composer_mod
    monkeypatch.setattr(composer_mod, "build_agent_config", build_cfg)

    return {
        "repo_get": repo_get,
        "download": download,
        "build_cfg": build_cfg,
        "run_initial": run_initial,
        "finalize": finalize,
    }


@pytest.mark.unit
async def test_run_bundle_returns_empty_when_no_companions(monkeypatch):
    """No work to do when the parent has no companions configured."""
    result = await run_bundle(
        case_id="26_10700",
        parent_resolved_values=[],
        parent_filled_bytes=b"",
        bundle_companions=[],
        bundle_picks=None,
        output_prefix="dry_run",
    )
    assert result == []


@pytest.mark.unit
async def test_run_bundle_threads_parent_resolved_into_parent_context(monkeypatch):
    """The parent's resolved values + draft text should land on the
    ParentBundleContext passed into run_initial_stages."""
    mocks = _install_run_bundle_mocks(monkeypatch)
    monkeypatch.setattr(
        bundling_module.DocxTemplateService,
        "extract_all_text",
        lambda _: "filed motion title and body",
    )

    fixed = FixedBundleCompanion(
        label="COS",
        child_template_id="tpl_child",
        slot_configurations={
            "case_number": ParentVariableSlotConfig(parent_variable="case_number"),
            "court_division": LiteralSlotConfig(literal_value="Fort Lauderdale"),
        },
    )

    children = await run_bundle(
        case_id="26_10700",
        parent_resolved_values=[
            ResolvedTemplateValue.high_confidence("case_number", "25-14980-PDR", ""),
        ],
        parent_filled_bytes=b"%DOCX",
        bundle_companions=[fixed],
        bundle_picks=None,
        output_prefix="dry_run",
    )

    assert len(children) == 1
    assert isinstance(children[0], BundleChildRun)

    parent_ctx = mocks["run_initial"].await_args.kwargs["parent_context"]
    assert parent_ctx.resolved_values == {"case_number": "25-14980-PDR"}
    assert parent_ctx.draft_text == "filed motion title and body"
    assert "case_number" in parent_ctx.slot_configurations
    assert "court_division" in parent_ctx.slot_configurations


@pytest.mark.unit
async def test_run_bundle_raises_500_when_child_surfaces_user_input(monkeypatch):
    mocks = _install_run_bundle_mocks(monkeypatch)
    mocks["run_initial"].return_value = SimpleNamespace(
        all_resolved=[],
        pending_inputs={"some_field": object()},
    )
    monkeypatch.setattr(
        bundling_module.DocxTemplateService,
        "extract_all_text",
        lambda _: "",
    )

    fixed = FixedBundleCompanion(label="COS", child_template_id="tpl_child")

    with pytest.raises(HTTPException) as exc:
        await run_bundle(
            case_id="26_10700",
            parent_resolved_values=[],
            parent_filled_bytes=b"",
            bundle_companions=[fixed],
            bundle_picks=None,
            output_prefix="dry_run",
        )
    assert exc.value.status_code == 500
    assert "user-input pauses" in exc.value.detail.lower()


@pytest.mark.unit
async def test_run_bundle_rejects_non_child_only_referenced_template(monkeypatch):
    mocks = _install_run_bundle_mocks(monkeypatch, child_role="standalone")
    monkeypatch.setattr(
        bundling_module.DocxTemplateService,
        "extract_all_text",
        lambda _: "",
    )

    fixed = FixedBundleCompanion(label="X", child_template_id="tpl_child")

    with pytest.raises(HTTPException) as exc:
        await run_bundle(
            case_id="26_10700",
            parent_resolved_values=[],
            parent_filled_bytes=b"",
            bundle_companions=[fixed],
            bundle_picks=None,
            output_prefix="dry_run",
        )
    assert exc.value.status_code == 400
    assert "child_only" in exc.value.detail
