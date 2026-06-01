"""Tests for DependentOnVariableSourceParams._validate_rules.

Seven invariants enforced by the model_validator:
  1. dependent_variable must be non-empty
  2. DATE derived type only accepts DATE-family rule effects
  3. FORMAT_ONLY must have NO rule_effect_value
  4. Non-FORMAT_ONLY DATE rules must have rule_effect_value
  5. rule_effect_value must parse as int
  6. rule_effect_value must be > 0
  7. Happy path (a valid config) constructs cleanly
"""

import pytest
from pydantic import ValidationError

from src.core.agents.types.sources import (
    DependentOnVariableSourceParams,
    DerivedValueType,
    RuleEffect,
)


def _build(**overrides) -> DependentOnVariableSourceParams:
    defaults = {
        "dependent_variable": "parent",
        "derived_value_type": DerivedValueType.DATE,
        "rule_effect": RuleEffect.INCREMENT_BY_DAYS,
        "rule_effect_value": "14",
    }
    defaults.update(overrides)
    return DependentOnVariableSourceParams(**defaults)


@pytest.mark.unit
def test_happy_path_constructs_cleanly():
    params = _build()
    assert params.dependent_variable == "parent"
    assert params.rule_effect_value == "14"


@pytest.mark.unit
def test_empty_dependent_variable_rejected():
    with pytest.raises(ValidationError, match="dependent_variable must be a non-empty string"):
        _build(dependent_variable="")


@pytest.mark.unit
def test_whitespace_only_dependent_variable_rejected():
    with pytest.raises(ValidationError, match="non-empty"):
        _build(dependent_variable="   ")


@pytest.mark.unit
def test_format_only_accepts_null_rule_effect_value():
    params = _build(rule_effect=RuleEffect.FORMAT_ONLY, rule_effect_value=None)
    assert params.rule_effect == RuleEffect.FORMAT_ONLY
    assert params.rule_effect_value is None


@pytest.mark.unit
def test_format_only_rejects_non_null_rule_effect_value():
    with pytest.raises(ValidationError, match="must be null when rule_effect is 'format_only'"):
        _build(rule_effect=RuleEffect.FORMAT_ONLY, rule_effect_value="14")


@pytest.mark.unit
def test_non_format_only_requires_rule_effect_value():
    with pytest.raises(ValidationError, match="rule_effect_value is required"):
        _build(rule_effect=RuleEffect.INCREMENT_BY_DAYS, rule_effect_value=None)


@pytest.mark.unit
def test_non_format_only_rejects_empty_rule_effect_value():
    with pytest.raises(ValidationError, match="rule_effect_value is required"):
        _build(rule_effect=RuleEffect.INCREMENT_BY_DAYS, rule_effect_value="   ")


@pytest.mark.unit
def test_rule_effect_value_must_parse_as_int():
    with pytest.raises(ValidationError, match="must be an integer string"):
        _build(rule_effect_value="fourteen")


@pytest.mark.unit
def test_rule_effect_value_must_be_positive():
    with pytest.raises(ValidationError, match="must be a positive integer"):
        _build(rule_effect_value="0")


@pytest.mark.unit
def test_rule_effect_value_rejects_negative():
    with pytest.raises(ValidationError, match="must be a positive integer"):
        _build(rule_effect_value="-5")


# ─── source_params union discrimination + extras-forbid ─────────────────


from pydantic import TypeAdapter  # noqa: E402  (kept here to scope to the union tests)

from src.core.agents.types.sources import (  # noqa: E402
    AuthorSourceParams,
    AutoDerivedSourceParams,
    ConstantsSourceParams,
    CourtDriveSourceParams,
    DropdownCaseVectorSourceParams,
    DropdownEmailSourceParams,
    GmailSourceParams,
    GroupDropdownComposite,
    GroupDropdownSourceParams,
    RecoChipsCaseVectorSourceParams,
    RecoChipsEmailSourceParams,
    VectorSourceParams,
)


_AUTHOR_ADAPTER = TypeAdapter(AuthorSourceParams)


@pytest.mark.unit
def test_author_union_picks_reco_chips_email_over_gmail_when_label_present():
    """`label` and `example_sentence` are RecoChipsEmail-specific. With
    extra='forbid' on every variant, Pydantic must pick RecoChipsEmail —
    pre-fix it would silently coerce to GmailSourceParams and drop the extras."""
    payload = {
        "subject_query": None,
        "body_query": "Voluntary Petition",
        "label": "Change in Circumstances",
        "example_sentence": "The Debtor has experienced a material change.",
    }
    result = _AUTHOR_ADAPTER.validate_python(payload)
    assert isinstance(result, RecoChipsEmailSourceParams)
    assert result.label == "Change in Circumstances"
    assert result.example_sentence == "The Debtor has experienced a material change."


@pytest.mark.unit
def test_author_union_picks_group_dropdown_over_gmail_when_group_label_present():
    payload = {
        "subject_query": None,
        "body_query": "Filed by Debtor",
        "group_label": "ECF Document",
        "left_label": "ECF Number",
        "right_label": "Document Description",
        "right_partner_variable": "document_description",
    }
    result = _AUTHOR_ADAPTER.validate_python(payload)
    assert isinstance(result, GroupDropdownSourceParams)
    assert result.group_label == "ECF Document"


@pytest.mark.unit
def test_author_union_picks_reco_chips_case_vector_when_text_query_and_example_present():
    payload = {
        "text_query": "employer occupation income employment Schedule I",
        "label": "Employment Description",
        "example_sentence": "The Debtor is employed in a trusted capacity.",
    }
    result = _AUTHOR_ADAPTER.validate_python(payload)
    assert isinstance(result, RecoChipsCaseVectorSourceParams)


@pytest.mark.unit
def test_author_union_picks_dropdown_email_when_example_format_present():
    """`example_format` + `label` (no example_sentence / no text_query) is
    the DropdownEmail signature."""
    payload = {
        "subject_query": None,
        "body_query": "Filed",
        "label": "Motion Type",
        "example_format": "Motion to Modify Plan",
    }
    result = _AUTHOR_ADAPTER.validate_python(payload)
    assert isinstance(result, DropdownEmailSourceParams)
    assert result.example_format == "Motion to Modify Plan"


@pytest.mark.unit
def test_author_union_picks_dropdown_case_vector_when_text_query_and_example_format_present():
    payload = {
        "text_query": "motion type",
        "label": "Motion Type",
        "example_format": "Motion to Modify Plan",
    }
    result = _AUTHOR_ADAPTER.validate_python(payload)
    assert isinstance(result, DropdownCaseVectorSourceParams)


@pytest.mark.unit
def test_author_union_picks_auto_derived_when_dependent_variable_alone_present():
    """A payload with ONLY `dependent_variable` is the AutoDerived signature.
    DependentOnVariableSourceParams also has dependent_variable but requires
    other fields too — extra='forbid' on AutoDerived narrows the match."""
    payload = {"dependent_variable": "ecf_full"}
    result = _AUTHOR_ADAPTER.validate_python(payload)
    assert isinstance(result, AutoDerivedSourceParams)
    assert result.dependent_variable == "ecf_full"


@pytest.mark.unit
def test_auto_derived_pluralize_by_count_round_trips():
    """A pluralize_by_count payload with both singular_value + plural_value
    is valid and parses through the author union adapter to AutoDerivedSourceParams."""
    from src.core.agents.types.sources import AutoDerivedRuleEffect

    payload = {
        "dependent_variable": "creditor_names",
        "rule_effect": "pluralize_by_count",
        "singular_value": "has",
        "plural_value": "have",
    }
    result = _AUTHOR_ADAPTER.validate_python(payload)
    assert isinstance(result, AutoDerivedSourceParams)
    assert result.rule_effect == AutoDerivedRuleEffect.PLURALIZE_BY_COUNT
    assert result.singular_value == "has"
    assert result.plural_value == "have"
    # Empty-string singular is valid (e.g. `s` suffix in `Creditor{s}`)
    payload_with_empty_singular = {
        "dependent_variable": "creditor_names",
        "rule_effect": "pluralize_by_count",
        "singular_value": "",
        "plural_value": "s",
    }
    result = _AUTHOR_ADAPTER.validate_python(payload_with_empty_singular)
    assert result.singular_value == ""
    assert result.plural_value == "s"


@pytest.mark.unit
def test_auto_derived_pluralize_by_count_rejects_missing_pair():
    """pluralize_by_count without singular_value or plural_value fails validation."""
    import pydantic

    payload_no_singular = {
        "dependent_variable": "creditor_names",
        "rule_effect": "pluralize_by_count",
        "plural_value": "have",
    }
    with pytest.raises(pydantic.ValidationError, match="singular_value and plural_value are required"):
        AutoDerivedSourceParams.model_validate(payload_no_singular)

    payload_no_plural = {
        "dependent_variable": "creditor_names",
        "rule_effect": "pluralize_by_count",
        "singular_value": "has",
    }
    with pytest.raises(pydantic.ValidationError, match="singular_value and plural_value are required"):
        AutoDerivedSourceParams.model_validate(payload_no_plural)


@pytest.mark.unit
def test_auto_derived_extract_substring_rejects_pluralize_pair():
    """extract_substring rule_effect with singular_value/plural_value set
    is a contract violation — those fields are pluralize-only."""
    import pydantic

    payload = {
        "dependent_variable": "ecf_full",
        "rule_effect": "extract_substring",
        "singular_value": "has",
        "plural_value": "have",
    }
    with pytest.raises(pydantic.ValidationError, match="only valid when rule_effect is 'pluralize_by_count'"):
        AutoDerivedSourceParams.model_validate(payload)


@pytest.mark.unit
def test_auto_derived_drops_sibling_class_fields_silently(caplog):
    """The template-agent LLM occasionally emits AutoDerivedSourceParams
    payloads with `derived_value_type` / `format` / `rule_effect_value`
    fields that bleed in from the sibling DependentOnVariableSourceParams
    class. The before-validator strips them with a logged warning so the
    legitimate AutoDerived payload validates cleanly. This is the regression
    fix for the 502 the template engine threw when trying to compose a
    `pluralize_by_count` field for has/have."""
    from src.core.agents.types.sources import AutoDerivedRuleEffect

    payload = {
        "dependent_variable": "creditors",
        "rule_effect": "pluralize_by_count",
        "singular_value": "has",
        "plural_value": "have",
        # Bleed from DependentOnVariableSourceParams (date math):
        "derived_value_type": "date",
        "format": "%Y-%m-%d",
        "rule_effect_value": "14",
    }
    with caplog.at_level("WARNING"):
        result = AutoDerivedSourceParams.model_validate(payload)

    # Legitimate fields preserved.
    assert result.dependent_variable == "creditors"
    assert result.rule_effect == AutoDerivedRuleEffect.PLURALIZE_BY_COUNT
    assert result.singular_value == "has"
    assert result.plural_value == "have"
    # Each spurious field logged a warning at WARNING level.
    warnings = [rec.message for rec in caplog.records if rec.levelname == "WARNING"]
    assert any("derived_value_type" in m for m in warnings)
    assert any("format" in m for m in warnings)
    assert any("rule_effect_value" in m for m in warnings)


@pytest.mark.unit
def test_auto_derived_before_validator_preserves_caller_dict():
    """Defensive copy: the before-validator must not mutate the caller's
    input dict. Pydantic union retries other variants on the same dict; a
    direct mutation would corrupt downstream `DependentOnVariableSourceParams`
    validation by stripping its required `derived_value_type`."""
    payload = {
        "dependent_variable": "creditors",
        "rule_effect": "pluralize_by_count",
        "singular_value": "has",
        "plural_value": "have",
        "derived_value_type": "date",
    }
    snapshot = dict(payload)
    AutoDerivedSourceParams.model_validate(payload)
    assert payload == snapshot, (
        "AutoDerivedSourceParams before-validator mutated the caller's dict; "
        "pydantic union retries on the same input would now corrupt sibling "
        "DependentOnVariableSourceParams validation."
    )


@pytest.mark.unit
def test_dependent_on_variable_still_validates_after_auto_derived_attempt():
    """Confirm the union-validator interaction: a DependentOnVariableSourceParams
    payload should still validate as that class even though the AutoDerived
    before-validator runs first (and would otherwise strip the date-math
    fields if it weren't using a defensive copy)."""
    payload = {
        "dependent_variable": "petition_filing_date",
        "derived_value_type": "date",
        "format": "%B %-d, %Y",
        "rule_effect": "increment_by_days",
        "rule_effect_value": "14",
    }
    result = _AUTHOR_ADAPTER.validate_python(payload)
    from src.core.agents.types.sources import DependentOnVariableSourceParams
    assert isinstance(result, DependentOnVariableSourceParams)
    assert result.derived_value_type.value == "date"
    assert result.rule_effect_value == "14"


@pytest.mark.unit
def test_author_union_minimal_gmail_payload_still_validates():
    payload = {"subject_query": "Voluntary Petition"}
    result = _AUTHOR_ADAPTER.validate_python(payload)
    assert isinstance(result, GmailSourceParams)


@pytest.mark.unit
def test_author_union_minimal_vector_payload_still_validates():
    payload = {"text_query": "case status"}
    result = _AUTHOR_ADAPTER.validate_python(payload)
    assert isinstance(result, VectorSourceParams)


@pytest.mark.unit
@pytest.mark.parametrize(
    "params_class, valid_payload",
    [
        (GmailSourceParams, {"subject_query": "x"}),
        (CourtDriveSourceParams, {"subject_query": "x"}),
        (VectorSourceParams, {"text_query": "x"}),
        (ConstantsSourceParams, {"short_code": "FIRM_NAME"}),
        (
            GroupDropdownSourceParams,
            {
                "group_label": "G",
                "left_label": "L",
                "right_label": "R",
                "right_partner_variable": "p",
            },
        ),
        (
            RecoChipsEmailSourceParams,
            {"label": "L"},
        ),
        (
            RecoChipsCaseVectorSourceParams,
            {"text_query": "x", "label": "L", "example_sentence": "S"},
        ),
        (
            GroupDropdownComposite,
            {
                "group_label": "G",
                "left_variable": "lv",
                "left_label": "L",
                "left_template_variable_string": "[[lv]]",
                "right_variable": "rv",
                "right_label": "R",
                "right_template_variable_string": "[[rv]]",
            },
        ),
        (
            DropdownEmailSourceParams,
            {"label": "L", "example_format": "F"},
        ),
        (
            DropdownCaseVectorSourceParams,
            {"text_query": "x", "label": "L", "example_format": "F"},
        ),
        (
            AutoDerivedSourceParams,
            {"dependent_variable": "p"},
        ),
    ],
)
def test_extras_are_rejected_on_individual_classes(params_class, valid_payload):
    """Adding any unknown key to an otherwise-valid payload must fail. This is
    the property that makes union discrimination correct — without it, Pydantic
    silently drops extras and picks the loosest variant."""
    payload_with_extra = {**valid_payload, "unexpected_field": "boom"}
    with pytest.raises(ValidationError, match="Extra inputs are not permitted|extra_forbidden"):
        params_class.model_validate(payload_with_extra)


# ─── MultiSelectFromGmailSourceParams ─────────────────────────────────


@pytest.mark.unit
def test_multi_select_from_gmail_round_trips_with_subject_query_only():
    """Subject query alone is sufficient (mirrors GmailSourceParams)."""
    from src.core.agents.types.sources import MultiSelectFromGmailSourceParams

    payload = {
        "label": "Select Creditors",
        "subject_query": "Proof of Claim",
        "example_formats": ["JPMorgan Chase Bank (POC 3)"],
    }
    result = MultiSelectFromGmailSourceParams.model_validate(payload)
    assert result.label == "Select Creditors"
    assert result.subject_query == "Proof of Claim"
    assert result.body_query is None
    assert result.scope_to_current_case is True  # default
    assert result.min_picks == 1
    assert result.oxford is True


@pytest.mark.unit
def test_multi_select_from_gmail_rejects_when_neither_subject_nor_body_set():
    """At least one of subject_query / body_query must be non-empty —
    same gate as plain Gmail / dropdown_from_gmail / reco_chips_from_gmail."""
    from src.core.agents.types.sources import MultiSelectFromGmailSourceParams

    payload = {
        "label": "Select Creditors",
        "example_formats": ["A"],
    }
    with pytest.raises(ValidationError, match="at least one of subject_query / body_query"):
        MultiSelectFromGmailSourceParams.model_validate(payload)


@pytest.mark.unit
def test_multi_select_from_gmail_rejects_max_picks_below_min_picks():
    from src.core.agents.types.sources import MultiSelectFromGmailSourceParams

    payload = {
        "label": "Select Creditors",
        "subject_query": "Proof of Claim",
        "example_formats": ["A"],
        "min_picks": 3,
        "max_picks": 1,
    }
    with pytest.raises(ValidationError, match="max_picks must be >= min_picks"):
        MultiSelectFromGmailSourceParams.model_validate(payload)


@pytest.mark.unit
def test_multi_select_from_gmail_rejects_blank_example_format_entries():
    from src.core.agents.types.sources import MultiSelectFromGmailSourceParams

    payload = {
        "label": "Select Creditors",
        "subject_query": "Proof of Claim",
        "example_formats": ["   "],
    }
    with pytest.raises(ValidationError, match="example_formats entries must be non-empty"):
        MultiSelectFromGmailSourceParams.model_validate(payload)


@pytest.mark.unit
def test_author_union_picks_multi_select_from_gmail_over_other_email_sources():
    """A payload with `example_formats` (list) + `subject_query` is the
    multi-select-from-gmail signature. RecoChipsEmailSourceParams /
    DropdownEmailSourceParams use singular `example_format` (string), so
    extra='forbid' on each class steers the union to the right variant."""
    from src.core.agents.types.sources import MultiSelectFromGmailSourceParams

    payload = {
        "label": "Select Creditors",
        "subject_query": "Proof of Claim",
        "example_formats": ["JPMorgan Chase Bank (POC 3)"],
    }
    result = _AUTHOR_ADAPTER.validate_python(payload)
    assert isinstance(result, MultiSelectFromGmailSourceParams)


# ─── inherit_from_parent (Phase 1B) ─────────────────────────────────────


@pytest.mark.unit
def test_inherit_from_parent_accepts_empty_payload():
    from src.core.agents.types.sources import InheritFromParentSourceParams
    result = InheritFromParentSourceParams()
    assert result.fallback_value is None


@pytest.mark.unit
def test_inherit_from_parent_accepts_fallback_value():
    from src.core.agents.types.sources import InheritFromParentSourceParams
    result = InheritFromParentSourceParams(fallback_value="[no parent]")
    assert result.fallback_value == "[no parent]"


@pytest.mark.unit
def test_inherit_from_parent_rejects_extras():
    from pydantic import ValidationError

    from src.core.agents.types.sources import InheritFromParentSourceParams

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        InheritFromParentSourceParams.model_validate(
            {"fallback_value": "x", "parent_variable": "case_number"}
        )
