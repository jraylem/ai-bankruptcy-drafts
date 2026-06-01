"""Tests for template_spec validators.

Covers the one public entry point + its three internal passes:

    validate_template_spec_source_map   — source ↔ source_params type check
    _validate_group_dropdown_references  — anchor / partner referential checks
    _validate_constants_short_codes_exist — CONSTANTS short_code must be known
    _validate_dependent_variable_references — dependent graph checks
"""

from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from src.core.agents.types.sources import (
    AutoDerivedSourceParams,
    CaseVectorSourceParams,
    ConstantsSourceParams,
    DependentOnVariableSourceParams,
    DerivedValueType,
    FieldSource,
    GroupDropdownSourceParams,
    RecoChipsFromDependentVariablesSourceParams,
    RuleEffect,
)
from src.core.common.storage.database import ReferenceDataRepository
from src.core.components.engines.template.validators import (
    _validate_dependent_variable_references,
    _validate_group_dropdown_references,
    validate_template_spec_source_map,
)
from tests.core.factories import (
    make_dropdown_case_vector_source_params,
    make_dropdown_email_source_params,
    make_gmail_source_params,
    make_group_dropdown_source_params,
    make_reco_chips_case_vector_source_params,
    make_reco_chips_source_params,
    make_template_variable,
)


# ─── validate_template_spec_source_map ────────────────────────────────


@pytest.mark.unit
async def test_source_map_accepts_valid_spec(monkeypatch):
    monkeypatch.setattr(ReferenceDataRepository, "list", AsyncMock(return_value=[]))
    spec = [
        make_template_variable(
            template_variable="debtor_email",
            source=FieldSource.GMAIL,
            source_params=make_gmail_source_params(subject_query="debtor"),
        ),
    ]
    await validate_template_spec_source_map(spec)  # no raise = pass


@pytest.mark.unit
async def test_source_map_rejects_missing_source(monkeypatch):
    monkeypatch.setattr(ReferenceDataRepository, "list", AsyncMock(return_value=[]))
    spec = [make_template_variable(template_variable="orphan", source=None)]

    with pytest.raises(HTTPException) as exc:
        await validate_template_spec_source_map(spec)

    errors = exc.value.detail["validation_errors"]
    assert any("'orphan'" in e and "missing source" in e for e in errors)


@pytest.mark.unit
async def test_source_map_allows_group_dropdown_partner_without_source(monkeypatch):
    """Partner variables legitimately have source=None — the anchor fills their
    source at compose time. Validator must not flag these."""
    monkeypatch.setattr(ReferenceDataRepository, "list", AsyncMock(return_value=[]))
    anchor = make_template_variable(
        template_variable="docket_num",
        source=FieldSource.GROUP_DROPDOWN_FROM_GMAIL,
        source_params=make_group_dropdown_source_params(right_partner_variable="docket_title"),
    )
    partner = make_template_variable(template_variable="docket_title", source=None)

    await validate_template_spec_source_map([anchor, partner])  # no raise


@pytest.mark.unit
async def test_source_map_case_vector_needs_no_source_params(monkeypatch):
    monkeypatch.setattr(ReferenceDataRepository, "list", AsyncMock(return_value=[]))
    spec = [
        make_template_variable(
            template_variable="court_doc",
            source=FieldSource.CASE_VECTOR,
            source_params=None,
        ),
    ]
    await validate_template_spec_source_map(spec)  # no raise


@pytest.mark.unit
async def test_source_map_rejects_missing_source_params(monkeypatch):
    monkeypatch.setattr(ReferenceDataRepository, "list", AsyncMock(return_value=[]))
    spec = [
        make_template_variable(
            template_variable="debtor_email",
            source=FieldSource.GMAIL,
            source_params=None,
        ),
    ]

    with pytest.raises(HTTPException) as exc:
        await validate_template_spec_source_map(spec)

    errors = exc.value.detail["validation_errors"]
    assert any("'debtor_email'" in e and "missing source_params" in e for e in errors)


@pytest.mark.unit
async def test_source_map_rejects_wrong_source_params_type(monkeypatch):
    monkeypatch.setattr(ReferenceDataRepository, "list", AsyncMock(return_value=[]))
    spec = [
        make_template_variable(
            template_variable="debtor_email",
            source=FieldSource.GMAIL,
            source_params=ConstantsSourceParams(short_code="FIRM_NAME"),  # wrong shape
        ),
    ]

    with pytest.raises(HTTPException) as exc:
        await validate_template_spec_source_map(spec)

    errors = exc.value.detail["validation_errors"]
    assert any(
        "ConstantsSourceParams" in e and "expected GmailSourceParams" in e for e in errors
    )


@pytest.mark.unit
async def test_source_map_accepts_reco_chips_with_reco_chips_params(monkeypatch):
    monkeypatch.setattr(ReferenceDataRepository, "list", AsyncMock(return_value=[]))
    spec = [
        make_template_variable(
            template_variable="change_in_circumstances",
            source=FieldSource.RECO_CHIPS_FROM_GMAIL,
            source_params=make_reco_chips_source_params(label="Change in Circumstances"),
        ),
    ]
    await validate_template_spec_source_map(spec)  # no raise = pass


@pytest.mark.unit
async def test_source_map_rejects_reco_chips_with_wrong_params(monkeypatch):
    monkeypatch.setattr(ReferenceDataRepository, "list", AsyncMock(return_value=[]))
    spec = [
        make_template_variable(
            template_variable="change_in_circumstances",
            source=FieldSource.RECO_CHIPS_FROM_GMAIL,
            source_params=make_gmail_source_params(subject_query="x"),  # wrong shape
        ),
    ]

    with pytest.raises(HTTPException) as exc:
        await validate_template_spec_source_map(spec)

    errors = exc.value.detail["validation_errors"]
    assert any(
        "GmailSourceParams" in e and "expected RecoChipsEmailSourceParams" in e for e in errors
    )


@pytest.mark.unit
async def test_source_map_accepts_reco_chips_case_vector(monkeypatch):
    monkeypatch.setattr(ReferenceDataRepository, "list", AsyncMock(return_value=[]))
    spec = [
        make_template_variable(
            template_variable="employment_explanation",
            source=FieldSource.RECO_CHIPS_FROM_CASE_VECTOR,
            source_params=make_reco_chips_case_vector_source_params(
                label="Employment Description",
                text_query="employer occupation income",
                example_sentence="The Debtor is employed in a trusted capacity.",
            ),
        ),
    ]
    await validate_template_spec_source_map(spec)  # no raise = pass


@pytest.mark.unit
async def test_source_map_rejects_reco_chips_case_vector_with_wrong_params(monkeypatch):
    monkeypatch.setattr(ReferenceDataRepository, "list", AsyncMock(return_value=[]))
    spec = [
        make_template_variable(
            template_variable="employment_explanation",
            source=FieldSource.RECO_CHIPS_FROM_CASE_VECTOR,
            source_params=make_reco_chips_source_params(label="x"),  # wrong shape (gmail-style)
        ),
    ]

    with pytest.raises(HTTPException) as exc:
        await validate_template_spec_source_map(spec)

    errors = exc.value.detail["validation_errors"]
    assert any(
        "RecoChipsEmailSourceParams" in e and "expected RecoChipsCaseVectorSourceParams" in e
        for e in errors
    )


@pytest.mark.unit
async def test_source_map_accepts_dropdown_email_with_dropdown_params(monkeypatch):
    monkeypatch.setattr(ReferenceDataRepository, "list", AsyncMock(return_value=[]))
    spec = [
        make_template_variable(
            template_variable="motion_type",
            source=FieldSource.DROPDOWN_FROM_GMAIL,
            source_params=make_dropdown_email_source_params(
                label="Motion Type", example_format="Motion to Modify Plan",
            ),
        ),
    ]
    await validate_template_spec_source_map(spec)  # no raise = pass


@pytest.mark.unit
async def test_source_map_accepts_dropdown_case_vector(monkeypatch):
    monkeypatch.setattr(ReferenceDataRepository, "list", AsyncMock(return_value=[]))
    spec = [
        make_template_variable(
            template_variable="motion_type",
            source=FieldSource.DROPDOWN_FROM_CASE_VECTOR,
            source_params=make_dropdown_case_vector_source_params(
                text_query="motion type", label="Motion Type", example_format="Motion to Modify Plan",
            ),
        ),
    ]
    await validate_template_spec_source_map(spec)  # no raise


@pytest.mark.unit
async def test_source_map_rejects_dropdown_with_wrong_params(monkeypatch):
    monkeypatch.setattr(ReferenceDataRepository, "list", AsyncMock(return_value=[]))
    spec = [
        make_template_variable(
            template_variable="motion_type",
            source=FieldSource.DROPDOWN_FROM_CASE_VECTOR,
            source_params=make_gmail_source_params(subject_query="x"),  # wrong shape
        ),
    ]

    with pytest.raises(HTTPException) as exc:
        await validate_template_spec_source_map(spec)

    errors = exc.value.detail["validation_errors"]
    assert any(
        "GmailSourceParams" in e and "expected DropdownCaseVectorSourceParams" in e for e in errors
    )


@pytest.mark.unit
async def test_source_map_rejects_constants_without_short_code(monkeypatch):
    monkeypatch.setattr(ReferenceDataRepository, "list", AsyncMock(return_value=[]))
    spec = [
        make_template_variable(
            template_variable="firm_name",
            source=FieldSource.CONSTANTS,
            source_params=ConstantsSourceParams(short_code=""),
        ),
    ]

    with pytest.raises(HTTPException) as exc:
        await validate_template_spec_source_map(spec)

    errors = exc.value.detail["validation_errors"]
    assert any("requires short_code" in e for e in errors)


# ─── _validate_group_dropdown_references ──────────────────────────────


def _gd_anchor(name: str, partner: str) -> "object":
    return make_template_variable(
        template_variable=name,
        source=FieldSource.GROUP_DROPDOWN_FROM_GMAIL,
        source_params=make_group_dropdown_source_params(right_partner_variable=partner),
    )


@pytest.mark.unit
def test_gd_rejects_self_reference():
    spec = [_gd_anchor("docket_num", partner="docket_num")]
    errors: list[str] = []
    _validate_group_dropdown_references(spec, errors)
    assert any("cannot be its own right_partner_variable" in e for e in errors)


@pytest.mark.unit
def test_gd_rejects_missing_partner():
    spec = [_gd_anchor("docket_num", partner="ghost")]
    errors: list[str] = []
    _validate_group_dropdown_references(spec, errors)
    assert any("'ghost'" in e and "does not exist" in e for e in errors)


@pytest.mark.unit
def test_gd_rejects_partner_with_source():
    anchor = _gd_anchor("docket_num", partner="docket_title")
    partner = make_template_variable(
        template_variable="docket_title",
        source=FieldSource.GMAIL,  # wrong — partner should have source=None
        source_params=make_gmail_source_params(),
    )
    errors: list[str] = []
    _validate_group_dropdown_references([anchor, partner], errors)
    assert any(
        "'docket_title'" in e and "already has a source" in e for e in errors
    )


@pytest.mark.unit
def test_gd_rejects_partner_claimed_by_multiple_anchors():
    a1 = _gd_anchor("anchor_1", partner="shared")
    a2 = _gd_anchor("anchor_2", partner="shared")
    partner = make_template_variable(template_variable="shared", source=None)

    errors: list[str] = []
    _validate_group_dropdown_references([a1, a2, partner], errors)

    assert any(
        "'shared'" in e and "claimed by multiple anchors" in e for e in errors
    )


@pytest.mark.unit
def test_gd_valid_partner_produces_no_error():
    anchor = _gd_anchor("docket_num", partner="docket_title")
    partner = make_template_variable(template_variable="docket_title", source=None)
    errors: list[str] = []
    _validate_group_dropdown_references([anchor, partner], errors)
    assert errors == []


# ─── _validate_dependent_variable_references ──────────────────────────


def _dep(name: str, parent: str):
    return make_template_variable(
        template_variable=name,
        source=FieldSource.DEPENDENT_ON_VARIABLE,
        source_params=DependentOnVariableSourceParams(
            dependent_variable=parent,
            derived_value_type=DerivedValueType.DATE,
            rule_effect=RuleEffect.INCREMENT_BY_DAYS,
            rule_effect_value="14",
        ),
    )


@pytest.mark.unit
def test_dep_rejects_self_reference():
    spec = [_dep("date_due", parent="date_due")]
    errors: list[str] = []
    _validate_dependent_variable_references(spec, errors)
    assert any("cannot depend on itself" in e for e in errors)


@pytest.mark.unit
def test_dep_rejects_missing_parent():
    spec = [_dep("date_due", parent="ghost")]
    errors: list[str] = []
    _validate_dependent_variable_references(spec, errors)
    assert any("'ghost'" in e and "does not exist" in e for e in errors)


@pytest.mark.unit
def test_dep_rejects_chained_dependent():
    """v1 disallows a dependent whose parent is also DEPENDENT_ON_VARIABLE —
    the pipeline does only a single resolution pass."""
    grandparent = make_template_variable(
        template_variable="date_filed",
        source=FieldSource.GMAIL,
        source_params=make_gmail_source_params(),
    )
    parent = _dep("date_shifted", parent="date_filed")
    child = _dep("date_due", parent="date_shifted")

    errors: list[str] = []
    _validate_dependent_variable_references([grandparent, parent, child], errors)

    assert any("chained dependents are not supported" in e for e in errors)


@pytest.mark.unit
def test_dep_valid_chain_produces_no_error():
    parent = make_template_variable(
        template_variable="date_filed",
        source=FieldSource.GMAIL,
        source_params=make_gmail_source_params(),
    )
    child = _dep("date_due", parent="date_filed")

    errors: list[str] = []
    _validate_dependent_variable_references([parent, child], errors)

    assert errors == []


# ─── _validate_constants_short_codes_exist (via full map path) ────────


@pytest.mark.unit
async def test_source_map_rejects_unknown_constants_short_code(monkeypatch):
    """No ref_data rows in the DB — any CONSTANTS short_code fails."""

    class _FakeRef:
        short_code = "FIRM_NAME"

    monkeypatch.setattr(
        ReferenceDataRepository, "list", AsyncMock(return_value=[_FakeRef()])
    )
    spec = [
        make_template_variable(
            template_variable="company",
            source=FieldSource.CONSTANTS,
            source_params=ConstantsSourceParams(short_code="MISSING_CODE"),
        ),
    ]

    with pytest.raises(HTTPException) as exc:
        await validate_template_spec_source_map(spec)

    errors = exc.value.detail["validation_errors"]
    assert any("'MISSING_CODE'" in e and "does not exist" in e for e in errors)


@pytest.mark.unit
async def test_source_map_accepts_known_constants_short_code(monkeypatch):
    class _FakeRef:
        short_code = "FIRM_NAME"

    monkeypatch.setattr(
        ReferenceDataRepository, "list", AsyncMock(return_value=[_FakeRef()])
    )
    spec = [
        make_template_variable(
            template_variable="company",
            source=FieldSource.CONSTANTS,
            source_params=ConstantsSourceParams(short_code="FIRM_NAME"),
        ),
    ]

    await validate_template_spec_source_map(spec)  # no raise


# ─── dropdown_from_constants references ATTORNEYS roster ──────────────


@pytest.mark.unit
async def test_source_map_accepts_dropdown_from_constants_with_known_short_code(monkeypatch):
    """dropdown_from_constants participates in the same short_code-exists
    check as plain constants — both resolve against reference_data."""
    from src.core.agents.types.sources import DropdownFromConstantsSourceParams

    class _FakeRef:
        short_code = "ATTORNEYS"

    monkeypatch.setattr(
        ReferenceDataRepository, "list", AsyncMock(return_value=[_FakeRef()])
    )
    spec = [
        make_template_variable(
            template_variable="signing_attorney",
            source=FieldSource.DROPDOWN_FROM_CONSTANTS,
            source_params=DropdownFromConstantsSourceParams(
                reference_short_code="ATTORNEYS",
                label="Signing Attorney",
            ),
        ),
    ]

    await validate_template_spec_source_map(spec)  # no raise


@pytest.mark.unit
async def test_source_map_rejects_dropdown_from_constants_with_unknown_short_code(monkeypatch):
    from src.core.agents.types.sources import DropdownFromConstantsSourceParams

    monkeypatch.setattr(ReferenceDataRepository, "list", AsyncMock(return_value=[]))
    spec = [
        make_template_variable(
            template_variable="signing_attorney",
            source=FieldSource.DROPDOWN_FROM_CONSTANTS,
            source_params=DropdownFromConstantsSourceParams(
                reference_short_code="NOPE",
                label="x",
            ),
        ),
    ]

    with pytest.raises(HTTPException) as exc:
        await validate_template_spec_source_map(spec)

    errors = exc.value.detail["validation_errors"]
    assert any("'NOPE'" in e and "does not exist" in e for e in errors)


# ─── auto_derived_from_variable ───────────────────────────────────────


@pytest.mark.unit
async def test_source_map_accepts_auto_derived_with_existing_parent(monkeypatch):
    monkeypatch.setattr(ReferenceDataRepository, "list", AsyncMock(return_value=[]))
    spec = [
        make_template_variable(
            template_variable="parent",
            source=FieldSource.GMAIL,
            source_params=make_gmail_source_params(subject_query="x"),
        ),
        make_template_variable(
            template_variable="derived",
            source=FieldSource.AUTO_DERIVED_FROM_VARIABLE,
            source_params=AutoDerivedSourceParams(dependent_variable="parent"),
        ),
    ]
    await validate_template_spec_source_map(spec)  # no raise


@pytest.mark.unit
async def test_source_map_rejects_auto_derived_with_missing_parent(monkeypatch):
    monkeypatch.setattr(ReferenceDataRepository, "list", AsyncMock(return_value=[]))
    spec = [
        make_template_variable(
            template_variable="derived",
            source=FieldSource.AUTO_DERIVED_FROM_VARIABLE,
            source_params=AutoDerivedSourceParams(dependent_variable="ghost"),
        ),
    ]

    with pytest.raises(HTTPException) as exc:
        await validate_template_spec_source_map(spec)

    errors = exc.value.detail["validation_errors"]
    assert any("'derived'" in e and "'ghost'" in e and "does not exist" in e for e in errors)


@pytest.mark.unit
async def test_source_map_rejects_auto_derived_self_reference(monkeypatch):
    monkeypatch.setattr(ReferenceDataRepository, "list", AsyncMock(return_value=[]))
    spec = [
        make_template_variable(
            template_variable="derived",
            source=FieldSource.AUTO_DERIVED_FROM_VARIABLE,
            source_params=AutoDerivedSourceParams(dependent_variable="derived"),
        ),
    ]

    with pytest.raises(HTTPException) as exc:
        await validate_template_spec_source_map(spec)

    errors = exc.value.detail["validation_errors"]
    assert any("'derived'" in e and "auto-derive from itself" in e for e in errors)


@pytest.mark.unit
async def test_source_map_accepts_chained_auto_derive(monkeypatch):
    """A chain `root → middle → leaf` (depth 3) is valid — runtime resolver
    handles it via topological iterative passes."""
    monkeypatch.setattr(ReferenceDataRepository, "list", AsyncMock(return_value=[]))
    spec = [
        make_template_variable(
            template_variable="root",
            source=FieldSource.GMAIL,
            source_params=make_gmail_source_params(subject_query="x"),
        ),
        make_template_variable(
            template_variable="middle",
            source=FieldSource.AUTO_DERIVED_FROM_VARIABLE,
            source_params=AutoDerivedSourceParams(dependent_variable="root"),
        ),
        make_template_variable(
            template_variable="leaf",
            source=FieldSource.AUTO_DERIVED_FROM_VARIABLE,
            source_params=AutoDerivedSourceParams(dependent_variable="middle"),
        ),
    ]
    spec[1].read_only = True
    spec[2].read_only = True

    await validate_template_spec_source_map(spec)  # no raise


@pytest.mark.unit
async def test_source_map_rejects_two_node_auto_derive_cycle(monkeypatch):
    """A cycle `A → B → A` errors with the cycle members named."""
    monkeypatch.setattr(ReferenceDataRepository, "list", AsyncMock(return_value=[]))
    spec = [
        make_template_variable(
            template_variable="alpha",
            source=FieldSource.AUTO_DERIVED_FROM_VARIABLE,
            source_params=AutoDerivedSourceParams(dependent_variable="beta"),
        ),
        make_template_variable(
            template_variable="beta",
            source=FieldSource.AUTO_DERIVED_FROM_VARIABLE,
            source_params=AutoDerivedSourceParams(dependent_variable="alpha"),
        ),
    ]
    spec[0].read_only = True
    spec[1].read_only = True

    with pytest.raises(HTTPException) as exc:
        await validate_template_spec_source_map(spec)

    errors = exc.value.detail["validation_errors"]
    assert any("cycle" in e.lower() and "alpha" in e and "beta" in e for e in errors)


@pytest.mark.unit
async def test_source_map_rejects_three_node_auto_derive_cycle(monkeypatch):
    """A longer cycle `A → B → C → A` is also caught and named."""
    monkeypatch.setattr(ReferenceDataRepository, "list", AsyncMock(return_value=[]))
    spec = [
        make_template_variable(
            template_variable="a",
            source=FieldSource.AUTO_DERIVED_FROM_VARIABLE,
            source_params=AutoDerivedSourceParams(dependent_variable="b"),
        ),
        make_template_variable(
            template_variable="b",
            source=FieldSource.AUTO_DERIVED_FROM_VARIABLE,
            source_params=AutoDerivedSourceParams(dependent_variable="c"),
        ),
        make_template_variable(
            template_variable="c",
            source=FieldSource.AUTO_DERIVED_FROM_VARIABLE,
            source_params=AutoDerivedSourceParams(dependent_variable="a"),
        ),
    ]
    for v in spec:
        v.read_only = True

    with pytest.raises(HTTPException) as exc:
        await validate_template_spec_source_map(spec)

    errors = exc.value.detail["validation_errors"]
    cycle_msgs = [e for e in errors if "cycle" in e.lower()]
    assert cycle_msgs, "expected a cycle error"
    assert "a" in cycle_msgs[0] and "b" in cycle_msgs[0] and "c" in cycle_msgs[0]


@pytest.mark.unit
async def test_source_map_rejects_read_only_on_non_auto_derived(monkeypatch):
    """read_only=true is only valid alongside auto_derived_from_variable source."""
    monkeypatch.setattr(ReferenceDataRepository, "list", AsyncMock(return_value=[]))
    spec = [
        make_template_variable(
            template_variable="bad",
            source=FieldSource.GMAIL,
            source_params=make_gmail_source_params(subject_query="x"),
        ),
    ]
    spec[0].read_only = True

    with pytest.raises(HTTPException) as exc:
        await validate_template_spec_source_map(spec)

    errors = exc.value.detail["validation_errors"]
    assert any("'bad'" in e and "read_only" in e for e in errors)


@pytest.mark.unit
async def test_source_map_accepts_read_only_on_auto_derived(monkeypatch):
    monkeypatch.setattr(ReferenceDataRepository, "list", AsyncMock(return_value=[]))
    spec = [
        make_template_variable(
            template_variable="parent",
            source=FieldSource.GMAIL,
            source_params=make_gmail_source_params(),
        ),
        make_template_variable(
            template_variable="derived",
            source=FieldSource.AUTO_DERIVED_FROM_VARIABLE,
            source_params=AutoDerivedSourceParams(dependent_variable="parent"),
        ),
    ]
    spec[1].read_only = True

    await validate_template_spec_source_map(spec)  # no raise


# ─── _validate_virtual_variables_have_dependents ──────────────────────


@pytest.mark.unit
async def test_source_map_rejects_virtual_with_no_auto_derive_child(monkeypatch):
    """Virtual variable (template_variable_string=None) without an
    auto_derive child is dead data — validator must error."""
    monkeypatch.setattr(ReferenceDataRepository, "list", AsyncMock(return_value=[]))
    spec = [
        make_template_variable(
            template_variable="proof_of_claim_row",
            source=FieldSource.GMAIL,
            source_params=make_gmail_source_params(),
            template_variable_string=None,
        ),
    ]
    with pytest.raises(HTTPException) as exc:
        await validate_template_spec_source_map(spec)
    errors = exc.value.detail["validation_errors"]
    assert any("proof_of_claim_row" in e and "virtual" in e for e in errors)


@pytest.mark.unit
async def test_source_map_accepts_virtual_with_auto_derive_child(monkeypatch):
    monkeypatch.setattr(ReferenceDataRepository, "list", AsyncMock(return_value=[]))
    spec = [
        make_template_variable(
            template_variable="proof_of_claim_row",
            source=FieldSource.GMAIL,
            source_params=make_gmail_source_params(),
            template_variable_string=None,
        ),
        make_template_variable(
            template_variable="claim_number",
            source=FieldSource.AUTO_DERIVED_FROM_VARIABLE,
            source_params=AutoDerivedSourceParams(dependent_variable="proof_of_claim_row"),
        ),
    ]
    spec[1].read_only = True
    await validate_template_spec_source_map(spec)  # no raise


# ─── _validate_dropdown_format_includes_auto_derive_children ──────────


@pytest.mark.unit
async def test_source_map_rejects_dropdown_format_missing_child_marker(monkeypatch):
    """Dropdown parent's example_format omits a child's marker → error names
    the child + its missing example value."""
    monkeypatch.setattr(ReferenceDataRepository, "list", AsyncMock(return_value=[]))
    spec = [
        make_template_variable(
            template_variable="proof_of_claim_row",
            source=FieldSource.DROPDOWN_FROM_GMAIL,
            source_params=make_dropdown_email_source_params(
                label="Pick the proof of claim row",
                example_format="Bank of America - $3,000.00",
                subject_query="Proof of Claim",
            ),
            template_variable_string=None,
        ),
        make_template_variable(
            template_variable="claim_number",
            source=FieldSource.AUTO_DERIVED_FROM_VARIABLE,
            source_params=AutoDerivedSourceParams(dependent_variable="proof_of_claim_row"),
            template_property_marker="4",
        ),
    ]
    spec[1].read_only = True

    with pytest.raises(HTTPException) as exc:
        await validate_template_spec_source_map(spec)

    errors = exc.value.detail["validation_errors"]
    assert any(
        "claim_number" in e and "'4'" in e and "example_format" in e
        for e in errors
    )


@pytest.mark.unit
async def test_source_map_accepts_dropdown_format_covering_all_children(monkeypatch):
    """All three child markers appear as substrings in example_format → pass."""
    monkeypatch.setattr(ReferenceDataRepository, "list", AsyncMock(return_value=[]))
    spec = [
        make_template_variable(
            template_variable="proof_of_claim_row",
            source=FieldSource.DROPDOWN_FROM_GMAIL,
            source_params=make_dropdown_email_source_params(
                label="Pick the proof of claim row",
                example_format="4 - Bank of America - $3,000.00",
                subject_query="Proof of Claim",
            ),
            template_variable_string=None,
        ),
        make_template_variable(
            template_variable="claim_number",
            source=FieldSource.AUTO_DERIVED_FROM_VARIABLE,
            source_params=AutoDerivedSourceParams(dependent_variable="proof_of_claim_row"),
            template_property_marker="4",
        ),
        make_template_variable(
            template_variable="claimant_name",
            source=FieldSource.AUTO_DERIVED_FROM_VARIABLE,
            source_params=AutoDerivedSourceParams(dependent_variable="proof_of_claim_row"),
            template_property_marker="Bank of America",
        ),
        make_template_variable(
            template_variable="claim_amount",
            source=FieldSource.AUTO_DERIVED_FROM_VARIABLE,
            source_params=AutoDerivedSourceParams(dependent_variable="proof_of_claim_row"),
            template_property_marker="$3,000.00",
        ),
    ]
    for v in spec[1:]:
        v.read_only = True

    await validate_template_spec_source_map(spec)  # no raise


@pytest.mark.unit
async def test_source_map_skips_coverage_check_when_child_marker_is_empty(monkeypatch):
    """No example value → validator can't enforce coverage; runtime-only
    failure mode. Pass at validate time."""
    monkeypatch.setattr(ReferenceDataRepository, "list", AsyncMock(return_value=[]))
    spec = [
        make_template_variable(
            template_variable="proof_of_claim_row",
            source=FieldSource.DROPDOWN_FROM_GMAIL,
            source_params=make_dropdown_email_source_params(
                label="Pick row",
                example_format="anything",
                subject_query="x",
            ),
            template_variable_string=None,
        ),
        make_template_variable(
            template_variable="claim_number",
            source=FieldSource.AUTO_DERIVED_FROM_VARIABLE,
            source_params=AutoDerivedSourceParams(dependent_variable="proof_of_claim_row"),
            template_property_marker=None,
        ),
    ]
    spec[1].read_only = True

    await validate_template_spec_source_map(spec)  # no raise


@pytest.mark.unit
async def test_source_map_skips_coverage_check_for_non_dropdown_parents(monkeypatch):
    """Only `dropdown_from_*` parents are subject to the coverage rule —
    a plain GMAIL parent's resolved value isn't shaped by example_format."""
    monkeypatch.setattr(ReferenceDataRepository, "list", AsyncMock(return_value=[]))
    spec = [
        make_template_variable(
            template_variable="ecf_full",
            source=FieldSource.GMAIL,
            source_params=make_gmail_source_params(subject_query="x"),
        ),
        make_template_variable(
            template_variable="ecf_title",
            source=FieldSource.AUTO_DERIVED_FROM_VARIABLE,
            source_params=AutoDerivedSourceParams(dependent_variable="ecf_full"),
            template_property_marker="3",
        ),
    ]
    spec[1].read_only = True

    await validate_template_spec_source_map(spec)  # no raise


# ─── _validate_query_template_refs ────────────────────────────────────


@pytest.mark.unit
async def test_source_map_accepts_query_template_ref_to_llm_draft_variable(monkeypatch):
    """`{{prior_case_number}}` refers to a case_vector LLM_DRAFT variable — eligible."""
    monkeypatch.setattr(ReferenceDataRepository, "list", AsyncMock(return_value=[]))
    spec = [
        make_template_variable(
            template_variable="prior_case_number",
            source=FieldSource.CASE_VECTOR,
            source_params=CaseVectorSourceParams(text_query="prior bankruptcy case"),
        ),
        make_template_variable(
            template_variable="prior_dismissal_row",
            source=FieldSource.DROPDOWN_FROM_GMAIL,
            source_params=make_dropdown_email_source_params(
                label="Pick the Order Dismissing email",
                example_format="October 15, 2024 — Order Dismissing Case",
                body_query="Notice of Order {{prior_case_number}}",
            ),
            template_variable_string=None,
        ),
        make_template_variable(
            template_variable="dismissal_date",
            source=FieldSource.AUTO_DERIVED_FROM_VARIABLE,
            source_params=AutoDerivedSourceParams(dependent_variable="prior_dismissal_row"),
            template_property_marker="October 15, 2024",
        ),
    ]
    spec[2].read_only = True
    await validate_template_spec_source_map(spec)  # no raise


@pytest.mark.unit
async def test_source_map_rejects_query_template_ref_to_unknown_variable(monkeypatch):
    monkeypatch.setattr(ReferenceDataRepository, "list", AsyncMock(return_value=[]))
    spec = [
        make_template_variable(
            template_variable="bad_query",
            source=FieldSource.GMAIL,
            source_params=make_gmail_source_params(
                body_query="Order {{undefined_var}}",
            ),
        ),
    ]
    with pytest.raises(HTTPException) as exc:
        await validate_template_spec_source_map(spec)
    errors = exc.value.detail["validation_errors"]
    assert any("undefined_var" in e and "unknown" in e for e in errors)


@pytest.mark.unit
async def test_source_map_accepts_llm_draft_ref_to_user_input_variable(monkeypatch):
    """Path B: LLM_DRAFT referencers (gmail, case_vector, etc.) CAN
    reference USER_INPUT-rooted targets — the pipeline defers these
    fetches to Pass 3 in `run_resume_stages`, after the user pick."""
    monkeypatch.setattr(ReferenceDataRepository, "list", AsyncMock(return_value=[]))
    spec = [
        make_template_variable(
            template_variable="user_pick",
            source=FieldSource.DROPDOWN_FROM_GMAIL,
            source_params=make_dropdown_email_source_params(
                label="Pick a row",
                example_format="...",
                subject_query="x",
            ),
        ),
        make_template_variable(
            template_variable="llm_draft_ref",
            source=FieldSource.GMAIL,
            source_params=make_gmail_source_params(
                body_query="depends on {{user_pick}}",
            ),
        ),
    ]
    await validate_template_spec_source_map(spec)  # no raise


@pytest.mark.unit
async def test_source_map_rejects_user_input_ref_to_user_input_variable(monkeypatch):
    """USER_INPUT → USER_INPUT-rooted is still rejected — both resolve
    at the same pause, can't order them within one pause."""
    monkeypatch.setattr(ReferenceDataRepository, "list", AsyncMock(return_value=[]))
    spec = [
        make_template_variable(
            template_variable="user_pick_a",
            source=FieldSource.DROPDOWN_FROM_GMAIL,
            source_params=make_dropdown_email_source_params(
                label="Pick A", example_format="...", subject_query="x",
            ),
        ),
        make_template_variable(
            template_variable="user_pick_b",
            source=FieldSource.DROPDOWN_FROM_GMAIL,
            source_params=make_dropdown_email_source_params(
                label="Pick B",
                example_format="...",
                subject_query="depends on {{user_pick_a}}",
            ),
        ),
    ]
    with pytest.raises(HTTPException) as exc:
        await validate_template_spec_source_map(spec)
    errors = exc.value.detail["validation_errors"]
    assert any("user_pick_a" in e and "user_input" in e.lower() for e in errors)


@pytest.mark.unit
async def test_source_map_rejects_query_template_cycle(monkeypatch):
    """A → B (via {{B}}) → A (via {{A}}) → cycle error."""
    monkeypatch.setattr(ReferenceDataRepository, "list", AsyncMock(return_value=[]))
    spec = [
        make_template_variable(
            template_variable="a",
            source=FieldSource.GMAIL,
            source_params=make_gmail_source_params(body_query="{{b}}"),
        ),
        make_template_variable(
            template_variable="b",
            source=FieldSource.GMAIL,
            source_params=make_gmail_source_params(body_query="{{a}}"),
        ),
    ]
    with pytest.raises(HTTPException) as exc:
        await validate_template_spec_source_map(spec)
    errors = exc.value.detail["validation_errors"]
    assert any("cycle" in e.lower() and "a" in e and "b" in e for e in errors)


# ─── _validate_reco_chips_dependent_variables ─────────────────────────


@pytest.mark.unit
async def test_source_map_accepts_reco_chips_from_dependent_variables(monkeypatch):
    monkeypatch.setattr(ReferenceDataRepository, "list", AsyncMock(return_value=[]))
    spec = [
        make_template_variable(
            template_variable="trustee_reason",
            source=FieldSource.GMAIL,
            source_params=make_gmail_source_params(subject_query="Order Dismissing"),
        ),
        make_template_variable(
            template_variable="change_in_circumstances_explanation",
            source=FieldSource.RECO_CHIPS_FROM_DEPENDENT_VARIABLES,
            source_params=RecoChipsFromDependentVariablesSourceParams(
                label="Change in circumstances",
                example_sentence="The Debtor will now be able to afford their plan...",
                dependent_variables=["trustee_reason"],
            ),
        ),
    ]
    await validate_template_spec_source_map(spec)  # no raise


@pytest.mark.unit
async def test_source_map_rejects_reco_chips_with_no_context_sources(monkeypatch):
    """All three context-source lists empty → reject. The chip generator
    needs at least one of {dependent_variables, case_vector_queries,
    dependent_chip_variables} to compose from."""
    monkeypatch.setattr(ReferenceDataRepository, "list", AsyncMock(return_value=[]))
    spec = [
        make_template_variable(
            template_variable="bad_chips",
            source=FieldSource.RECO_CHIPS_FROM_DEPENDENT_VARIABLES,
            source_params=RecoChipsFromDependentVariablesSourceParams(
                label="x",
                example_sentence="x",
                dependent_variables=[],
                case_vector_queries=[],
                dependent_chip_variables=[],
            ),
        ),
    ]
    with pytest.raises(HTTPException) as exc:
        await validate_template_spec_source_map(spec)
    errors = exc.value.detail["validation_errors"]
    assert any(
        "dependent_variables" in e and "case_vector_queries" in e and "dependent_chip_variables" in e
        for e in errors
    )


@pytest.mark.unit
async def test_source_map_rejects_reco_chips_with_unknown_dependent_variable(monkeypatch):
    monkeypatch.setattr(ReferenceDataRepository, "list", AsyncMock(return_value=[]))
    spec = [
        make_template_variable(
            template_variable="bad_chips",
            source=FieldSource.RECO_CHIPS_FROM_DEPENDENT_VARIABLES,
            source_params=RecoChipsFromDependentVariablesSourceParams(
                label="x",
                example_sentence="x",
                dependent_variables=["nonexistent_var"],
            ),
        ),
    ]
    with pytest.raises(HTTPException) as exc:
        await validate_template_spec_source_map(spec)
    errors = exc.value.detail["validation_errors"]
    assert any("nonexistent_var" in e and "does not exist" in e for e in errors)


@pytest.mark.unit
async def test_source_map_rejects_reco_chips_dependent_on_user_input_target(monkeypatch):
    """Dependent variable must resolve before USER_INPUT pause — pointing to a
    USER_INPUT-stage variable means the chip composer would never see a value."""
    monkeypatch.setattr(ReferenceDataRepository, "list", AsyncMock(return_value=[]))
    spec = [
        make_template_variable(
            template_variable="picked_row",
            source=FieldSource.DROPDOWN_FROM_GMAIL,
            source_params=make_dropdown_email_source_params(
                label="Pick a row",
                example_format="...",
                subject_query="x",
            ),
        ),
        make_template_variable(
            template_variable="bad_chips",
            source=FieldSource.RECO_CHIPS_FROM_DEPENDENT_VARIABLES,
            source_params=RecoChipsFromDependentVariablesSourceParams(
                label="x",
                example_sentence="x",
                dependent_variables=["picked_row"],
            ),
        ),
    ]
    with pytest.raises(HTTPException) as exc:
        await validate_template_spec_source_map(spec)
    errors = exc.value.detail["validation_errors"]
    assert any("picked_row" in e and "user_input" in e.lower() for e in errors)


@pytest.mark.unit
async def test_source_map_accepts_chip_to_chip_alignment(monkeypatch):
    """Chip B with dependent_chip_variables=[A] where A is also a
    reco_chips_from_dependent_variables variable — valid, no cycle."""
    monkeypatch.setattr(ReferenceDataRepository, "list", AsyncMock(return_value=[]))
    spec = [
        make_template_variable(
            template_variable="trustee_reason",
            source=FieldSource.GMAIL,
            source_params=make_gmail_source_params(subject_query="x"),
        ),
        make_template_variable(
            template_variable="change_in_circ",
            source=FieldSource.RECO_CHIPS_FROM_DEPENDENT_VARIABLES,
            source_params=RecoChipsFromDependentVariablesSourceParams(
                label="Change",
                example_sentence="x",
                dependent_variables=["trustee_reason"],
            ),
        ),
        make_template_variable(
            template_variable="dismissal_explanation",
            source=FieldSource.RECO_CHIPS_FROM_DEPENDENT_VARIABLES,
            source_params=RecoChipsFromDependentVariablesSourceParams(
                label="Dismissal",
                example_sentence="x",
                dependent_variables=["trustee_reason"],
                dependent_chip_variables=["change_in_circ"],
            ),
        ),
    ]
    await validate_template_spec_source_map(spec)  # no raise


@pytest.mark.unit
async def test_source_map_rejects_dependent_chip_variable_to_non_chip_source(monkeypatch):
    monkeypatch.setattr(ReferenceDataRepository, "list", AsyncMock(return_value=[]))
    spec = [
        make_template_variable(
            template_variable="some_email",
            source=FieldSource.GMAIL,
            source_params=make_gmail_source_params(subject_query="x"),
        ),
        make_template_variable(
            template_variable="bad_chips",
            source=FieldSource.RECO_CHIPS_FROM_DEPENDENT_VARIABLES,
            source_params=RecoChipsFromDependentVariablesSourceParams(
                label="x",
                example_sentence="x",
                dependent_variables=["some_email"],
                dependent_chip_variables=["some_email"],  # not a chip source
            ),
        ),
    ]
    with pytest.raises(HTTPException) as exc:
        await validate_template_spec_source_map(spec)
    errors = exc.value.detail["validation_errors"]
    assert any(
        "dependent_chip_variable" in e and "some_email" in e and "reco_chips" in e.lower()
        for e in errors
    )


@pytest.mark.unit
async def test_source_map_rejects_dependent_chip_variable_cycle(monkeypatch):
    """A → B → A through dependent_chip_variables is a cycle."""
    monkeypatch.setattr(ReferenceDataRepository, "list", AsyncMock(return_value=[]))
    spec = [
        make_template_variable(
            template_variable="trustee_reason",
            source=FieldSource.GMAIL,
            source_params=make_gmail_source_params(subject_query="x"),
        ),
        make_template_variable(
            template_variable="chip_a",
            source=FieldSource.RECO_CHIPS_FROM_DEPENDENT_VARIABLES,
            source_params=RecoChipsFromDependentVariablesSourceParams(
                label="A",
                example_sentence="x",
                dependent_variables=["trustee_reason"],
                dependent_chip_variables=["chip_b"],
            ),
        ),
        make_template_variable(
            template_variable="chip_b",
            source=FieldSource.RECO_CHIPS_FROM_DEPENDENT_VARIABLES,
            source_params=RecoChipsFromDependentVariablesSourceParams(
                label="B",
                example_sentence="x",
                dependent_variables=["trustee_reason"],
                dependent_chip_variables=["chip_a"],
            ),
        ),
    ]
    with pytest.raises(HTTPException) as exc:
        await validate_template_spec_source_map(spec)
    errors = exc.value.detail["validation_errors"]
    assert any("cycle" in e.lower() for e in errors)


@pytest.mark.unit
async def test_source_map_accepts_chip_with_only_case_vector_queries(monkeypatch):
    """At least one of {dependent_variables, case_vector_queries,
    dependent_chip_variables} must be non-empty — case_vector_queries alone is OK."""
    from src.core.agents.types.sources import CaseVectorQueryEntry

    monkeypatch.setattr(ReferenceDataRepository, "list", AsyncMock(return_value=[]))
    spec = [
        make_template_variable(
            template_variable="employment_description",
            source=FieldSource.RECO_CHIPS_FROM_DEPENDENT_VARIABLES,
            source_params=RecoChipsFromDependentVariablesSourceParams(
                label="Employment",
                example_sentence="x",
                dependent_variables=[],
                case_vector_queries=[
                    CaseVectorQueryEntry(label="Schedule I", text_query="employer occupation income"),
                ],
            ),
        ),
    ]
    await validate_template_spec_source_map(spec)  # no raise


@pytest.mark.unit
async def test_source_map_rejects_case_vector_queries_with_unknown_var_ref(monkeypatch):
    from src.core.agents.types.sources import CaseVectorQueryEntry

    monkeypatch.setattr(ReferenceDataRepository, "list", AsyncMock(return_value=[]))
    spec = [
        make_template_variable(
            template_variable="bad_chips",
            source=FieldSource.RECO_CHIPS_FROM_DEPENDENT_VARIABLES,
            source_params=RecoChipsFromDependentVariablesSourceParams(
                label="x",
                example_sentence="x",
                case_vector_queries=[
                    CaseVectorQueryEntry(label="X", text_query="Schedule {{undefined_var}}"),
                ],
            ),
        ),
    ]
    with pytest.raises(HTTPException) as exc:
        await validate_template_spec_source_map(spec)
    errors = exc.value.detail["validation_errors"]
    assert any("undefined_var" in e and "unknown" in e for e in errors)


# ─── multi_select_from_case_vector ──────────────────────


from src.core.agents.types.sources import MultiSelectFromCaseVectorSourceParams


def _multi_select_var(
    template_variable: str = "selected_assets",
    string: str | None = None,
    example_formats: list[str] | None = None,
):
    if example_formats is None:
        example_formats = ['2018 Mercedes G-Wagon, VIN# X ("Vehicle")']
    params = MultiSelectFromCaseVectorSourceParams(
        label="Select Assets",
        instruction="pick options",
        text_query="Schedule A/B property OR Schedule D vehicle",
        example_formats=example_formats,
        min_picks=1,
    )
    return make_template_variable(
        template_variable=template_variable,
        source=FieldSource.MULTI_SELECT_FROM_CASE_VECTOR,
        source_params=params,
        template_variable_string=string,
    )


@pytest.mark.unit
async def test_source_map_accepts_multi_select_bound_directly_to_docx(monkeypatch):
    """multi_select can fill a docx slot directly — no auto_derive child needed
    because expand_picks Oxford-comma-joins the picks itself."""
    monkeypatch.setattr(ReferenceDataRepository, "list", AsyncMock(return_value=[]))
    spec = [
        _multi_select_var(
            template_variable="selected_assets",
            string="[[selected_assets]]",
        ),
    ]
    await validate_template_spec_source_map(spec)  # no raise


@pytest.mark.unit
async def test_multi_select_default_join_params():
    """Defaults: list_joiner=', ' and oxford=True so binding directly to a
    docx slot yields Oxford-comma prose without further configuration."""
    params = MultiSelectFromCaseVectorSourceParams(
        label="x",
        text_query="x",
        example_formats=["example"],
    )
    assert params.list_joiner == ", "
    assert params.oxford is True


@pytest.mark.unit
async def test_multi_select_accepts_custom_join_params():
    params = MultiSelectFromCaseVectorSourceParams(
        label="x",
        text_query="x",
        example_formats=["example"],
        list_joiner="; ",
        oxford=False,
    )
    assert params.list_joiner == "; "
    assert params.oxford is False


@pytest.mark.unit
async def test_multi_select_rejects_empty_text_query():
    with pytest.raises(Exception) as exc:
        MultiSelectFromCaseVectorSourceParams(
            label="x",
            text_query="   ",
            example_formats=["example"],
        )
    assert "text_query" in str(exc.value)


@pytest.mark.unit
async def test_multi_select_rejects_empty_example_formats_list():
    with pytest.raises(Exception) as exc:
        MultiSelectFromCaseVectorSourceParams(
            label="x",
            text_query="x",
            example_formats=[],
        )
    assert "at least 1" in str(exc.value).lower() or "example_formats" in str(exc.value)


@pytest.mark.unit
async def test_multi_select_rejects_blank_example_format_entry():
    with pytest.raises(Exception) as exc:
        MultiSelectFromCaseVectorSourceParams(
            label="x",
            text_query="x",
            example_formats=["valid", "  "],
        )
    assert "example_formats" in str(exc.value)


@pytest.mark.unit
async def test_multi_select_accepts_multiple_example_formats():
    """Two heterogeneous shapes are valid — used for asset pickers mixing
    vehicles and properties in one source."""
    params = MultiSelectFromCaseVectorSourceParams(
        label="Select Assets",
        text_query="Schedule A/B OR Schedule D",
        example_formats=[
            '2018 Mercedes G-Wagon, VIN# X ("Vehicle")',
            '1234 Main St, Oakland Park, FL ("Property")',
        ],
    )
    assert len(params.example_formats) == 2


@pytest.mark.unit
async def test_multi_select_rejects_max_below_min():
    with pytest.raises(Exception) as exc:
        MultiSelectFromCaseVectorSourceParams(
            label="x",
            text_query="x",
            example_formats=["example"],
            min_picks=3,
            max_picks=1,
        )
    assert ">= min_picks" in str(exc.value)


# ─── _validate_reco_chips_dependent_variables — remaining branches ─────


@pytest.mark.unit
async def test_source_map_rejects_reco_chips_self_reference_in_dependent_variables(monkeypatch):
    """A reco_chips variable can't list itself in dependent_variables."""
    monkeypatch.setattr(ReferenceDataRepository, "list", AsyncMock(return_value=[]))
    spec = [
        make_template_variable(
            template_variable="self_ref",
            source=FieldSource.RECO_CHIPS_FROM_DEPENDENT_VARIABLES,
            source_params=RecoChipsFromDependentVariablesSourceParams(
                label="x",
                example_sentence="x",
                dependent_variables=["self_ref"],
            ),
        ),
    ]
    with pytest.raises(HTTPException) as exc:
        await validate_template_spec_source_map(spec)
    errors = exc.value.detail["validation_errors"]
    assert any("cannot reference itself" in e and "dependent_variables" in e for e in errors)


@pytest.mark.unit
async def test_source_map_rejects_reco_chips_dependent_on_target_with_no_source(monkeypatch):
    """Pointing at a partner variable (source=None, claimed by a group-dropdown
    anchor) is not allowed — only LLM_DRAFT / SYSTEM_GENERATED variables can
    be referenced from a reco-chips dependent."""
    monkeypatch.setattr(ReferenceDataRepository, "list", AsyncMock(return_value=[]))
    spec = [
        make_template_variable(
            template_variable="gd_anchor",
            source=FieldSource.GROUP_DROPDOWN_FROM_GMAIL,
            source_params=GroupDropdownSourceParams(
                subject_query="x",
                group_label="g",
                left_label="L",
                right_label="R",
                right_partner_variable="partner",
            ),
        ),
        make_template_variable(
            template_variable="partner",
            source=None,
            source_params=None,
        ),
        make_template_variable(
            template_variable="bad_chips",
            source=FieldSource.RECO_CHIPS_FROM_DEPENDENT_VARIABLES,
            source_params=RecoChipsFromDependentVariablesSourceParams(
                label="x",
                example_sentence="x",
                dependent_variables=["partner"],
            ),
        ),
    ]
    with pytest.raises(HTTPException) as exc:
        await validate_template_spec_source_map(spec)
    errors = exc.value.detail["validation_errors"]
    assert any("partner" in e and "no source" in e for e in errors)


@pytest.mark.unit
async def test_source_map_rejects_reco_chips_self_reference_in_dependent_chip_variables(monkeypatch):
    """A reco_chips variable can't list itself in dependent_chip_variables."""
    monkeypatch.setattr(ReferenceDataRepository, "list", AsyncMock(return_value=[]))
    spec = [
        make_template_variable(
            template_variable="some_email",
            source=FieldSource.GMAIL,
            source_params=make_gmail_source_params(subject_query="x"),
        ),
        make_template_variable(
            template_variable="self_ref_chip",
            source=FieldSource.RECO_CHIPS_FROM_DEPENDENT_VARIABLES,
            source_params=RecoChipsFromDependentVariablesSourceParams(
                label="x",
                example_sentence="x",
                dependent_variables=["some_email"],
                dependent_chip_variables=["self_ref_chip"],
            ),
        ),
    ]
    with pytest.raises(HTTPException) as exc:
        await validate_template_spec_source_map(spec)
    errors = exc.value.detail["validation_errors"]
    assert any("cannot reference itself" in e and "dependent_chip_variables" in e for e in errors)


@pytest.mark.unit
async def test_source_map_rejects_reco_chips_with_unknown_dependent_chip_variable(monkeypatch):
    """dependent_chip_variables pointing to a name not in template_spec → reject."""
    monkeypatch.setattr(ReferenceDataRepository, "list", AsyncMock(return_value=[]))
    spec = [
        make_template_variable(
            template_variable="some_email",
            source=FieldSource.GMAIL,
            source_params=make_gmail_source_params(subject_query="x"),
        ),
        make_template_variable(
            template_variable="bad_chips",
            source=FieldSource.RECO_CHIPS_FROM_DEPENDENT_VARIABLES,
            source_params=RecoChipsFromDependentVariablesSourceParams(
                label="x",
                example_sentence="x",
                dependent_variables=["some_email"],
                dependent_chip_variables=["ghost_chip"],
            ),
        ),
    ]
    with pytest.raises(HTTPException) as exc:
        await validate_template_spec_source_map(spec)
    errors = exc.value.detail["validation_errors"]
    assert any("ghost_chip" in e and "does not exist" in e for e in errors)


# ─── auto_derived effective-stage references ──────────────────────────


@pytest.mark.unit
async def test_source_map_accepts_query_ref_to_auto_derived_with_llm_draft_root(monkeypatch):
    """An auto_derived child whose ROOT parent is case_vector (LLM_DRAFT) is
    referenceable via {{var}} in another LLM_DRAFT variable's text_query.
    Resolves in the early-pass between Pass 1 and Pass 2."""
    monkeypatch.setattr(ReferenceDataRepository, "list", AsyncMock(return_value=[]))
    spec = [
        make_template_variable(
            template_variable="vehicle_record",
            source=FieldSource.CASE_VECTOR,
            source_params=CaseVectorSourceParams(text_query="vehicle row"),
            template_variable_string=None,
        ),
        make_template_variable(
            template_variable="vehicle_name",
            source=FieldSource.AUTO_DERIVED_FROM_VARIABLE,
            source_params=AutoDerivedSourceParams(dependent_variable="vehicle_record"),
            template_property_marker="2018 Toyota Camry",
        ),
        make_template_variable(
            template_variable="creditor_name",
            source=FieldSource.CASE_VECTOR,
            source_params=CaseVectorSourceParams(
                text_query="lien holder for {{vehicle_name}}"
            ),
        ),
    ]
    spec[1].read_only = True
    await validate_template_spec_source_map(spec)  # no raise


@pytest.mark.unit
async def test_source_map_accepts_llm_draft_ref_to_auto_derived_with_user_input_root(monkeypatch):
    """Path B: LLM_DRAFT referencers (case_vector here) CAN reference
    auto_derived children of USER_INPUT-rooted parents — the deferred
    Pass 3 fetch resolves them after the user pick + late auto-derive."""
    monkeypatch.setattr(ReferenceDataRepository, "list", AsyncMock(return_value=[]))
    spec = [
        make_template_variable(
            template_variable="vehicle_record",
            source=FieldSource.DROPDOWN_FROM_GMAIL,
            source_params=make_dropdown_email_source_params(
                label="Pick the vehicle row",
                example_format="2018 Toyota Camry — VIN — 82,300 mi",
                subject_query="vehicle",
            ),
            template_variable_string=None,
        ),
        make_template_variable(
            template_variable="vehicle_name",
            source=FieldSource.AUTO_DERIVED_FROM_VARIABLE,
            source_params=AutoDerivedSourceParams(dependent_variable="vehicle_record"),
            template_property_marker="2018 Toyota Camry",
        ),
        make_template_variable(
            template_variable="creditor_name",
            source=FieldSource.CASE_VECTOR,
            source_params=CaseVectorSourceParams(
                text_query="lien holder for {{vehicle_name}}"
            ),
        ),
    ]
    spec[1].read_only = True
    await validate_template_spec_source_map(spec)  # no raise


@pytest.mark.unit
async def test_source_map_rejects_reco_chips_dependent_variable_to_auto_derived_with_user_input_root(monkeypatch):
    """Same rule applies to the reco_chips_from_dependent_variables.dependent_variables list."""
    monkeypatch.setattr(ReferenceDataRepository, "list", AsyncMock(return_value=[]))
    spec = [
        make_template_variable(
            template_variable="vehicle_record",
            source=FieldSource.DROPDOWN_FROM_GMAIL,
            source_params=make_dropdown_email_source_params(
                label="Pick row", example_format="...", subject_query="vehicle",
            ),
            template_variable_string=None,
        ),
        make_template_variable(
            template_variable="vehicle_name",
            source=FieldSource.AUTO_DERIVED_FROM_VARIABLE,
            source_params=AutoDerivedSourceParams(dependent_variable="vehicle_record"),
            template_property_marker="2018 Toyota Camry",
        ),
        make_template_variable(
            template_variable="explanation",
            source=FieldSource.RECO_CHIPS_FROM_DEPENDENT_VARIABLES,
            source_params=RecoChipsFromDependentVariablesSourceParams(
                label="Change in circumstances",
                example_sentence="x",
                dependent_variables=["vehicle_name"],
            ),
        ),
    ]
    spec[1].read_only = True
    with pytest.raises(HTTPException) as exc:
        await validate_template_spec_source_map(spec)
    errors = exc.value.detail["validation_errors"]
    assert any(
        "vehicle_name" in e and "user_input" in e.lower() for e in errors
    ), f"Expected dependent_variable error mentioning vehicle_name + user_input; got: {errors}"


@pytest.mark.unit
async def test_source_map_accepts_chain_depth_two_with_llm_draft_root(monkeypatch):
    """auto_derived → auto_derived → case_vector chain — leaf is referenceable."""
    monkeypatch.setattr(ReferenceDataRepository, "list", AsyncMock(return_value=[]))
    spec = [
        make_template_variable(
            template_variable="vehicle_record",
            source=FieldSource.CASE_VECTOR,
            source_params=CaseVectorSourceParams(text_query="vehicle row"),
            template_variable_string=None,
        ),
        make_template_variable(
            template_variable="vehicle_name",
            source=FieldSource.AUTO_DERIVED_FROM_VARIABLE,
            source_params=AutoDerivedSourceParams(dependent_variable="vehicle_record"),
            template_property_marker="2018 Toyota Camry",
        ),
        make_template_variable(
            template_variable="vehicle_name_truncated",
            source=FieldSource.AUTO_DERIVED_FROM_VARIABLE,
            source_params=AutoDerivedSourceParams(dependent_variable="vehicle_name"),
            template_property_marker="Toyota Camry",
        ),
        make_template_variable(
            template_variable="creditor_name",
            source=FieldSource.CASE_VECTOR,
            source_params=CaseVectorSourceParams(
                text_query="lien for {{vehicle_name_truncated}}"
            ),
        ),
    ]
    spec[1].read_only = True
    spec[2].read_only = True
    await validate_template_spec_source_map(spec)  # no raise


@pytest.mark.unit
async def test_source_map_accepts_llm_draft_ref_to_auto_derived_with_unbound_root(monkeypatch):
    """Placeholder rule: at compose time, before the virtual parent has
    been bound to a source, LLM_DRAFT-stage referencers can still wire
    `{{auto_derived_child}}` references. Lets authors stub variables and
    set up references before deciding source bindings."""
    monkeypatch.setattr(ReferenceDataRepository, "list", AsyncMock(return_value=[]))
    spec = [
        make_template_variable(
            template_variable="vehicle_record",
            source=None,
            source_params=None,
            template_variable_string=None,
        ),
        make_template_variable(
            template_variable="car_model",
            source=FieldSource.AUTO_DERIVED_FROM_VARIABLE,
            source_params=AutoDerivedSourceParams(dependent_variable="vehicle_record"),
            template_property_marker="2023 Kia Sportage",
        ),
        make_template_variable(
            template_variable="creditor_name",
            source=FieldSource.CASE_VECTOR,
            source_params=CaseVectorSourceParams(
                text_query="secured claims for {{car_model}}"
            ),
        ),
    ]
    spec[1].read_only = True
    await validate_template_spec_source_map(spec)  # no raise


@pytest.mark.unit
async def test_source_map_rejects_reco_chips_dependent_variable_to_auto_derived_with_unbound_root(monkeypatch):
    """USER_INPUT-stage referencer (reco_chips_from_dependent_variables)
    can NOT wire placeholder refs to unbound-root auto_derived. The
    placeholder rule is restricted to LLM_DRAFT referencers — once the
    parent IS bound to anything USER_INPUT-stage, this would still be a
    same-pause circular reference."""
    monkeypatch.setattr(ReferenceDataRepository, "list", AsyncMock(return_value=[]))
    spec = [
        make_template_variable(
            template_variable="vehicle_record",
            source=None,
            source_params=None,
            template_variable_string=None,
        ),
        make_template_variable(
            template_variable="car_model",
            source=FieldSource.AUTO_DERIVED_FROM_VARIABLE,
            source_params=AutoDerivedSourceParams(dependent_variable="vehicle_record"),
            template_property_marker="2023 Kia Sportage",
        ),
        make_template_variable(
            template_variable="explanation",
            source=FieldSource.RECO_CHIPS_FROM_DEPENDENT_VARIABLES,
            source_params=RecoChipsFromDependentVariablesSourceParams(
                label="Change in circumstances",
                example_sentence="x",
                dependent_variables=["car_model"],
            ),
        ),
    ]
    spec[1].read_only = True
    with pytest.raises(HTTPException) as exc:
        await validate_template_spec_source_map(spec)
    errors = exc.value.detail["validation_errors"]
    assert any("car_model" in e for e in errors), (
        f"Expected rejection mentioning car_model; got: {errors}"
    )


@pytest.mark.unit
async def test_source_map_rejects_llm_draft_ref_to_unbound_non_auto_derived_target(monkeypatch):
    """The placeholder rule applies ONLY to auto_derived targets. A direct
    `{{var}}` ref to an unbound non-auto_derived variable is still
    rejected (the author needs to bind the target before referencing it
    — there's no chain that promises future resolution)."""
    monkeypatch.setattr(ReferenceDataRepository, "list", AsyncMock(return_value=[]))
    spec = [
        make_template_variable(
            template_variable="vehicle_record",
            source=None,
            source_params=None,
            template_variable_string=None,
        ),
        make_template_variable(
            template_variable="creditor_name",
            source=FieldSource.CASE_VECTOR,
            source_params=CaseVectorSourceParams(
                text_query="lien for {{vehicle_record}}"
            ),
        ),
    ]
    with pytest.raises(HTTPException) as exc:
        await validate_template_spec_source_map(spec)
    errors = exc.value.detail["validation_errors"]
    assert any(
        "vehicle_record" in e and "no source" in e.lower() for e in errors
    ), f"Expected 'no source' error mentioning vehicle_record; got: {errors}"
