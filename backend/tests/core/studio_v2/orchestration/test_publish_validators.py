"""Tests for the Phase 3 publish-gate validator suite.

Covers every helper inside `validate_for_publish`:
- _validate_dependent_variable_references_v2
- _validate_query_dependencies_v2
- _validate_no_resolution_cycles_v2
- _validate_virtual_parents_have_children_v2
- _validate_user_input_label_required_v2
- _validate_constants_short_codes_exist_v2 (async, DB mocked)
- _validate_attorney_ids_exist_v2 (async, DB mocked)
- assert_part_of_packet_has_no_user_input_v2 re-run safety net

Plus end-to-end `validate_for_publish` aggregation: every check feeds
into the same list and order is preserved.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.core.studio_v2.orchestration.validators import (
    _validate_attorney_ids_exist_v2,
    _validate_constants_short_codes_exist_v2,
    _validate_dependent_variable_references_v2,
    _validate_no_resolution_cycles_v2,
    _validate_query_dependencies_v2,
    _validate_user_input_label_required_v2,
    _validate_virtual_parents_have_children_v2,
    validate_for_publish,
)
from src.core.studio_v2.types.fields import TemplateFieldV2
from src.core.studio_v2.types.wizard_sources import (
    AuthorInputKind,
    PresentationShape,
    SourceKind,
    WizardSourceParams,
)


_TEMPLATE_UUID = "00000000-0000-0000-0000-000000000001"
_FIELD_UUID = "00000000-0000-0000-0000-000000000002"


def _field(name, params, *, template_property_marker="X"):
    return TemplateFieldV2(
        id=_FIELD_UUID, template_id=_TEMPLATE_UUID,
        template_variable=name, template_property_marker=template_property_marker,
        params=params,
    )


def _derive_params(parent):
    return WizardSourceParams(
        source=SourceKind.DERIVED_FROM_VARIABLE,
        dependent_variable=parent,
        extraction_prompt="ignored for these tests",
    )


def _gmail_raw_params(query_deps=None):
    return WizardSourceParams(
        source=SourceKind.GMAIL,
        presentation_shape=PresentationShape.RAW,
        extraction_prompt="x",
        query_dependencies=query_deps or [],
    )


# ─── dependent_variable references ─────────────────────────────────


@pytest.mark.unit
def test_derive_with_missing_parent_errors():
    errors: list[str] = []
    _validate_dependent_variable_references_v2(
        [_field("child", _derive_params("ghost"))],
        errors,
    )
    assert any("does not exist" in e for e in errors)


@pytest.mark.unit
def test_derive_with_self_reference_errors():
    errors: list[str] = []
    _validate_dependent_variable_references_v2(
        [_field("loop", _derive_params("loop"))],
        errors,
    )
    assert any("cannot be based on itself" in e for e in errors)


@pytest.mark.unit
def test_derive_with_empty_parent_errors():
    errors: list[str] = []
    field = TemplateFieldV2(
        id=_FIELD_UUID, template_id=_TEMPLATE_UUID,
        template_variable="orphan",
        template_property_marker="X",
        params=WizardSourceParams(
            source=SourceKind.DERIVED_FROM_VARIABLE,
            dependent_variable=None,
        ),
    )
    _validate_dependent_variable_references_v2([field], errors)
    assert any("no parent field is selected" in e for e in errors)


@pytest.mark.unit
def test_derive_with_valid_parent_passes():
    errors: list[str] = []
    parent = _field("anchor", _gmail_raw_params())
    child = _field("child", _derive_params("anchor"))
    _validate_dependent_variable_references_v2([parent, child], errors)
    assert errors == []


# ─── query_dependencies ────────────────────────────────────────────


@pytest.mark.unit
def test_query_dep_missing_variable_errors():
    errors: list[str] = []
    _validate_query_dependencies_v2(
        [_field("a", _gmail_raw_params(query_deps=["missing"]))],
        errors,
    )
    assert any("'missing' as a query dependency" in e for e in errors)


@pytest.mark.unit
def test_query_dep_self_errors():
    errors: list[str] = []
    _validate_query_dependencies_v2(
        [_field("a", _gmail_raw_params(query_deps=["a"]))],
        errors,
    )
    assert any("cannot reference itself" in e for e in errors)


@pytest.mark.unit
def test_query_dep_valid_reference_passes():
    errors: list[str] = []
    other = _field("b", _gmail_raw_params())
    field = _field("a", _gmail_raw_params(query_deps=["b"]))
    _validate_query_dependencies_v2([other, field], errors)
    assert errors == []


# ─── cycle detection ───────────────────────────────────────────────


@pytest.mark.unit
def test_cycle_between_derives_detected():
    """a → b → a via derive chain."""
    errors: list[str] = []
    _validate_no_resolution_cycles_v2(
        [
            _field("a", _derive_params("b")),
            _field("b", _derive_params("a")),
        ],
        errors,
    )
    assert any("cycle detected" in e.lower() for e in errors)


@pytest.mark.unit
def test_cycle_through_query_dependencies_detected():
    """a's query_deps reference b; b derives from a."""
    errors: list[str] = []
    _validate_no_resolution_cycles_v2(
        [
            _field("a", _gmail_raw_params(query_deps=["b"])),
            _field("b", _derive_params("a")),
        ],
        errors,
    )
    assert any("cycle detected" in e.lower() for e in errors)


@pytest.mark.unit
def test_acyclic_chain_passes():
    """a (no deps) ← b derives from a ← c derives from b."""
    errors: list[str] = []
    _validate_no_resolution_cycles_v2(
        [
            _field("a", _gmail_raw_params()),
            _field("b", _derive_params("a")),
            _field("c", _derive_params("b")),
        ],
        errors,
    )
    assert errors == []


# ─── virtual parents ───────────────────────────────────────────────


@pytest.mark.unit
def test_virtual_parent_without_children_errors():
    errors: list[str] = []
    field = TemplateFieldV2(
        id=_FIELD_UUID, template_id=_TEMPLATE_UUID,
        template_variable="orphan_virtual",
        template_property_marker=None,  # virtual
        params=None,
    )
    _validate_virtual_parents_have_children_v2([field], errors)
    assert any("orphan_virtual" in e for e in errors)


@pytest.mark.unit
def test_virtual_parent_with_derived_child_passes():
    errors: list[str] = []
    parent = TemplateFieldV2(
        id=_FIELD_UUID, template_id=_TEMPLATE_UUID,
        template_variable="record",
        template_property_marker=None,
        params=None,
    )
    child = _field("vin", _derive_params("record"))
    _validate_virtual_parents_have_children_v2([parent, child], errors)
    assert errors == []


# ─── user-input label required ─────────────────────────────────────


@pytest.mark.unit
def test_author_input_without_label_errors():
    field = _field(
        "narrative",
        WizardSourceParams(
            source=SourceKind.AUTHOR_INPUT,
            author_input_kind=AuthorInputKind.PLAIN_TEXT,
            label=None,
        ),
    )
    errors: list[str] = []
    _validate_user_input_label_required_v2([field], errors)
    assert any("question prompt" in e for e in errors)


@pytest.mark.unit
def test_dropdown_without_label_errors():
    field = _field(
        "creditor",
        WizardSourceParams(
            source=SourceKind.GMAIL,
            presentation_shape=PresentationShape.DROPDOWN,
            extraction_prompt="x",
            label="   ",  # whitespace-only
        ),
    )
    errors: list[str] = []
    _validate_user_input_label_required_v2([field], errors)
    assert any("question prompt" in e for e in errors)


@pytest.mark.unit
def test_raw_extractor_without_label_passes():
    """RAW shape doesn't need a label — no draft-time picker."""
    field = _field("x", _gmail_raw_params())
    errors: list[str] = []
    _validate_user_input_label_required_v2([field], errors)
    assert errors == []


# ─── async DB validators ───────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
async def test_constants_short_code_missing_errors():
    field = _field(
        "firm_addr",
        WizardSourceParams(
            source=SourceKind.CONSTANTS,
            constants_short_code="MISSING_CODE",
        ),
    )
    fake_rows = [SimpleNamespace(short_code="FIRM_ADDRESS")]
    with patch(
        "src.core.studio_v2.orchestration.validators.ReferenceDataRepository.list",
        new=AsyncMock(return_value=fake_rows),
    ):
        errors: list[str] = []
        await _validate_constants_short_codes_exist_v2([field], errors)
    assert any("MISSING_CODE" in e for e in errors)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_constants_short_code_unset_errors():
    field = _field(
        "firm_addr",
        WizardSourceParams(
            source=SourceKind.CONSTANTS,
            constants_short_code=None,
        ),
    )
    errors: list[str] = []
    await _validate_constants_short_codes_exist_v2([field], errors)
    assert any("no constant is picked" in e for e in errors)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_constants_short_code_present_passes():
    field = _field(
        "firm_addr",
        WizardSourceParams(
            source=SourceKind.CONSTANTS,
            constants_short_code="FIRM_ADDRESS",
        ),
    )
    fake_rows = [SimpleNamespace(short_code="FIRM_ADDRESS")]
    with patch(
        "src.core.studio_v2.orchestration.validators.ReferenceDataRepository.list",
        new=AsyncMock(return_value=fake_rows),
    ):
        errors: list[str] = []
        await _validate_constants_short_codes_exist_v2([field], errors)
    assert errors == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_attorney_id_missing_errors():
    field = _field(
        "atty",
        WizardSourceParams(
            source=SourceKind.ATTORNEY,
            presentation_shape=PresentationShape.RAW,
            attorney_id="ghost_id",
        ),
    )
    fake_roster = [SimpleNamespace(id="real_id")]
    with patch(
        "src.core.studio_v2.orchestration.validators.AttorneyRosterRepository.list",
        new=AsyncMock(return_value=fake_roster),
    ):
        errors: list[str] = []
        await _validate_attorney_ids_exist_v2([field], errors)
    assert any("ghost_id" in e for e in errors)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_attorney_dropdown_shape_is_not_validated():
    """Pickable shape leaves attorney_id empty by design — no error."""
    field = _field(
        "atty",
        WizardSourceParams(
            source=SourceKind.ATTORNEY,
            presentation_shape=PresentationShape.DROPDOWN,
            attorney_id=None,
            label="Pick the attorney",
        ),
    )
    errors: list[str] = []
    await _validate_attorney_ids_exist_v2([field], errors)
    assert errors == []


# ─── validate_for_publish aggregation ──────────────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
async def test_validate_for_publish_aggregates_errors():
    """Multiple distinct errors all surface in one list."""
    parent = _field("a", _derive_params("a"))  # self-reference
    child = _field("b", _gmail_raw_params(query_deps=["b"]))  # self-reference
    fields = [parent, child]
    with patch(
        "src.core.studio_v2.orchestration.validators.ReferenceDataRepository.list",
        new=AsyncMock(return_value=[]),
    ), patch(
        "src.core.studio_v2.orchestration.validators.AttorneyRosterRepository.list",
        new=AsyncMock(return_value=[]),
    ):
        errors = await validate_for_publish(fields)
    # Expect at least one error from each per-edge validator.
    assert any("cannot be based on itself" in e for e in errors)
    assert any("cannot reference itself" in e for e in errors)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_validate_for_publish_clean_spec_returns_empty():
    """A well-formed spec returns no errors (role=single, user-input ok)."""
    fields = [
        _field("debtor_name", _gmail_raw_params()),
        _field(
            "creditor_pick",
            WizardSourceParams(
                source=SourceKind.GMAIL,
                presentation_shape=PresentationShape.DROPDOWN,
                extraction_prompt="x",
                label="Pick the creditor",
            ),
        ),
    ]
    with patch(
        "src.core.studio_v2.orchestration.validators.ReferenceDataRepository.list",
        new=AsyncMock(return_value=[]),
    ), patch(
        "src.core.studio_v2.orchestration.validators.AttorneyRosterRepository.list",
        new=AsyncMock(return_value=[]),
    ):
        errors = await validate_for_publish(fields, role="single")
    assert errors == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_companion_role_blocks_user_input_fields():
    """role=part_of_packet rejects any user-input field."""
    fields = [
        _field("debtor_name", _gmail_raw_params()),
        _field(
            "creditor_pick",
            WizardSourceParams(
                source=SourceKind.GMAIL,
                presentation_shape=PresentationShape.DROPDOWN,
                extraction_prompt="x",
                label="Pick the creditor",
            ),
        ),
    ]
    with patch(
        "src.core.studio_v2.orchestration.validators.ReferenceDataRepository.list",
        new=AsyncMock(return_value=[]),
    ), patch(
        "src.core.studio_v2.orchestration.validators.AttorneyRosterRepository.list",
        new=AsyncMock(return_value=[]),
    ):
        errors = await validate_for_publish(fields, role="part_of_packet")
    assert any("Companion templates cannot include" in e for e in errors)
    assert any("creditor_pick" in e for e in errors)
