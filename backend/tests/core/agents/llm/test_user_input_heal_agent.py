"""Tests for UserInputHealAgent — grammar + legal-tone heal on reco-chip AND dropdown picks.

Two public surfaces:
  UserInputHealAgent.run(template_paragraph, placeholder, user_value, heal_target?, heal_target_kind?)
      — one heal call, returns healed fragment or raw user_value on failure.
  UserInputHealAgent.heal_resolved_values(template_bytes, agent_config, resolved_values)
      — batch heal across a resolved-values list, touches reco-chip + dropdown entries.
"""

from unittest.mock import AsyncMock

import pytest
from docx import Document

from src.core.agents.llm.user_input_heal import (
    UserInputHealAgent,
    _HealedFragment,
)
from src.core.agents.types.sources import FieldSource
from src.core.agents.types.spec import AgentConfig, TemplateField
from tests.core.factories import (
    make_dropdown_case_vector_source_params,
    make_gmail_source_params,
    make_reco_chips_case_vector_source_params,
    make_reco_chips_source_params,
    make_resolved_value,
)


def _docx_with_paragraphs(paragraphs: list[str]) -> bytes:
    """Build an in-memory DOCX with given paragraph texts, return its bytes."""
    from io import BytesIO

    doc = Document()
    for text in paragraphs:
        doc.add_paragraph(text)
    buf = BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf.read()


def _field(
    property_name: str,
    source: FieldSource,
    source_params=None,
    template_variable_string: str | None = None,
    template_property_marker: str | None = None,
) -> TemplateField:
    return TemplateField(
        property_name=property_name,
        source=source,
        source_params=source_params,
        template_variable_string=template_variable_string or f"[[{property_name}]]",
        template_property_marker=template_property_marker,
    )


# ─── UserInputHealAgent.run ───────────────────────────────────────────


@pytest.mark.unit
async def test_run_returns_healed_text_from_invoke(mock_agent_invoke):
    captured = mock_agent_invoke(_HealedFragment(text="has been employed at UPS for 37 years"))

    result = await UserInputHealAgent.run(
        template_paragraph="The Debtor, [[debtor_name]], [[employment_description]].",
        placeholder="[[employment_description]]",
        user_value="The Debtor has been employed at UPS for 37 years",
    )

    assert result == "has been employed at UPS for 37 years"
    assert captured["run_name"] == "UserInputHeal"
    assert captured["metadata"] == {"placeholder": "[[employment_description]]"}
    prompt = captured["prompt"]
    assert "[[employment_description]]" in prompt
    assert "The Debtor, [[debtor_name]], [[employment_description]]." in prompt
    assert "The Debtor has been employed at UPS for 37 years" in prompt


@pytest.mark.unit
async def test_run_returns_user_value_unchanged_on_none(mock_agent_invoke):
    mock_agent_invoke(None)

    result = await UserInputHealAgent.run(
        template_paragraph="x [[p]] y",
        placeholder="[[p]]",
        user_value="raw user text",
    )

    assert result == "raw user text"


@pytest.mark.unit
async def test_run_returns_user_value_unchanged_on_exception(mock_agent_invoke):
    mock_agent_invoke(RuntimeError("LLM failed"))

    result = await UserInputHealAgent.run(
        template_paragraph="x [[p]] y",
        placeholder="[[p]]",
        user_value="raw user text",
    )

    assert result == "raw user text"


@pytest.mark.unit
async def test_run_returns_user_value_unchanged_on_empty_text(mock_agent_invoke):
    mock_agent_invoke(_HealedFragment(text="   "))

    result = await UserInputHealAgent.run(
        template_paragraph="x [[p]] y",
        placeholder="[[p]]",
        user_value="raw user text",
    )

    assert result == "raw user text"


@pytest.mark.unit
async def test_run_includes_example_sentence_block_for_reco_chips(mock_agent_invoke):
    captured = mock_agent_invoke(_HealedFragment(text="healed"))

    await UserInputHealAgent.run(
        template_paragraph="x [[p]] y",
        placeholder="[[p]]",
        user_value="raw",
        heal_target="The Debtor is employed in a capacity where their role involves handling sensitive consumer information.",
        heal_target_kind="example_sentence",
    )

    prompt = captured["prompt"]
    assert "GUIDE" in prompt
    assert "handling sensitive consumer information" in prompt
    assert "PREFERRED PRESENTATION" not in prompt


@pytest.mark.unit
async def test_run_includes_preferred_presentation_block_for_dropdown(mock_agent_invoke):
    captured = mock_agent_invoke(_HealedFragment(text="healed"))

    await UserInputHealAgent.run(
        template_paragraph="The motion type is [[motion_type]].",
        placeholder="[[motion_type]]",
        user_value="MOTION TO MODIFY PLAN",
        heal_target="Motion to Modify Plan",
        heal_target_kind="preferred_format",
    )

    prompt = captured["prompt"]
    assert "PREFERRED PRESENTATION" in prompt
    assert "Motion to Modify Plan" in prompt
    assert "GUIDE" not in prompt


@pytest.mark.unit
@pytest.mark.parametrize("heal_target, heal_target_kind", [
    (None, None),
    ("", "example_sentence"),
    ("   \n  ", "example_sentence"),
    ("some text", None),
    (None, "preferred_format"),
])
async def test_run_omits_heal_target_block_when_missing(mock_agent_invoke, heal_target, heal_target_kind):
    """No heal block rendered when either heal_target is blank or kind is None."""
    captured = mock_agent_invoke(_HealedFragment(text="healed"))

    await UserInputHealAgent.run(
        template_paragraph="x [[p]] y",
        placeholder="[[p]]",
        user_value="raw",
        heal_target=heal_target,
        heal_target_kind=heal_target_kind,
    )

    prompt = captured["prompt"]
    assert "GUIDE" not in prompt
    assert "PREFERRED PRESENTATION" not in prompt


# ─── UserInputHealAgent.heal_resolved_values ──────────────────────────


@pytest.mark.unit
async def test_heal_resolved_values_skips_non_user_input_fields(monkeypatch):
    """Only user-input (reco-chip OR dropdown) values go through the LLM —
    draft/gmail values pass through."""
    run_mock = AsyncMock(return_value="HEALED")
    monkeypatch.setattr(UserInputHealAgent, "run", run_mock)

    template_bytes = _docx_with_paragraphs([
        "In re: [[case_number]]",
        "The Debtor, [[debtor_name]], [[employment_description]].",
    ])
    agent_config = AgentConfig(
        template_id="tpl",
        template_fields=[
            _field("case_number", FieldSource.GMAIL, make_gmail_source_params()),
            _field(
                "employment_description",
                FieldSource.RECO_CHIPS_FROM_CASE_VECTOR,
                make_reco_chips_case_vector_source_params(
                    text_query="employer", example_sentence="The Debtor is employed.",
                ),
            ),
        ],
    )
    resolved = [
        make_resolved_value(property_name="case_number", value="26-14090"),
        make_resolved_value(property_name="employment_description", value="raw user text"),
    ]

    out = await UserInputHealAgent.heal_resolved_values(
        template_bytes=template_bytes,
        agent_config=agent_config,
        resolved_values=resolved,
    )

    assert run_mock.await_count == 1
    assert out[0].value == "26-14090"
    assert out[1].value == "HEALED"
    assert "[grammar/tone healed]" in out[1].reasoning


@pytest.mark.unit
async def test_heal_resolved_values_parallel_dispatch_across_families(monkeypatch):
    """Reco-chip field AND dropdown field each get their own heal call in parallel."""
    run_mock = AsyncMock(side_effect=["RECO-healed", "DROPDOWN-healed"])
    monkeypatch.setattr(UserInputHealAgent, "run", run_mock)

    template_bytes = _docx_with_paragraphs([
        "Paragraph with [[chip_field]].",
        "The motion type is [[motion_type]].",
    ])
    agent_config = AgentConfig(
        template_id="tpl",
        template_fields=[
            _field("chip_field", FieldSource.RECO_CHIPS_FROM_GMAIL, make_reco_chips_source_params()),
            _field(
                "motion_type",
                FieldSource.DROPDOWN_FROM_CASE_VECTOR,
                make_dropdown_case_vector_source_params(
                    text_query="motion type", label="Motion Type", example_format="Motion to Modify Plan",
                ),
                template_property_marker="Motion to Modify Plan",
            ),
        ],
    )
    resolved = [
        make_resolved_value(property_name="chip_field", value="raw chip"),
        make_resolved_value(property_name="motion_type", value="MOTION TO MODIFY PLAN"),
    ]

    out = await UserInputHealAgent.heal_resolved_values(
        template_bytes=template_bytes,
        agent_config=agent_config,
        resolved_values=resolved,
    )

    assert run_mock.await_count == 2
    assert out[0].value == "RECO-healed"
    assert out[1].value == "DROPDOWN-healed"


@pytest.mark.unit
async def test_heal_resolved_values_dropdown_uses_template_property_marker(monkeypatch):
    """Dropdown field heal sends template_property_marker as heal_target with
    kind='preferred_format'."""
    captured = {}

    async def fake_run(template_paragraph, placeholder, user_value, heal_target=None, heal_target_kind=None, author_instruction=None):
        captured["heal_target"] = heal_target
        captured["heal_target_kind"] = heal_target_kind
        return "healed"

    monkeypatch.setattr(UserInputHealAgent, "run", fake_run)

    template_bytes = _docx_with_paragraphs(["The motion type is [[motion_type]]."])
    agent_config = AgentConfig(
        template_id="tpl",
        template_fields=[
            _field(
                "motion_type",
                FieldSource.DROPDOWN_FROM_CASE_VECTOR,
                make_dropdown_case_vector_source_params(
                    text_query="motion type", label="Motion Type", example_format="Motion to Modify Plan",
                ),
                template_property_marker="Motion to Modify Plan",
            ),
        ],
    )
    resolved = [make_resolved_value(property_name="motion_type", value="motion to modify plan")]

    await UserInputHealAgent.heal_resolved_values(
        template_bytes=template_bytes,
        agent_config=agent_config,
        resolved_values=resolved,
    )

    assert captured["heal_target"] == "Motion to Modify Plan"
    assert captured["heal_target_kind"] == "preferred_format"


@pytest.mark.unit
async def test_heal_resolved_values_dropdown_from_constants_uses_template_property_marker(monkeypatch):
    """dropdown_from_constants heals the same way as other dropdowns — picked
    value flows through UserInputHealAgent with template_property_marker as
    the preferred-format target, so 'Chad Van Horn' can heal to 'Chad Van
    Horn, Esq.' when the template's marker carries the suffix."""
    from src.core.agents.types.sources import DropdownFromConstantsSourceParams

    captured = {}

    async def fake_run(template_paragraph, placeholder, user_value, heal_target=None, heal_target_kind=None, author_instruction=None):
        captured["heal_target"] = heal_target
        captured["heal_target_kind"] = heal_target_kind
        return "Chad Van Horn, Esq."

    monkeypatch.setattr(UserInputHealAgent, "run", fake_run)

    template_bytes = _docx_with_paragraphs(["Signed, [[attorney_name]]."])
    agent_config = AgentConfig(
        template_id="tpl",
        template_fields=[
            _field(
                "attorney_name",
                FieldSource.DROPDOWN_FROM_CONSTANTS,
                DropdownFromConstantsSourceParams(
                    reference_short_code="ATTORNEYS",
                    label="Signing Attorney",
                ),
                template_property_marker="Chad Van Horn, Esq.",
            ),
        ],
    )
    resolved = [make_resolved_value(property_name="attorney_name", value="Chad Van Horn")]

    await UserInputHealAgent.heal_resolved_values(
        template_bytes=template_bytes,
        agent_config=agent_config,
        resolved_values=resolved,
    )

    assert captured["heal_target"] == "Chad Van Horn, Esq."
    assert captured["heal_target_kind"] == "preferred_format"


@pytest.mark.unit
async def test_heal_resolved_values_reco_chips_uses_example_sentence(monkeypatch):
    """Reco-chips field heal sends example_sentence as heal_target with
    kind='example_sentence'."""
    captured = {}

    async def fake_run(template_paragraph, placeholder, user_value, heal_target=None, heal_target_kind=None, author_instruction=None):
        captured["heal_target"] = heal_target
        captured["heal_target_kind"] = heal_target_kind
        return "healed"

    monkeypatch.setattr(UserInputHealAgent, "run", fake_run)

    template_bytes = _docx_with_paragraphs(["The Debtor, [[debtor_name]], [[field]]."])
    agent_config = AgentConfig(
        template_id="tpl",
        template_fields=[
            _field(
                "field",
                FieldSource.RECO_CHIPS_FROM_CASE_VECTOR,
                make_reco_chips_case_vector_source_params(
                    text_query="employer occupation",
                    example_sentence="The Debtor is employed in a trusted role.",
                ),
            ),
        ],
    )
    resolved = [make_resolved_value(property_name="field", value="raw user text")]

    await UserInputHealAgent.heal_resolved_values(
        template_bytes=template_bytes,
        agent_config=agent_config,
        resolved_values=resolved,
    )

    assert captured["heal_target"] == "The Debtor is employed in a trusted role."
    assert captured["heal_target_kind"] == "example_sentence"


@pytest.mark.unit
async def test_heal_resolved_values_dropdown_without_marker_still_heals(monkeypatch):
    """Dropdown field with no template_property_marker still runs heal (relying
    on template_paragraph alone), just with no heal_target block."""
    captured = {}

    async def fake_run(template_paragraph, placeholder, user_value, heal_target=None, heal_target_kind=None, author_instruction=None):
        captured["heal_target"] = heal_target
        captured["heal_target_kind"] = heal_target_kind
        return "healed"

    monkeypatch.setattr(UserInputHealAgent, "run", fake_run)

    template_bytes = _docx_with_paragraphs(["[[motion_type]]"])
    agent_config = AgentConfig(
        template_id="tpl",
        template_fields=[
            _field(
                "motion_type",
                FieldSource.DROPDOWN_FROM_CASE_VECTOR,
                make_dropdown_case_vector_source_params(
                    text_query="x", label="L", example_format="F",
                ),
                template_property_marker=None,
            ),
        ],
    )
    resolved = [make_resolved_value(property_name="motion_type", value="raw")]

    out = await UserInputHealAgent.heal_resolved_values(
        template_bytes=template_bytes,
        agent_config=agent_config,
        resolved_values=resolved,
    )

    # Heal was called (once), with heal_target None so no block is rendered.
    assert captured["heal_target"] is None
    assert captured["heal_target_kind"] == "preferred_format"
    assert out[0].value == "healed"


@pytest.mark.unit
async def test_heal_resolved_values_skips_when_paragraph_not_found(monkeypatch):
    """If the placeholder isn't in the DOCX, the value is returned unchanged
    and the agent is NOT invoked."""
    run_mock = AsyncMock(return_value="SHOULD_NOT_RUN")
    monkeypatch.setattr(UserInputHealAgent, "run", run_mock)

    template_bytes = _docx_with_paragraphs(["A completely unrelated paragraph."])
    agent_config = AgentConfig(
        template_id="tpl",
        template_fields=[
            _field("missing_field", FieldSource.RECO_CHIPS_FROM_GMAIL, make_reco_chips_source_params()),
        ],
    )
    resolved = [make_resolved_value(property_name="missing_field", value="raw value")]

    out = await UserInputHealAgent.heal_resolved_values(
        template_bytes=template_bytes,
        agent_config=agent_config,
        resolved_values=resolved,
    )

    run_mock.assert_not_called()
    assert out[0].value == "raw value"
    assert "[grammar/tone healed]" not in (out[0].reasoning or "")


@pytest.mark.unit
async def test_heal_resolved_values_keeps_original_when_heal_returned_same(monkeypatch):
    """If .run returns the exact user_value, the ResolvedTemplateValue is left
    alone (no '[grammar/tone healed]' marker on an unchanged value)."""
    async def fake_run(template_paragraph, placeholder, user_value, heal_target=None, heal_target_kind=None, author_instruction=None):
        return user_value  # no-op heal

    monkeypatch.setattr(UserInputHealAgent, "run", fake_run)

    template_bytes = _docx_with_paragraphs(["[[field]]"])
    agent_config = AgentConfig(
        template_id="tpl",
        template_fields=[
            _field("field", FieldSource.RECO_CHIPS_FROM_GMAIL, make_reco_chips_source_params()),
        ],
    )
    original = make_resolved_value(property_name="field", value="unchanged", reasoning="original reason")

    out = await UserInputHealAgent.heal_resolved_values(
        template_bytes=template_bytes,
        agent_config=agent_config,
        resolved_values=[original],
    )

    assert out[0].value == "unchanged"
    assert out[0].reasoning == "original reason"
    assert "[grammar/tone healed]" not in out[0].reasoning


@pytest.mark.unit
async def test_heal_resolved_values_empty_list_shortcircuits(monkeypatch):
    """No user-input values → no LLM calls, returns the list as-is."""
    run_mock = AsyncMock(return_value="ignored")
    monkeypatch.setattr(UserInputHealAgent, "run", run_mock)

    agent_config = AgentConfig(template_id="tpl", template_fields=[])
    result = await UserInputHealAgent.heal_resolved_values(
        template_bytes=_docx_with_paragraphs(["anything"]),
        agent_config=agent_config,
        resolved_values=[],
    )

    run_mock.assert_not_called()
    assert result == []


@pytest.mark.unit
async def test_heal_resolved_values_heals_supporting_docs_field_with_no_heal_target(monkeypatch):
    """user_input_with_supporting_docs fields flow through heal AFTER
    ExplanationEnhanceAgent so the enhanced paragraph grammatically fits the
    template sentence structure. Since this source has no example_sentence
    or preferred_format marker, heal runs with heal_target=None — relying on
    the template_paragraph alone to drop duplicate subjects / fix tense."""
    from src.core.agents.types.sources import UserInputWithSupportingDocsSourceParams

    captured = {}

    async def fake_run(template_paragraph, placeholder, user_value, heal_target=None, heal_target_kind=None, author_instruction=None):
        captured["template_paragraph"] = template_paragraph
        captured["placeholder"] = placeholder
        captured["user_value"] = user_value
        captured["heal_target"] = heal_target
        captured["heal_target_kind"] = heal_target_kind
        return "was laid off from her position in February 2026"

    monkeypatch.setattr(UserInputHealAgent, "run", fake_run)

    template_bytes = _docx_with_paragraphs([
        "The Debtor, [[debtor_name]], [[letter_body]]."
    ])
    agent_config = AgentConfig(
        template_id="tpl",
        template_fields=[
            _field(
                "letter_body",
                FieldSource.USER_INPUT_WITH_SUPPORTING_DOCS,
                UserInputWithSupportingDocsSourceParams(label="Letter of Explanation"),
            ),
        ],
    )
    resolved = [
        make_resolved_value(
            property_name="letter_body",
            value="The Debtor was laid off from her position in February 2026",
        ),
    ]

    result = await UserInputHealAgent.heal_resolved_values(
        template_bytes=template_bytes,
        agent_config=agent_config,
        resolved_values=resolved,
    )

    # Heal WAS invoked (source is in _USER_INPUT_HEAL_SOURCES).
    assert captured["placeholder"] == "[[letter_body]]"
    assert "[[letter_body]]" in captured["template_paragraph"]
    # No heal_target for this source — template paragraph is the sole context.
    assert captured["heal_target"] is None
    assert captured["heal_target_kind"] is None
    # The healed text replaces the enhancement output in the resolved value.
    assert result[0].value == "was laid off from her position in February 2026"


# ─── multi_select_from_case_vector heal target dispatch ───────────────


@pytest.mark.unit
async def test_heal_resolved_values_multi_select_uses_template_property_marker(monkeypatch):
    """multi_select fields heal against template_property_marker with
    kind='preferred_format' — same pattern as dropdown_from_*."""
    from src.core.agents.types.sources import MultiSelectFromCaseVectorSourceParams

    captured = {}

    async def fake_run(template_paragraph, placeholder, user_value, heal_target=None, heal_target_kind=None, author_instruction=None):
        captured["heal_target"] = heal_target
        captured["heal_target_kind"] = heal_target_kind
        captured["user_value"] = user_value
        return '2018 Mercedes G-Wagon ("Vehicle")'

    monkeypatch.setattr(UserInputHealAgent, "run", fake_run)

    template_bytes = _docx_with_paragraphs([
        "The Debtor scheduled their property [[selected_assets]] within their Chapter 7 schedules."
    ])
    agent_config = AgentConfig(
        template_id="tpl",
        template_fields=[
            _field(
                "selected_assets",
                FieldSource.MULTI_SELECT_FROM_CASE_VECTOR,
                MultiSelectFromCaseVectorSourceParams(
                    label="Select Assets",
                    text_query="Schedule A/B property OR Schedule D vehicle",
                    example_formats=['2018 Mercedes G-Wagon, VIN# X ("Vehicle")'],
                ),
                template_property_marker='2018 Mercedes G-Wagon, VIN# WDCYC3KH3JX288288 ("Vehicle")',
            ),
        ],
    )
    resolved = [make_resolved_value(property_name="selected_assets", value="2018 Mercedes G-Wagon")]

    out = await UserInputHealAgent.heal_resolved_values(
        template_bytes=template_bytes,
        agent_config=agent_config,
        resolved_values=resolved,
    )

    assert captured["heal_target"] == '2018 Mercedes G-Wagon, VIN# WDCYC3KH3JX288288 ("Vehicle")'
    assert captured["heal_target_kind"] == "preferred_format"
    assert captured["user_value"] == "2018 Mercedes G-Wagon"
    assert out[0].value == '2018 Mercedes G-Wagon ("Vehicle")'


@pytest.mark.unit
async def test_heal_resolved_values_multi_select_from_gmail_uses_template_property_marker(monkeypatch):
    """Gmail multi-select goes through the same heal pass with the same
    preferred_format target — no source-type-specific branching needed."""
    from src.core.agents.types.sources import MultiSelectFromGmailSourceParams

    captured = {}

    async def fake_run(template_paragraph, placeholder, user_value, heal_target=None, heal_target_kind=None, author_instruction=None):
        captured["heal_target"] = heal_target
        captured["heal_target_kind"] = heal_target_kind
        captured["user_value"] = user_value
        return "JPMorgan Chase Bank (POC 3)"

    monkeypatch.setattr(UserInputHealAgent, "run", fake_run)

    template_bytes = _docx_with_paragraphs([
        "Since then, the Creditor, [[creditor_names]] materially altered the terms..."
    ])
    agent_config = AgentConfig(
        template_id="tpl",
        template_fields=[
            _field(
                "creditor_names",
                FieldSource.MULTI_SELECT_FROM_GMAIL,
                MultiSelectFromGmailSourceParams(
                    label="Select Creditors",
                    subject_query="Proof of Claim",
                    example_formats=["JPMorgan Chase Bank (POC 3)"],
                ),
                template_property_marker="JPMorgan Chase Bank (POC 3)",
            ),
        ],
    )
    resolved = [make_resolved_value(property_name="creditor_names", value="JPMorgan Chase Bank")]

    out = await UserInputHealAgent.heal_resolved_values(
        template_bytes=template_bytes,
        agent_config=agent_config,
        resolved_values=resolved,
    )

    assert captured["heal_target"] == "JPMorgan Chase Bank (POC 3)"
    assert captured["heal_target_kind"] == "preferred_format"
    assert captured["user_value"] == "JPMorgan Chase Bank"
    assert out[0].value == "JPMorgan Chase Bank (POC 3)"


@pytest.mark.unit
async def test_run_preferred_presentation_block_includes_anti_fact_borrowing_language(mock_agent_invoke):
    """The preferred-format heal block must explicitly tell the LLM not to copy
    sample-case facts (VINs, addresses, etc.) from the marker — those belong
    to a different case. Mitigates hallucination risk for multi_select picks
    that intentionally lack fields the marker has."""
    captured = mock_agent_invoke(_HealedFragment(text="healed"))

    await UserInputHealAgent.run(
        template_paragraph="The Debtor scheduled [[selected_assets]].",
        placeholder="[[selected_assets]]",
        user_value="2018 Mercedes G-Wagon",
        heal_target='2018 Mercedes G-Wagon, VIN# WDCYC3KH3JX288288 ("Vehicle")',
        heal_target_kind="preferred_format",
    )

    prompt = captured["prompt"]
    assert "PREFERRED PRESENTATION" in prompt
    # Anti-fact-borrowing rules.
    assert "different sample case" in prompt or "different case" in prompt
    assert "LEAVE IT MISSING" in prompt or "leave it missing" in prompt.lower()
    assert "VIN" in prompt  # the rule names VINs/addresses/dates as examples


# ─── user_input_plain_text heal target dispatch ───────────────────────


@pytest.mark.unit
async def test_heal_resolved_values_plain_text_always_uses_example_output_sentence(monkeypatch):
    """user_input_plain_text always has example_output_sentence (required) →
    heal_target=that sentence, kind='example_sentence'."""
    from src.core.agents.types.sources import UserInputPlainTextSourceParams

    captured = {}

    async def fake_run(template_paragraph, placeholder, user_value, heal_target=None, heal_target_kind=None, author_instruction=None):
        captured["heal_target"] = heal_target
        captured["heal_target_kind"] = heal_target_kind
        return "healed-prose"

    monkeypatch.setattr(UserInputHealAgent, "run", fake_run)

    template_bytes = _docx_with_paragraphs(["Basis: [[basis_for_objection]]."])
    agent_config = AgentConfig(
        template_id="tpl",
        template_fields=[
            _field(
                "basis_for_objection",
                FieldSource.USER_INPUT_PLAIN_TEXT,
                UserInputPlainTextSourceParams(
                    label="Basis for Objection",
                    example_output_sentence="The claim should be disallowed because the documentation supplied is insufficient.",
                ),
            ),
        ],
    )
    resolved = [make_resolved_value(property_name="basis_for_objection", value="lack of docs")]

    await UserInputHealAgent.heal_resolved_values(
        template_bytes=template_bytes,
        agent_config=agent_config,
        resolved_values=resolved,
    )

    assert captured["heal_target_kind"] == "example_sentence"
    assert captured["heal_target"].startswith("The claim should be disallowed")


# ─── author_instruction (TemplateField.instruction → heal prompt) ─────


@pytest.mark.unit
async def test_run_includes_author_instruction_block_when_present(mock_agent_invoke):
    """When `author_instruction` is set, the AUTHOR INSTRUCTION block + the
    `authoritative` rule appear in the heal prompt."""
    captured = mock_agent_invoke(_HealedFragment(text="healed"))

    await UserInputHealAgent.run(
        template_paragraph="The Debtor [[change_in_circumstances]].",
        placeholder="[[change_in_circumstances]]",
        user_value="had a job loss",
        heal_target="had a temporary loss of income from a workplace injury",
        heal_target_kind="example_sentence",
        author_instruction="PAST TENSE ONLY. Predicate-only — drop any 'The Debtor' subject (already in the docx).",
    )

    prompt = captured["prompt"]
    # Block heading + content rendered.
    assert "AUTHOR INSTRUCTION" in prompt
    assert "PAST TENSE ONLY" in prompt
    assert "Predicate-only" in prompt
    # Rule 4 (authoritative override) is in the base prompt unconditionally.
    assert "authoritative" in prompt.lower() or "AUTHORITATIVE" in prompt


@pytest.mark.unit
@pytest.mark.parametrize("author_instruction", [None, "", "   \n   \t  "])
async def test_run_omits_author_instruction_block_when_blank(mock_agent_invoke, author_instruction):
    """No AUTHOR INSTRUCTION block rendered when instruction is None or whitespace-only."""
    captured = mock_agent_invoke(_HealedFragment(text="healed"))

    await UserInputHealAgent.run(
        template_paragraph="x [[p]] y",
        placeholder="[[p]]",
        user_value="raw",
        heal_target="example",
        heal_target_kind="example_sentence",
        author_instruction=author_instruction,
    )

    prompt = captured["prompt"]
    assert "AUTHOR INSTRUCTION —" not in prompt


@pytest.mark.unit
async def test_run_renders_author_instruction_alongside_heal_target(mock_agent_invoke):
    """When BOTH heal_target and author_instruction are set, both blocks render."""
    captured = mock_agent_invoke(_HealedFragment(text="healed"))

    await UserInputHealAgent.run(
        template_paragraph="The Debtor [[change_in_circumstances]].",
        placeholder="[[change_in_circumstances]]",
        user_value="raw",
        heal_target="had a temporary loss of income",
        heal_target_kind="example_sentence",
        author_instruction="PAST TENSE ONLY",
    )

    prompt = captured["prompt"]
    assert "GUIDE" in prompt
    assert "had a temporary loss of income" in prompt
    assert "AUTHOR INSTRUCTION" in prompt
    assert "PAST TENSE ONLY" in prompt


@pytest.mark.unit
async def test_heal_resolved_values_passes_field_output_instruction_to_run(monkeypatch):
    """The TemplateField.output_instruction (NOT .instruction) is threaded
    into the per-field heal call via `author_instruction=...`. Empty /
    whitespace-only output_instructions are normalized to None.

    Critical separation: `instruction` is the EXTRACTION-time hint for
    DraftAgent / vision agents and must NOT bleed into heal — they have
    different concerns (retrieval guidance vs. output shape).
    """
    captured: dict = {}

    async def fake_run(template_paragraph, placeholder, user_value, heal_target=None, heal_target_kind=None, author_instruction=None):
        captured.setdefault("by_placeholder", {})[placeholder] = author_instruction
        return "healed"

    monkeypatch.setattr(UserInputHealAgent, "run", fake_run)

    template_bytes = _docx_with_paragraphs([
        "The Debtor [[change_in_circumstances]].",
        "These circumstances have since been resolved. The Debtor [[resolution]].",
        "Basis: [[basis_for_objection]].",
        "Lookup: [[other_field]].",
    ])

    agent_config = AgentConfig(
        template_id="tpl",
        template_fields=[
            TemplateField(
                property_name="change_in_circumstances",
                source=FieldSource.RECO_CHIPS_FROM_CASE_VECTOR,
                source_params=make_reco_chips_case_vector_source_params(
                    text_query="Schedule J expenses",
                    example_sentence="had a temporary loss of income",
                ),
                output_instruction="PAST TENSE ONLY. Predicate-only.",
                template_variable_string="[[change_in_circumstances]]",
            ),
            TemplateField(
                property_name="resolution",
                source=FieldSource.RECO_CHIPS_FROM_CASE_VECTOR,
                source_params=make_reco_chips_case_vector_source_params(
                    text_query="current employment",
                    example_sentence="has since secured stable employment",
                ),
                # Whitespace-only output_instruction must normalize to None —
                # heal shouldn't render an empty AUTHOR INSTRUCTION block.
                output_instruction="   \n  ",
                template_variable_string="[[resolution]]",
            ),
            TemplateField(
                property_name="basis_for_objection",
                source=FieldSource.RECO_CHIPS_FROM_CASE_VECTOR,
                source_params=make_reco_chips_case_vector_source_params(
                    text_query="claim documentation",
                    example_sentence="the claim should be disallowed",
                ),
                # No output_instruction at all.
                output_instruction=None,
                template_variable_string="[[basis_for_objection]]",
            ),
            TemplateField(
                property_name="other_field",
                source=FieldSource.RECO_CHIPS_FROM_CASE_VECTOR,
                source_params=make_reco_chips_case_vector_source_params(
                    text_query="other context",
                    example_sentence="example",
                ),
                # Extraction-time `instruction` is set, but `output_instruction`
                # is None — heal must NOT pick up `instruction` (separation
                # of concerns: instruction is for extraction agents, not heal).
                instruction="Extract Document Number from email body",
                output_instruction=None,
                template_variable_string="[[other_field]]",
            ),
        ],
    )
    resolved = [
        make_resolved_value(property_name="change_in_circumstances", value="had a job loss"),
        make_resolved_value(property_name="resolution", value="got a new job"),
        make_resolved_value(property_name="basis_for_objection", value="lack of docs"),
        make_resolved_value(property_name="other_field", value="some value"),
    ]

    await UserInputHealAgent.heal_resolved_values(
        template_bytes=template_bytes,
        agent_config=agent_config,
        resolved_values=resolved,
    )

    assert captured["by_placeholder"]["[[change_in_circumstances]]"] == "PAST TENSE ONLY. Predicate-only."
    assert captured["by_placeholder"]["[[resolution]]"] is None
    assert captured["by_placeholder"]["[[basis_for_objection]]"] is None
    # Critical separation check: extraction-time `instruction` must NOT
    # leak into heal. Only `output_instruction` reaches author_instruction.
    assert captured["by_placeholder"]["[[other_field]]"] is None
