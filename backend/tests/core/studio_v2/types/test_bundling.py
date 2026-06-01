"""Tests for TemplateConfigV2 + bundling discriminated unions."""

import pytest
from pydantic import ValidationError

from src.core.studio_v2.types.bundling import (
    BranchCompanion,
    BranchOption,
    ExtractFromDraftSlotConfig,
    FixedCompanion,
    LiteralSlotConfig,
    ParentVariableSlotConfig,
    TemplateConfigV2,
    TemplateRole,
)


@pytest.mark.unit
def test_default_template_config_is_standalone_no_companions():
    cfg = TemplateConfigV2()
    assert cfg.role == TemplateRole.SINGLE
    assert cfg.companions == []


@pytest.mark.unit
@pytest.mark.parametrize("role", list(TemplateRole))
def test_every_role_round_trips(role: TemplateRole):
    cfg = TemplateConfigV2(role=role)
    raw = cfg.model_dump_json()
    restored = TemplateConfigV2.model_validate_json(raw)
    assert restored.role == role


@pytest.mark.unit
def test_fixed_companion_round_trips_with_slot_configs():
    cfg = TemplateConfigV2(
        role=TemplateRole.MASTER,
        companions=[
            FixedCompanion(
                id="cmp-1",
                label="Creditor letter",
                child_template_id="tpl-creditor-letter",
                slot_configurations={
                    "debtor_name": ParentVariableSlotConfig(
                        parent_variable="debtor_name",
                    ),
                    "claim_amount": LiteralSlotConfig(literal_value="TBD"),
                    "service_address": ExtractFromDraftSlotConfig(
                        extract_instruction="pull the recipient's mailing address",
                    ),
                },
            ),
        ],
    )
    raw = cfg.model_dump_json()
    restored = TemplateConfigV2.model_validate_json(raw)
    assert len(restored.companions) == 1
    companion = restored.companions[0]
    assert isinstance(companion, FixedCompanion)
    assert companion.kind == "fixed"
    assert companion.child_template_id == "tpl-creditor-letter"

    debtor_slot = companion.slot_configurations["debtor_name"]
    assert isinstance(debtor_slot, ParentVariableSlotConfig)
    assert debtor_slot.parent_variable == "debtor_name"

    claim_slot = companion.slot_configurations["claim_amount"]
    assert isinstance(claim_slot, LiteralSlotConfig)
    assert claim_slot.literal_value == "TBD"

    service_slot = companion.slot_configurations["service_address"]
    assert isinstance(service_slot, ExtractFromDraftSlotConfig)
    assert service_slot.extract_instruction.startswith("pull")


@pytest.mark.unit
def test_branch_companion_round_trips_with_options():
    cfg = TemplateConfigV2(
        role=TemplateRole.MASTER,
        companions=[
            BranchCompanion(
                id="cmp-2",
                label="Filing path",
                question="Is the debtor pro se?",
                options=[
                    BranchOption(
                        id="opt-yes",
                        option_label="Yes",
                        child_template_id="tpl-pro-se-cover",
                    ),
                    BranchOption(
                        id="opt-no",
                        option_label="No",
                        child_template_id="tpl-attorney-cover",
                        slot_configurations={
                            "attorney_name": ParentVariableSlotConfig(
                                parent_variable="attorney_name",
                            ),
                        },
                    ),
                ],
            ),
        ],
    )
    raw = cfg.model_dump_json()
    restored = TemplateConfigV2.model_validate_json(raw)
    companion = restored.companions[0]
    assert isinstance(companion, BranchCompanion)
    assert companion.kind == "branch"
    assert companion.question == "Is the debtor pro se?"
    assert len(companion.options) == 2
    assert companion.options[0].child_template_id == "tpl-pro-se-cover"
    no_slot = companion.options[1].slot_configurations["attorney_name"]
    assert isinstance(no_slot, ParentVariableSlotConfig)


@pytest.mark.unit
def test_discriminator_picks_right_slot_kind_on_deserialization():
    """The kind discriminator must drive parsing — a parent_variable
    JSON payload should NOT validate as a LiteralSlotConfig even if
    field names happen to overlap."""
    payload = '{"kind": "literal", "literal_value": "hello"}'
    cfg = TemplateConfigV2.model_validate_json(
        '{"role": "master", "companions": ['
        '  {"kind": "fixed", "id": "x", "label": "y", "child_template_id": null,'
        f'   "slot_configurations": {{"v": {payload}}}}}'
        ']}'
    )
    slot = cfg.companions[0].slot_configurations["v"]
    assert isinstance(slot, LiteralSlotConfig)
    assert slot.literal_value == "hello"


@pytest.mark.unit
def test_companion_discriminator_picks_right_kind():
    cfg = TemplateConfigV2.model_validate_json(
        '{"role": "master", "companions": ['
        '  {"kind": "branch", "id": "b", "label": "B", "question": "Q?", "options": []}'
        ']}'
    )
    assert isinstance(cfg.companions[0], BranchCompanion)


@pytest.mark.unit
def test_unknown_slot_kind_rejected():
    with pytest.raises(ValidationError):
        TemplateConfigV2.model_validate_json(
            '{"role": "master", "companions": ['
            '  {"kind": "fixed", "id": "x", "label": "y", "child_template_id": null,'
            '   "slot_configurations": {"v": {"kind": "made_up", "x": 1}}}'
            ']}'
        )
