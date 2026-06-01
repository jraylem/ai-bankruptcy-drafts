"""Tests for the bundling types — TemplateBundleRole, BundleCompanion, SlotConfig."""

import pytest
from pydantic import TypeAdapter, ValidationError

from src.core.agents.types.bundling import (
    BranchBundleCompanion,
    BranchOption,
    BundleCompanion,
    ExtractFromDraftSlotConfig,
    FixedBundleCompanion,
    LiteralSlotConfig,
    ParentVariableSlotConfig,
    SlotConfig,
    TemplateBundleRole,
)


_COMPANION_ADAPTER = TypeAdapter(BundleCompanion)
_SLOT_ADAPTER = TypeAdapter(SlotConfig)


# ─── TemplateBundleRole ──────────────────────────────────────────────


@pytest.mark.unit
def test_template_bundle_role_values():
    assert {role.value for role in TemplateBundleRole} == {
        "standalone",
        "parent",
        "child_only",
    }


# ─── SlotConfig union discrimination ─────────────────────────────────


@pytest.mark.unit
def test_slot_config_picks_parent_variable_kind():
    payload = {"kind": "parent_variable", "parent_variable": "case_number"}
    result = _SLOT_ADAPTER.validate_python(payload)
    assert isinstance(result, ParentVariableSlotConfig)
    assert result.parent_variable == "case_number"


@pytest.mark.unit
def test_slot_config_picks_extract_from_draft_kind():
    payload = {
        "kind": "extract_from_draft",
        "extract_instruction": "the bold heading line",
    }
    result = _SLOT_ADAPTER.validate_python(payload)
    assert isinstance(result, ExtractFromDraftSlotConfig)
    assert result.extract_instruction == "the bold heading line"


@pytest.mark.unit
def test_slot_config_picks_literal_kind():
    payload = {"kind": "literal", "literal_value": "PDR"}
    result = _SLOT_ADAPTER.validate_python(payload)
    assert isinstance(result, LiteralSlotConfig)
    assert result.literal_value == "PDR"


@pytest.mark.unit
def test_slot_config_rejects_unknown_kind():
    with pytest.raises(ValidationError):
        _SLOT_ADAPTER.validate_python({"kind": "from_air", "value": "x"})


@pytest.mark.unit
def test_slot_config_rejects_extras_per_kind():
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        _SLOT_ADAPTER.validate_python(
            {"kind": "parent_variable", "parent_variable": "x", "literal_value": "y"}
        )


# ─── FixedBundleCompanion ────────────────────────────────────────────


@pytest.mark.unit
def test_fixed_companion_accepts_empty_slot_configurations():
    fixed = FixedBundleCompanion(
        label="Cover Sheet",
        child_template_id="tpl_cover",
    )
    assert fixed.kind == "fixed"
    assert fixed.slot_configurations == {}


@pytest.mark.unit
def test_fixed_companion_with_slot_configurations():
    fixed = FixedBundleCompanion(
        label="Cover Sheet",
        child_template_id="tpl_cover",
        slot_configurations={
            "case_number": ParentVariableSlotConfig(parent_variable="case_number"),
        },
    )
    assert isinstance(
        fixed.slot_configurations["case_number"], ParentVariableSlotConfig
    )


# ─── BranchBundleCompanion ───────────────────────────────────────────


@pytest.mark.unit
def test_branch_companion_requires_at_least_two_options():
    with pytest.raises(ValidationError, match="at least 2 items"):
        BranchBundleCompanion(
            label="Certificate of Service",
            question="Includes a Notice of Hearing?",
            options=[
                BranchOption(label="Yes", child_template_id="tpl_cos_with"),
            ],
        )


@pytest.mark.unit
def test_branch_companion_two_options_ok():
    branch = BranchBundleCompanion(
        label="Certificate of Service",
        question="Includes a Notice of Hearing?",
        options=[
            BranchOption(label="Yes", child_template_id="tpl_cos_with"),
            BranchOption(label="No", child_template_id="tpl_cos_no"),
        ],
    )
    assert branch.kind == "branch"
    assert len(branch.options) == 2


@pytest.mark.unit
def test_companion_union_picks_branch_when_question_present():
    payload = {
        "kind": "branch",
        "label": "COS",
        "question": "Includes Notice?",
        "options": [
            {"label": "Yes", "child_template_id": "a", "slot_configurations": {}},
            {"label": "No", "child_template_id": "b", "slot_configurations": {}},
        ],
    }
    result = _COMPANION_ADAPTER.validate_python(payload)
    assert isinstance(result, BranchBundleCompanion)


@pytest.mark.unit
def test_companion_union_picks_fixed_when_kind_fixed():
    payload = {
        "kind": "fixed",
        "label": "Cover",
        "child_template_id": "tpl_cover",
    }
    result = _COMPANION_ADAPTER.validate_python(payload)
    assert isinstance(result, FixedBundleCompanion)


# ─── AgentConfig.bundle_role ─────────────────────────────────────────


@pytest.mark.unit
def test_agent_config_bundle_role_defaults_to_standalone():
    from src.core.agents.types.spec import AgentConfig

    cfg = AgentConfig(template_id="tpl_x", template_fields=[])
    assert cfg.bundle_role == TemplateBundleRole.STANDALONE


@pytest.mark.unit
def test_agent_config_bundle_role_accepts_explicit_value():
    from src.core.agents.types.spec import AgentConfig

    cfg = AgentConfig(
        template_id="tpl_x",
        template_fields=[],
        bundle_role=TemplateBundleRole.PARENT,
    )
    assert cfg.bundle_role == TemplateBundleRole.PARENT
