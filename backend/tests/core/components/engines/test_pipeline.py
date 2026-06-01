"""Tests for the small pipeline-internal helpers + Path B wave-B integration.

The full `run_initial_stages` / `run_resume_stages` orchestration is
exercised end-to-end via the dry-run and draft router tests; here we
cover the in-module dedup helper plus a focused wave-B test that
proves `run_resume_stages` correctly threads late-auto-derived values
into Pass 3 case_vector substitutions.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.agents.orchestration.pipeline import _dedupe_last_wins
from tests.core.factories import make_resolved_value


@pytest.mark.unit
def test_dedupe_last_wins_collapses_duplicates_keeping_last_value():
    pass_1_low = make_resolved_value(
        property_name="prior_case_dismissal_date",
        value="",
        confidence="low",
    )
    pass_2_high = make_resolved_value(
        property_name="prior_case_dismissal_date",
        value="November 17, 2025",
        confidence="high",
    )
    other = make_resolved_value(property_name="case_number", value="26-10700")

    deduped = _dedupe_last_wins([pass_1_low, other, pass_2_high])

    assert len(deduped) == 2
    by_name = {rv.property_name: rv for rv in deduped}
    assert by_name["prior_case_dismissal_date"].value == "November 17, 2025"
    assert by_name["prior_case_dismissal_date"].confidence == "high"
    assert by_name["case_number"].value == "26-10700"


@pytest.mark.unit
def test_dedupe_last_wins_preserves_original_position_when_overwriting():
    a1 = make_resolved_value(property_name="a", value="old")
    b = make_resolved_value(property_name="b", value="b_val")
    a2 = make_resolved_value(property_name="a", value="new")

    deduped = _dedupe_last_wins([a1, b, a2])

    assert [rv.property_name for rv in deduped] == ["a", "b"]
    assert deduped[0].value == "new"


@pytest.mark.unit
def test_dedupe_last_wins_no_op_when_already_unique():
    values = [
        make_resolved_value(property_name="a"),
        make_resolved_value(property_name="b"),
    ]
    assert _dedupe_last_wins(values) == values


@pytest.mark.unit
def test_dedupe_last_wins_empty_input_returns_empty():
    assert _dedupe_last_wins([]) == []


# ─── Path B — wave-B Pass 3 in run_resume_stages ──────────────────────


from src.core.agents.context import DraftContextService
from src.core.agents.context.types import DraftAgentContext, FetchedContext
from src.core.agents.llm.auto_derive import AutoDeriveAgent
from src.core.agents.llm.draft import DraftAgent, DraftAgentOutput
from src.core.agents.orchestration.pipeline import run_resume_stages
from src.core.agents.resolvers.user_input_resolver import UserSelection
from src.core.agents.types.sources import (
    AutoDerivedSourceParams,
    CaseVectorSourceParams,
    DropdownEmailSourceParams,
    FieldSource,
)
from src.core.agents.types.spec import AgentConfig, TemplateField


@pytest.mark.unit
async def test_run_resume_stages_pass_3_substitutes_user_input_rooted_auto_derived(monkeypatch):
    """End-to-end: vehicle_record (dropdown_from_gmail) → car_model (auto_derived)
    → creditor_name (case_vector, text_query="lien for {{car_model}}").

    After expand_picks resolves vehicle_record, late auto-derive must
    populate car_model, then Pass 3 must call fetch_with_substitution
    with the substituted query containing the literal car_model value.
    """
    vehicle_record = TemplateField(
        property_name="vehicle_record",
        source=FieldSource.DROPDOWN_FROM_GMAIL,
        source_params=DropdownEmailSourceParams(
            label="Pick the vehicle row",
            example_format="...",
            subject_query="vehicle",
        ),
        template_variable_string=None,
    )
    car_model = TemplateField(
        property_name="car_model",
        source=FieldSource.AUTO_DERIVED_FROM_VARIABLE,
        source_params=AutoDerivedSourceParams(dependent_variable="vehicle_record"),
        template_property_marker="2023 Kia Sportage",
        template_variable_string="[[car_model]]",
    )
    creditor_name = TemplateField(
        property_name="creditor_name",
        source=FieldSource.CASE_VECTOR,
        source_params=CaseVectorSourceParams(text_query="lien for {{car_model}}"),
        template_variable_string="[[creditor_name]]",
    )
    agent_config = AgentConfig(
        template_id="tpl_test",
        template_fields=[vehicle_record, car_model, creditor_name],
    )

    # Stub CaseRepository.get so the pipeline's resource_key auto-resolve
    # doesn't hit a real DB. Returning None makes run_resume_stages
    # fall through with resource_key=None — fine for tests that don't
    # exercise the supporting-doc R2 path.
    monkeypatch.setattr(
        "src.core.agents.orchestration.pipeline.CaseRepository.get",
        AsyncMock(return_value=None),
    )

    # Stub: user picked a vehicle row → expand_picks emits the parent's value
    async def fake_expand_picks(
        template_fields, resolved_values, user_picks, case_id, resource_key=None,
    ):
        return [
            make_resolved_value(
                property_name="vehicle_record",
                value="2023 Kia Sportage - VIN - 39235",
            ),
        ]
    monkeypatch.setattr(
        "src.core.agents.orchestration.pipeline.UserInputResolver.expand_picks",
        fake_expand_picks,
    )

    # Late auto-derive: AutoDeriveAgent extracts "2023 Kia Sportage" from parent row text
    monkeypatch.setattr(
        AutoDeriveAgent,
        "run",
        AsyncMock(return_value="2023 Kia Sportage"),
    )

    # Pass 3 fetch returns a fake context — assertion happens via call capture
    captured_fetch_context: dict[str, DraftAgentContext] = {}

    async def fake_fetch_with_substitution(draft_ctx):
        captured_fetch_context["ctx"] = draft_ctx
        return [
            FetchedContext(
                property_name="creditor_name",
                source=FieldSource.CASE_VECTOR,
                raw_result="GENESIS FINANCE",
                instruction=None,
            ),
        ]
    monkeypatch.setattr(
        DraftContextService,
        "fetch_with_substitution",
        fake_fetch_with_substitution,
    )

    # DraftContextService.build returns a minimal context; the real one needs DB access
    fake_draft_context = DraftAgentContext(
        agent_config=agent_config,
        case_id="26_14234",
        case_number="26-14234-MAM",
        case_details={"debtor_name": "Test", "case_number": "26-14234-MAM"},
        petition_pdf_url=None,
        resolved_by_name={},
    )
    monkeypatch.setattr(
        DraftContextService,
        "build",
        AsyncMock(return_value=fake_draft_context),
    )

    # Pass 3 DraftAgent run: extracts creditor name from the fake fetched context
    monkeypatch.setattr(
        DraftAgent,
        "run",
        AsyncMock(return_value=DraftAgentOutput(
            resolved_values=[
                make_resolved_value(property_name="creditor_name", value="GENESIS FINANCE"),
            ],
        )),
    )

    # Run the resume stage
    user_picks = {"vehicle_record": MagicMock(spec=UserSelection)}
    result = await run_resume_stages(
        agent_config=agent_config,
        case_id="26_14234",
        resolved_values=[],  # nothing resolved before the pause for this minimal test
        user_picks=user_picks,
    )

    # 1. The captured Pass 3 context must include resolved car_model in resolved_by_name.
    assert "ctx" in captured_fetch_context, "fetch_with_substitution was never called"
    ctx = captured_fetch_context["ctx"]
    assert "car_model" in ctx.resolved_by_name, \
        f"car_model missing from Pass 3 resolved_by_name: {list(ctx.resolved_by_name.keys())}"
    assert ctx.resolved_by_name["car_model"].value == "2023 Kia Sportage"
    assert "vehicle_record" in ctx.resolved_by_name, "vehicle_record missing"

    # 2. The scoped agent_config passed to Pass 3 must contain ONLY the wave-B field (creditor_name).
    wave_b_property_names = {f.property_name for f in ctx.agent_config.template_fields}
    assert wave_b_property_names == {"creditor_name"}, \
        f"Pass 3 scope should contain only creditor_name, got: {wave_b_property_names}"

    # 3. The final resolved_values list must contain creditor_name (from Pass 3 DraftAgent).
    by_name = {rv.property_name: rv for rv in result}
    assert "creditor_name" in by_name
    assert by_name["creditor_name"].value == "GENESIS FINANCE"
    # And car_model must be there (resolved by late auto-derive).
    assert by_name["car_model"].value == "2023 Kia Sportage"


@pytest.mark.unit
async def test_run_resume_stages_skips_pass_3_when_no_wave_b_fields(monkeypatch):
    """When no LLM_DRAFT field references a USER_INPUT-rooted target,
    Pass 3 is skipped entirely (no DraftContextService.build, no extra
    DraftAgent call) — preserves the pre-Path B behavior."""
    parent = TemplateField(
        property_name="vehicle_record",
        source=FieldSource.DROPDOWN_FROM_GMAIL,
        source_params=DropdownEmailSourceParams(
            label="x", example_format="x", subject_query="vehicle",
        ),
        template_variable_string=None,
    )
    child = TemplateField(
        property_name="car_model",
        source=FieldSource.AUTO_DERIVED_FROM_VARIABLE,
        source_params=AutoDerivedSourceParams(dependent_variable="vehicle_record"),
        template_property_marker="x",
    )
    agent_config = AgentConfig(
        template_id="tpl_test",
        template_fields=[parent, child],
    )

    # Same DB stub as the other run_resume_stages test.
    monkeypatch.setattr(
        "src.core.agents.orchestration.pipeline.CaseRepository.get",
        AsyncMock(return_value=None),
    )

    async def fake_expand_picks(
        template_fields, resolved_values, user_picks, case_id, resource_key=None,
    ):
        return [make_resolved_value(property_name="vehicle_record", value="row text")]
    monkeypatch.setattr(
        "src.core.agents.orchestration.pipeline.UserInputResolver.expand_picks",
        fake_expand_picks,
    )

    monkeypatch.setattr(AutoDeriveAgent, "run", AsyncMock(return_value="2023 Kia"))
    build_mock = AsyncMock()
    monkeypatch.setattr(DraftContextService, "build", build_mock)
    fetch_mock = AsyncMock(return_value=[])
    monkeypatch.setattr(DraftContextService, "fetch_with_substitution", fetch_mock)
    draft_mock = AsyncMock()
    monkeypatch.setattr(DraftAgent, "run", draft_mock)

    user_picks = {"vehicle_record": MagicMock(spec=UserSelection)}
    await run_resume_stages(
        agent_config=agent_config,
        case_id="26_14234",
        resolved_values=[],
        user_picks=user_picks,
    )

    assert build_mock.await_count == 0
    assert fetch_mock.await_count == 0
    assert draft_mock.await_count == 0
