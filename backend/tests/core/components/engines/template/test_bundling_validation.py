"""Tests for the bundle-companion slot validators on `update_template_bundling_config`.

Covers:
- `_is_slot_config_complete` — the per-variant completeness rule (literal allows
  empty; the other two require non-empty payload).
- `_slots_required_for_child` — pulls only `inherit_from_parent` variables.
- `_validate_companion_slots` — reports missing keys + incomplete configs with
  clear messages so the FE can show every problem in one shot.
- Integration: `update_template_bundling_config` rejects a parent with any
  incomplete companion via HTTPException(400, code='BUNDLE_SLOTS_INCOMPLETE').
"""

from unittest.mock import AsyncMock
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from src.core.agents.types.bundling import (
    BranchBundleCompanion,
    BranchOption,
    ExtractFromDraftSlotConfig,
    FixedBundleCompanion,
    LiteralSlotConfig,
    ParentVariableSlotConfig,
)
from src.core.components.engines.template import crud as crud_module
from src.core.components.engines.template.crud import (
    _is_slot_config_complete,
    _slots_required_for_child,
    _validate_companion_slots,
    update_template_bundling_config,
)


# ─── _is_slot_config_complete ──────────────────────────────────────────


@pytest.mark.unit
def test_parent_variable_complete_when_non_empty():
    assert _is_slot_config_complete(
        ParentVariableSlotConfig(parent_variable="case_number")
    ) is True


@pytest.mark.unit
def test_parent_variable_incomplete_when_empty_or_whitespace():
    assert _is_slot_config_complete(ParentVariableSlotConfig(parent_variable="")) is False
    assert _is_slot_config_complete(ParentVariableSlotConfig(parent_variable="   ")) is False


@pytest.mark.unit
def test_extract_from_draft_complete_when_non_empty():
    assert _is_slot_config_complete(
        ExtractFromDraftSlotConfig(extract_instruction="Pull the docket title")
    ) is True


@pytest.mark.unit
def test_extract_from_draft_incomplete_when_blank():
    assert _is_slot_config_complete(ExtractFromDraftSlotConfig(extract_instruction="")) is False
    assert _is_slot_config_complete(ExtractFromDraftSlotConfig(extract_instruction="   ")) is False


@pytest.mark.unit
def test_literal_always_complete_even_when_empty():
    """`literal` is deliberately permitted to be empty — empty literal is a
    valid choice (e.g. caller wants a blank line)."""
    assert _is_slot_config_complete(LiteralSlotConfig(literal_value="")) is True
    assert _is_slot_config_complete(LiteralSlotConfig(literal_value="foo")) is True


# ─── _slots_required_for_child ────────────────────────────────────────


@pytest.mark.unit
def test_slots_required_for_child_handles_none_and_empty():
    assert _slots_required_for_child(None) == []
    assert _slots_required_for_child([]) == []


@pytest.mark.unit
def test_slots_required_for_child_filters_to_inherit_from_parent_only():
    spec = [
        {"template_variable": "case_no", "source": "inherit_from_parent"},
        {"template_variable": "firm", "source": "constants"},
        {"template_variable": "docket_title", "source": "inherit_from_parent"},
        {"template_variable": "ignored_no_source"},
        {"source": "inherit_from_parent"},  # missing template_variable — drop
    ]
    assert _slots_required_for_child(spec) == ["case_no", "docket_title"]


# ─── _validate_companion_slots ────────────────────────────────────────


@pytest.fixture
def stub_child_template_lookup(monkeypatch):
    """Stub DraftTemplateRepository.get so tests can hand-roll child specs."""

    def _install(specs_by_id: dict[str, list | None]):
        async def _get(template_id):
            if template_id not in specs_by_id:
                return None
            return SimpleNamespace(id=template_id, template_spec=specs_by_id[template_id])

        monkeypatch.setattr(
            crud_module.DraftTemplateRepository,
            "get",
            AsyncMock(side_effect=_get),
        )

    return _install


@pytest.mark.unit
async def test_validate_companion_slots_reports_missing_child_template(
    stub_child_template_lookup,
):
    stub_child_template_lookup({})  # any child_template_id misses
    errors = await _validate_companion_slots(
        label="Cover Sheet",
        child_template_id="nope",
        slot_configurations={},
    )
    assert len(errors) == 1
    assert "Cover Sheet" in errors[0]
    assert "nope" in errors[0]


@pytest.mark.unit
async def test_validate_companion_slots_passes_when_all_slots_complete(
    stub_child_template_lookup,
):
    stub_child_template_lookup({
        "tpl-child": [
            {"template_variable": "case_no", "source": "inherit_from_parent"},
            {"template_variable": "docket_title", "source": "inherit_from_parent"},
        ],
    })
    errors = await _validate_companion_slots(
        label="Cover Sheet",
        child_template_id="tpl-child",
        slot_configurations={
            "case_no": ParentVariableSlotConfig(parent_variable="case_number"),
            "docket_title": ExtractFromDraftSlotConfig(
                extract_instruction="Pull the bold heading",
            ),
        },
    )
    assert errors == []


@pytest.mark.unit
async def test_validate_companion_slots_flags_missing_key(stub_child_template_lookup):
    stub_child_template_lookup({
        "tpl-child": [
            {"template_variable": "case_no", "source": "inherit_from_parent"},
            {"template_variable": "docket_title", "source": "inherit_from_parent"},
        ],
    })
    errors = await _validate_companion_slots(
        label="Cover Sheet",
        child_template_id="tpl-child",
        slot_configurations={
            "case_no": ParentVariableSlotConfig(parent_variable="case_number"),
            # docket_title intentionally omitted
        },
    )
    assert len(errors) == 1
    assert "docket_title" in errors[0]
    assert "missing" in errors[0].lower()


@pytest.mark.unit
async def test_validate_companion_slots_flags_incomplete_payload(
    stub_child_template_lookup,
):
    stub_child_template_lookup({
        "tpl-child": [
            {"template_variable": "case_no", "source": "inherit_from_parent"},
        ],
    })
    errors = await _validate_companion_slots(
        label="Cover Sheet",
        child_template_id="tpl-child",
        slot_configurations={
            "case_no": ParentVariableSlotConfig(parent_variable=""),
        },
    )
    assert len(errors) == 1
    assert "case_no" in errors[0]
    assert "parent_variable" in errors[0]
    assert "incomplete" in errors[0].lower()


@pytest.mark.unit
async def test_validate_companion_slots_aggregates_multiple_errors(
    stub_child_template_lookup,
):
    """Authors should see EVERY problem in one shot, not one-at-a-time."""
    stub_child_template_lookup({
        "tpl-child": [
            {"template_variable": "case_no", "source": "inherit_from_parent"},
            {"template_variable": "docket_title", "source": "inherit_from_parent"},
            {"template_variable": "filing_date", "source": "inherit_from_parent"},
        ],
    })
    errors = await _validate_companion_slots(
        label="Cover Sheet",
        child_template_id="tpl-child",
        slot_configurations={
            "case_no": ParentVariableSlotConfig(parent_variable=""),  # incomplete
            "docket_title": ExtractFromDraftSlotConfig(extract_instruction="   "),  # incomplete
            # filing_date missing entirely
        },
    )
    assert len(errors) == 3


@pytest.mark.unit
async def test_validate_companion_slots_skips_non_inherit_variables(
    stub_child_template_lookup,
):
    """A CONSTANTS-sourced or autoderived variable is NOT a slot the parent fills."""
    stub_child_template_lookup({
        "tpl-child": [
            {"template_variable": "firm", "source": "constants"},
            {"template_variable": "computed", "source": "auto_derived"},
        ],
    })
    errors = await _validate_companion_slots(
        label="Cover Sheet",
        child_template_id="tpl-child",
        slot_configurations={},  # nothing required
    )
    assert errors == []


# ─── update_template_bundling_config (integration) ────────────────────


@pytest.fixture
def stub_parent_template_exists(monkeypatch):
    """Make DraftTemplateRepository.get return a parent template, then route
    subsequent lookups (children) through a `child_specs` map."""

    def _install(parent_id: str, child_specs: dict[str, list | None]):
        async def _get(template_id):
            if template_id == parent_id:
                return SimpleNamespace(id=parent_id, template_spec=None)
            if template_id in child_specs:
                return SimpleNamespace(id=template_id, template_spec=child_specs[template_id])
            return None

        monkeypatch.setattr(
            crud_module.DraftTemplateRepository,
            "get",
            AsyncMock(side_effect=_get),
        )

    return _install


@pytest.mark.unit
async def test_update_bundling_rejects_parent_with_incomplete_fixed_companion(
    monkeypatch, stub_parent_template_exists,
):
    stub_parent_template_exists(
        "parent-1",
        {"tpl-child": [
            {"template_variable": "case_no", "source": "inherit_from_parent"},
        ]},
    )
    # Update is a side-effect; not relevant to this test.
    monkeypatch.setattr(
        crud_module.DraftTemplateRepository, "update", AsyncMock(return_value=None)
    )

    with pytest.raises(HTTPException) as exc_info:
        await update_template_bundling_config(
            "parent-1",
            "parent",
            [
                FixedBundleCompanion(
                    label="Cover Sheet",
                    child_template_id="tpl-child",
                    slot_configurations={
                        "case_no": ParentVariableSlotConfig(parent_variable=""),
                    },
                )
            ],
        )
    assert exc_info.value.status_code == 400
    detail = exc_info.value.detail
    assert detail["code"] == "BUNDLE_SLOTS_INCOMPLETE"
    assert any("case_no" in e for e in detail["errors"])


@pytest.mark.unit
async def test_update_bundling_rejects_parent_with_incomplete_branch_option(
    monkeypatch, stub_parent_template_exists,
):
    stub_parent_template_exists(
        "parent-1",
        {
            "tpl-yes": [
                {"template_variable": "case_no", "source": "inherit_from_parent"},
            ],
            "tpl-no": [
                {"template_variable": "case_no", "source": "inherit_from_parent"},
                {"template_variable": "docket_title", "source": "inherit_from_parent"},
            ],
        },
    )
    monkeypatch.setattr(
        crud_module.DraftTemplateRepository, "update", AsyncMock(return_value=None)
    )

    with pytest.raises(HTTPException) as exc_info:
        await update_template_bundling_config(
            "parent-1",
            "parent",
            [
                BranchBundleCompanion(
                    label="Notice of Hearing",
                    question="Does this case need a Notice of Hearing?",
                    options=[
                        BranchOption(
                            label="Yes",
                            child_template_id="tpl-yes",
                            slot_configurations={
                                "case_no": ParentVariableSlotConfig(parent_variable="case_number"),
                            },
                        ),
                        BranchOption(
                            label="No",
                            child_template_id="tpl-no",
                            slot_configurations={
                                "case_no": ParentVariableSlotConfig(parent_variable="case_number"),
                                # docket_title missing
                            },
                        ),
                    ],
                )
            ],
        )
    detail = exc_info.value.detail
    assert detail["code"] == "BUNDLE_SLOTS_INCOMPLETE"
    # Branch labels are nested under the parent label for the error message.
    assert any("Notice of Hearing → No" in e and "docket_title" in e for e in detail["errors"])


@pytest.mark.unit
async def test_update_bundling_accepts_complete_parent(
    monkeypatch, stub_parent_template_exists,
):
    """Happy path: every required slot is set; persistence should proceed."""
    stub_parent_template_exists(
        "parent-1",
        {"tpl-child": [
            {"template_variable": "case_no", "source": "inherit_from_parent"},
        ]},
    )
    # Stub the update + response builder side of the function so the test is hermetic.
    updated_template = SimpleNamespace(
        id="parent-1",
        template_spec=None,
        bundle_role="parent",
        bundle_companions=[],
    )
    monkeypatch.setattr(
        crud_module.DraftTemplateRepository,
        "update",
        AsyncMock(return_value=updated_template),
    )
    monkeypatch.setattr(
        crud_module,
        "_build_template_response",
        AsyncMock(return_value="OK_RESPONSE"),
    )

    result = await update_template_bundling_config(
        "parent-1",
        "parent",
        [
            FixedBundleCompanion(
                label="Cover Sheet",
                child_template_id="tpl-child",
                slot_configurations={
                    "case_no": ParentVariableSlotConfig(parent_variable="case_number"),
                },
            )
        ],
    )
    assert result == "OK_RESPONSE"


@pytest.mark.unit
async def test_update_bundling_skips_slot_check_for_standalone_and_child_only(
    monkeypatch, stub_parent_template_exists,
):
    """Non-parent roles can't carry companions — the slot validator must not
    even run (otherwise a child_only template with an empty list would falsely
    pass via the early role-check)."""
    stub_parent_template_exists("parent-1", {})
    updated_template = SimpleNamespace(
        id="parent-1",
        template_spec=None,
        bundle_role="standalone",
        bundle_companions=None,
    )
    monkeypatch.setattr(
        crud_module.DraftTemplateRepository,
        "update",
        AsyncMock(return_value=updated_template),
    )
    monkeypatch.setattr(
        crud_module,
        "_build_template_response",
        AsyncMock(return_value="OK_RESPONSE"),
    )

    # Standalone + None companions — no slot validation triggered, no raise.
    result = await update_template_bundling_config("parent-1", "standalone", None)
    assert result == "OK_RESPONSE"


@pytest.mark.unit
async def test_update_bundling_coerces_pydantic_models_to_dicts_for_repository(
    monkeypatch, stub_parent_template_exists,
):
    """Regression: `BundlingConfigUpdateRequest.bundle_companions` is now
    typed as `list[BundleCompanion]`, so FastAPI hands us Pydantic instances.
    The repository persists via `json.dumps(bundle_companions)` and dies if
    those are still model instances — the service layer must `.model_dump()`
    each one before handing off."""
    stub_parent_template_exists(
        "parent-1",
        {"tpl-child": [
            {"template_variable": "case_no", "source": "inherit_from_parent"},
        ]},
    )

    captured: dict = {}

    async def _fake_update(template_id, *, bundle_role, bundle_companions, clear_bundle_companions):
        captured["bundle_companions"] = bundle_companions
        captured["clear"] = clear_bundle_companions
        return SimpleNamespace(
            id=template_id,
            template_spec=None,
            bundle_role=bundle_role,
            bundle_companions=bundle_companions,
        )

    monkeypatch.setattr(
        crud_module.DraftTemplateRepository, "update", AsyncMock(side_effect=_fake_update),
    )
    monkeypatch.setattr(
        crud_module, "_build_template_response", AsyncMock(return_value="OK"),
    )

    await update_template_bundling_config(
        "parent-1",
        "parent",
        [
            FixedBundleCompanion(
                label="Cover Sheet",
                child_template_id="tpl-child",
                slot_configurations={
                    "case_no": ParentVariableSlotConfig(parent_variable="case_number"),
                },
            ),
            BranchBundleCompanion(
                label="Notice of Hearing",
                question="Hearing?",
                options=[
                    BranchOption(
                        label="Yes",
                        child_template_id="tpl-child",
                        slot_configurations={
                            "case_no": ParentVariableSlotConfig(parent_variable="case_number"),
                        },
                    ),
                    BranchOption(
                        label="No",
                        child_template_id="tpl-child",
                        slot_configurations={
                            "case_no": ParentVariableSlotConfig(parent_variable="case_number"),
                        },
                    ),
                ],
            ),
        ],
    )

    # Repository must see plain dicts, NOT Pydantic instances. That's what
    # json.dumps in the repo's UPDATE statement can actually serialize.
    received = captured["bundle_companions"]
    assert isinstance(received, list) and len(received) == 2
    for companion_payload in received:
        assert isinstance(companion_payload, dict), (
            f"Expected dict, got {type(companion_payload).__name__} — service-layer "
            "missed a .model_dump() before persisting."
        )
        assert "kind" in companion_payload
    # Branch option nesting also lands as nested dicts (model_dump is recursive).
    branch = received[1]
    assert all(isinstance(opt, dict) for opt in branch["options"])
    assert captured["clear"] is False
