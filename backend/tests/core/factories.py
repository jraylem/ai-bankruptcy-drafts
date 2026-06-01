"""Plain-function builders for core domain types.

Every factory has sensible defaults so tests only pass the fields that
matter for the scenario. Factories compose — e.g. make_agent_config
accepts a pre-built list of TemplateFields.
"""

from typing import Literal

from typing import Any

from src.core.agents.context import FetchedContext
from src.core.agents.resolvers.user_input_resolver import GroupDropdownPick
from src.core.agents.types.resolution import ResolvedTemplateValue
from src.core.agents.types.sources import (
    DEFAULT_DATE_FORMAT,
    CourtDriveSourceParams,
    DependentOnVariableSourceParams,
    DerivedValueType,
    FieldSource,
    GmailSourceParams,
    GroupDropdownComposite,
    DropdownCaseVectorSourceParams,
    DropdownEmailSourceParams,
    GroupDropdownSourceParams,
    RecoChipsCaseVectorSourceParams,
    RecoChipsEmailSourceParams,
    RuleEffect,
    SystemGeneratedSourceParams,
    SystemGeneratedType,
)
from src.core.agents.types.spec import AgentConfig, TemplateField, TemplateVariable
from src.core.common.services.email import Email, EmailSearchResult, EmailType


def make_resolved_value(
    property_name: str = "x",
    value: str = "42",
    reasoning: str = "test",
    confidence: Literal["high", "medium", "low"] = "high",
) -> ResolvedTemplateValue:
    return ResolvedTemplateValue(
        property_name=property_name,
        value=value,
        reasoning=reasoning,
        confidence=confidence,
    )


_UNSET = object()


def make_template_variable(
    template_variable: str = "debtor_name",
    template_index: int = 0,
    source: FieldSource | None = None,
    source_params=None,
    template_property_marker: str | None = None,
    template_variable_string=_UNSET,
    template_identifying_text_match: str | None = None,
    description: str | None = None,
    instruction: str | None = None,
) -> TemplateVariable:
    # Default to a placeholder string so the produced variable is `kind="physical"`.
    # The validator that requires every virtual variable to have an auto_derive
    # child would otherwise reject any test fixture that left this unset.
    # Tests that need a virtual variable explicitly pass `template_variable_string=None`.
    placeholder = (
        f"[[{template_variable}]]"
        if template_variable_string is _UNSET
        else template_variable_string
    )
    return TemplateVariable(
        template_variable=template_variable,
        template_index=template_index,
        source=source,
        source_params=source_params,
        template_property_marker=template_property_marker,
        template_variable_string=placeholder,
        template_identifying_text_match=template_identifying_text_match,
        description=description,
        instruction=instruction,
    )


def make_template_field(
    property_name: str = "debtor_name",
    source: FieldSource = FieldSource.GMAIL,
    source_params=None,
    instruction: str | None = None,
    template_variable_string: str | None = None,
    template_property_marker: str | None = None,
) -> TemplateField:
    return TemplateField(
        property_name=property_name,
        source=source,
        source_params=source_params,
        instruction=instruction,
        template_variable_string=template_variable_string,
        template_property_marker=template_property_marker,
    )


def make_dependent_params(
    dependent_variable: str = "parent",
    derived_value_type: DerivedValueType = DerivedValueType.DATE,
    rule_effect: RuleEffect = RuleEffect.INCREMENT_BY_DAYS,
    rule_effect_value: str | None = "14",
    date_format: str = DEFAULT_DATE_FORMAT,
) -> DependentOnVariableSourceParams:
    return DependentOnVariableSourceParams(
        dependent_variable=dependent_variable,
        derived_value_type=derived_value_type,
        format=date_format,
        rule_effect=rule_effect,
        rule_effect_value=rule_effect_value,
    )


def make_agent_config(
    template_id: str = "tpl_test",
    fields: list[TemplateField] | None = None,
) -> AgentConfig:
    return AgentConfig(
        template_id=template_id,
        template_fields=fields if fields is not None else [],
    )


def make_gmail_source_params(
    subject_query: str | None = None,
    body_query: str | None = None,
) -> GmailSourceParams:
    return GmailSourceParams(subject_query=subject_query, body_query=body_query)


def make_court_drive_source_params(
    subject_query: str | None = None,
    body_query: str | None = None,
) -> CourtDriveSourceParams:
    return CourtDriveSourceParams(subject_query=subject_query, body_query=body_query)


def make_system_generated_params(
    type: SystemGeneratedType = SystemGeneratedType.CURRENT_DATE,
    format: str = DEFAULT_DATE_FORMAT,
) -> SystemGeneratedSourceParams:
    return SystemGeneratedSourceParams(type=type, format=format)


def make_group_dropdown_source_params(
    subject_query: str | None = None,
    body_query: str | None = None,
    group_label: str = "Docket",
    left_label: str = "Docket Number",
    right_label: str = "Docket Title",
    right_partner_variable: str = "partner",
) -> GroupDropdownSourceParams:
    return GroupDropdownSourceParams(
        subject_query=subject_query,
        body_query=body_query,
        group_label=group_label,
        left_label=left_label,
        right_label=right_label,
        right_partner_variable=right_partner_variable,
    )


def make_group_dropdown_composite(
    subject_query: str | None = None,
    body_query: str | None = None,
    group_label: str = "Docket",
    left_variable: str = "docket_number",
    left_label: str = "Docket Number",
    left_template_variable_string: str = "[[docket_number]]",
    right_variable: str = "docket_title",
    right_label: str = "Docket Title",
    right_template_variable_string: str = "[[docket_title]]",
) -> GroupDropdownComposite:
    return GroupDropdownComposite(
        subject_query=subject_query,
        body_query=body_query,
        group_label=group_label,
        left_variable=left_variable,
        left_label=left_label,
        left_template_variable_string=left_template_variable_string,
        right_variable=right_variable,
        right_label=right_label,
        right_template_variable_string=right_template_variable_string,
    )


def make_reco_chips_source_params(
    label: str = "Change in Circumstances",
    subject_query: str | None = None,
    body_query: str | None = None,
    example_sentence: str | None = None,
) -> RecoChipsEmailSourceParams:
    return RecoChipsEmailSourceParams(
        label=label,
        subject_query=subject_query,
        body_query=body_query,
        example_sentence=example_sentence,
    )


def make_reco_chips_case_vector_source_params(
    *,
    text_query: str,
    example_sentence: str,
    label: str = "Employment Description",
) -> RecoChipsCaseVectorSourceParams:
    """Both text_query and example_sentence are required on the real model;
    callers must pass them explicitly so tests exercise the intended params."""
    return RecoChipsCaseVectorSourceParams(
        label=label,
        text_query=text_query,
        example_sentence=example_sentence,
    )


def make_dropdown_email_source_params(
    *,
    label: str,
    example_format: str,
    subject_query: str | None = None,
    body_query: str | None = None,
) -> DropdownEmailSourceParams:
    """Both label and example_format are required on the real model;
    callers pass them explicitly so tests exercise the intended params."""
    return DropdownEmailSourceParams(
        label=label,
        example_format=example_format,
        subject_query=subject_query,
        body_query=body_query,
    )


def make_dropdown_case_vector_source_params(
    *,
    text_query: str,
    label: str,
    example_format: str,
) -> DropdownCaseVectorSourceParams:
    """All three fields are required on the real model; kw-only to keep
    call sites explicit."""
    return DropdownCaseVectorSourceParams(
        text_query=text_query,
        label=label,
        example_format=example_format,
    )


def make_fetched_context(
    property_name: str = "x",
    source: FieldSource = FieldSource.GMAIL,
    raw_result: Any = None,
    instruction: str | None = None,
) -> FetchedContext:
    return FetchedContext(
        property_name=property_name,
        source=source,
        raw_result=raw_result,
        instruction=instruction,
    )


def make_group_dropdown_pick(left: str = "L", right: str = "R") -> GroupDropdownPick:
    return GroupDropdownPick(left=left, right=right)


def make_email(
    id: str = "msg_1",
    subject: str = "Case 26-10700 filing",
    body: str = "Body text",
    sender: str | None = "clerk@court.example",
    date: str | None = "Mon, 1 Jan 2026 10:00:00 -0500",
) -> Email:
    return Email(id=id, subject=subject, body=body, sender=sender, date=date)


def make_email_search_result(
    emails: list[Email] | None = None,
    source: EmailType = EmailType.GMAIL,
) -> EmailSearchResult:
    emails = emails if emails is not None else []
    return EmailSearchResult(emails=emails, total=len(emails), source=source)
