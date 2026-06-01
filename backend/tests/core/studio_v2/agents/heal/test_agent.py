"""Tests for UserInputHealAgentV2.run + heal_resolved_values.

LLM calls are patched via `_invoke` so no Anthropic round-trip
happens. The interesting test logic is around:
- Soft failure (LLM error / empty / None → raw value passthrough).
- Per-shape eligibility (which (source × shape) gets healed).
- Heal-target selection (example_format → preferred_format vs
  output_expectation → example_sentence).
"""

from unittest.mock import AsyncMock, patch

import pytest

from src.core.studio_v2.agents.heal.agent import (
    UserInputHealAgentV2,
    _HealedFragmentV2,
    _needs_heal,
    _resolve_heal_target,
)
from src.core.studio_v2.types.fields import TemplateFieldV2
from src.core.studio_v2.types.resolution import ResolvedTemplateValueV2
from src.core.studio_v2.types.wizard_sources import (
    AuthorInputKind,
    PresentationShape,
    SourceKind,
    WizardSourceParams,
)


_FIELD_UUID = "00000000-0000-0000-0000-000000000001"
_TEMPLATE_UUID = "00000000-0000-0000-0000-000000000002"


def _field(name, params):
    return TemplateFieldV2(
        id=_FIELD_UUID, template_id=_TEMPLATE_UUID,
        template_variable=name, template_index=0, params=params,
    )


# ─── _needs_heal ─────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.parametrize(
    "params,expected",
    [
        # author_input — every kind heals
        (WizardSourceParams(source=SourceKind.AUTHOR_INPUT,
                            author_input_kind=AuthorInputKind.PLAIN_TEXT), True),
        (WizardSourceParams(source=SourceKind.AUTHOR_INPUT,
                            author_input_kind=AuthorInputKind.DATE), True),
        (WizardSourceParams(source=SourceKind.AUTHOR_INPUT,
                            author_input_kind=AuthorInputKind.WITH_DOCS), True),
        # gmail/case_file raw — now heals too (post-extraction shape
        # pass against the template marker). Earlier behavior was
        # False; flipped so the rendered docx is consistent across
        # raw vs user-pick extractions.
        (WizardSourceParams(source=SourceKind.GMAIL,
                            presentation_shape=PresentationShape.RAW), True),
        (WizardSourceParams(source=SourceKind.CASE_FILE,
                            presentation_shape=PresentationShape.RAW), True),
        # gmail/case_file pick shapes — heal
        (WizardSourceParams(source=SourceKind.GMAIL,
                            presentation_shape=PresentationShape.DROPDOWN), True),
        (WizardSourceParams(source=SourceKind.CASE_FILE,
                            presentation_shape=PresentationShape.CHIP), True),
        (WizardSourceParams(source=SourceKind.GMAIL,
                            presentation_shape=PresentationShape.MULTI_SELECT), True),
        # attorney raw — no heal
        (WizardSourceParams(source=SourceKind.ATTORNEY,
                            presentation_shape=PresentationShape.RAW), False),
        # attorney pick — heal
        (WizardSourceParams(source=SourceKind.ATTORNEY,
                            presentation_shape=PresentationShape.DROPDOWN), True),
        # System / inherit / current_date / constants / derived — no heal
        (WizardSourceParams(source=SourceKind.CURRENT_DATE), False),
        (WizardSourceParams(source=SourceKind.CONSTANTS), False),
        (WizardSourceParams(source=SourceKind.VALUE_FROM_PARENT_BUNDLE), False),
        (WizardSourceParams(source=SourceKind.DERIVED_FROM_VARIABLE), False),
    ],
)
def test_needs_heal_per_source_shape(params, expected):
    assert _needs_heal(params) is expected


# ─── _resolve_heal_target ────────────────────────────────────────────


@pytest.mark.unit
def test_heal_target_dropdown_uses_example_format_as_preferred_format():
    params = WizardSourceParams(
        source=SourceKind.GMAIL,
        presentation_shape=PresentationShape.DROPDOWN,
        example_format="Acme Bank — $1,200",
    )
    target, kind = _resolve_heal_target(params)
    assert target == "Acme Bank — $1,200"
    assert kind == "preferred_format"


@pytest.mark.unit
def test_heal_target_chip_uses_output_expectation_as_example_sentence():
    params = WizardSourceParams(
        source=SourceKind.GMAIL,
        presentation_shape=PresentationShape.CHIP,
        output_expectation="Concise objection statement.",
    )
    target, kind = _resolve_heal_target(params)
    assert target == "Concise objection statement."
    assert kind == "example_sentence"


@pytest.mark.unit
def test_heal_target_author_plain_text_falls_back_to_marker():
    """When output_expectation is missing, the field's
    `template_property_marker` (original phrase from the source doc)
    becomes the heal target. Without this fallback the heal agent
    receives no guidance and returns the user's value unchanged."""
    params = WizardSourceParams(
        source=SourceKind.AUTHOR_INPUT,
        author_input_kind=AuthorInputKind.PLAIN_TEXT,
        output_expectation=None,
    )
    target, kind = _resolve_heal_target(
        params,
        template_property_marker="the claim is barred by the statute of limitations",
    )
    assert target == "the claim is barred by the statute of limitations"
    assert kind == "example_sentence"


@pytest.mark.unit
def test_heal_target_dropdown_falls_back_through_marker():
    """Dropdown priority: example_format → output_expectation → marker."""
    params = WizardSourceParams(
        source=SourceKind.GMAIL,
        presentation_shape=PresentationShape.DROPDOWN,
        example_format=None,
        output_expectation=None,
    )
    target, kind = _resolve_heal_target(
        params,
        template_property_marker="Wells Fargo — $9,330.50",
    )
    assert target == "Wells Fargo — $9,330.50"
    assert kind == "preferred_format"


@pytest.mark.unit
def test_heal_target_no_marker_no_expectation_returns_none():
    """All sources missing → no guidance; heal still runs but
    operates on user_value alone with no example/format hint."""
    params = WizardSourceParams(
        source=SourceKind.AUTHOR_INPUT,
        author_input_kind=AuthorInputKind.PLAIN_TEXT,
        output_expectation=None,
    )
    target, kind = _resolve_heal_target(params, template_property_marker=None)
    assert target is None
    assert kind == "example_sentence"


@pytest.mark.unit
def test_heal_target_author_plain_text_uses_output_expectation():
    """When output_expectation IS present, it wins over the marker."""
    params = WizardSourceParams(
        source=SourceKind.AUTHOR_INPUT,
        author_input_kind=AuthorInputKind.PLAIN_TEXT,
        output_expectation="A formal hardship paragraph.",
    )
    target, kind = _resolve_heal_target(
        params,
        template_property_marker="some marker value",  # ignored, expectation wins
    )
    assert target == "A formal hardship paragraph."
    assert kind == "example_sentence"


# ─── run() — single-field heal call ──────────────────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_returns_llm_text_stripped():
    with patch.object(
        UserInputHealAgentV2, "_invoke",
        new=AsyncMock(return_value=_HealedFragmentV2(text="  healed prose  ")),
    ):
        out = await UserInputHealAgentV2.run(
            template_paragraph="x [[ph]] y",
            placeholder="[[ph]]",
            user_value="raw user value",
        )
    assert out == "healed prose"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_llm_exception_returns_raw_user_value():
    with patch.object(
        UserInputHealAgentV2, "_invoke", side_effect=RuntimeError("boom"),
    ):
        out = await UserInputHealAgentV2.run(
            template_paragraph="x [[ph]] y",
            placeholder="[[ph]]",
            user_value="raw user value",
        )
    assert out == "raw user value"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_llm_none_returns_raw_user_value():
    with patch.object(
        UserInputHealAgentV2, "_invoke", new=AsyncMock(return_value=None),
    ):
        out = await UserInputHealAgentV2.run(
            template_paragraph="x [[ph]] y",
            placeholder="[[ph]]",
            user_value="raw user value",
        )
    assert out == "raw user value"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_llm_empty_text_returns_raw_user_value():
    with patch.object(
        UserInputHealAgentV2, "_invoke",
        new=AsyncMock(return_value=_HealedFragmentV2(text="")),
    ):
        out = await UserInputHealAgentV2.run(
            template_paragraph="x [[ph]] y",
            placeholder="[[ph]]",
            user_value="raw user value",
        )
    assert out == "raw user value"


# ─── heal_resolved_values ────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
async def test_heal_resolved_values_only_heals_eligible():
    """A `current_date` field should pass through; a `gmail dropdown`
    field should get healed."""
    fields = [
        _field(
            "doc_date",
            WizardSourceParams(source=SourceKind.CURRENT_DATE),
        ),
        _field(
            "creditor",
            WizardSourceParams(
                source=SourceKind.GMAIL,
                presentation_shape=PresentationShape.DROPDOWN,
            ),
        ),
    ]
    resolved = [
        ResolvedTemplateValueV2(template_variable="doc_date", value="January 21, 2026"),
        ResolvedTemplateValueV2(template_variable="creditor", value="acme bank"),
    ]
    with patch(
        "src.core.studio_v2.agents.heal.agent.DocxTemplateService.find_paragraph_containing",
        return_value="The Debtor's creditor is [[creditor]].",
    ), patch.object(
        UserInputHealAgentV2, "_invoke",
        new=AsyncMock(return_value=_HealedFragmentV2(text="Acme Bank, N.A.")),
    ):
        out = await UserInputHealAgentV2.heal_resolved_values(
            template_bytes=b"\x00\x00",
            template_fields=fields,
            resolved_values=resolved,
        )
    # current_date row unchanged.
    assert out[0].value == "January 21, 2026"
    # gmail dropdown row healed.
    assert out[1].value == "Acme Bank, N.A."
    assert "healed" in out[1].note.lower()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_heal_resolved_values_skips_when_no_paragraph_found():
    """If the docx doesn't contain the [[placeholder]], skip — leave
    the resolved value alone."""
    fields = [
        _field(
            "x",
            WizardSourceParams(
                source=SourceKind.AUTHOR_INPUT,
                author_input_kind=AuthorInputKind.PLAIN_TEXT,
            ),
        ),
    ]
    resolved = [ResolvedTemplateValueV2(template_variable="x", value="raw")]
    with patch(
        "src.core.studio_v2.agents.heal.agent.DocxTemplateService.find_paragraph_containing",
        return_value=None,
    ), patch.object(UserInputHealAgentV2, "_invoke", new=AsyncMock()) as invoke_mock:
        out = await UserInputHealAgentV2.heal_resolved_values(
            template_bytes=b"\x00",
            template_fields=fields,
            resolved_values=resolved,
        )
    invoke_mock.assert_not_called()
    assert out[0].value == "raw"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_heal_resolved_values_empty_jobs_is_a_no_op():
    """No heal-eligible fields → no LLM calls, return original list."""
    fields = [_field("x", WizardSourceParams(source=SourceKind.CURRENT_DATE))]
    resolved = [ResolvedTemplateValueV2(template_variable="x", value="anything")]
    with patch.object(UserInputHealAgentV2, "run", new=AsyncMock()) as run_mock:
        out = await UserInputHealAgentV2.heal_resolved_values(
            template_bytes=b"\x00", template_fields=fields, resolved_values=resolved,
        )
    run_mock.assert_not_called()
    assert out is resolved  # identity preserved
