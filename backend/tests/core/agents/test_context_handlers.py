"""Tests for the context-handler behaviors that ride with the cross-case feature.

Focuses on the three handler changes:
  - `_handle_gmail_email` honors `scope_to_current_case=False` by passing
    `case_number=None` to the email service.
  - `_handle_case_vector_auto_query` honors an explicit `text_query` on
    `CaseVectorSourceParams` and falls back to the property-name auto-derive
    when None / empty.
  - `_handle_reco_chips_from_dependent_variables` composes resolved values
    from the context's `resolved_by_name` lookup; returns None when nothing
    resolved.
"""

from unittest.mock import AsyncMock

import pytest

from src.core.agents.context import (
    DraftAgentContext,
    _handle_case_vector_auto_query,
    _handle_gmail_email,
    _handle_reco_chips_from_dependent_variables,
)
from src.core.agents.types.sources import (
    CaseVectorSourceParams,
    FieldSource,
    GmailSourceParams,
    RecoChipsFromDependentVariablesSourceParams,
)
from src.core.common.toolbox import ToolBox
from tests.core.factories import (
    make_agent_config,
    make_template_field,
)


def _make_ctx(case_number: str | None = "26-10700", **resolved):
    return DraftAgentContext(
        agent_config=make_agent_config(),
        case_id="26_10700",
        case_number=case_number,
        case_file_collection="case_file_26",
        gmail_collection="gmail_26",
        courtdrive_collection="courtdrive_26",
        resolved_by_name=resolved,
    )


# ─── _handle_gmail_email ──────────────────────────────────────────────


@pytest.mark.unit
async def test_handle_gmail_passes_case_number_when_scope_to_current_case_true(monkeypatch):
    captured: dict = {}

    async def fake_query_email(**kwargs):
        captured.update(kwargs)
        return None

    monkeypatch.setattr(ToolBox, "query_email", fake_query_email)
    field = make_template_field(
        source=FieldSource.GMAIL,
        source_params=GmailSourceParams(
            subject_query="Order",
            scope_to_current_case=True,
        ),
    )
    await _handle_gmail_email(field, _make_ctx())
    assert captured["case_number"] == "26-10700"


@pytest.mark.unit
async def test_handle_gmail_drops_case_number_when_scope_to_current_case_false(monkeypatch):
    captured: dict = {}

    async def fake_query_email(**kwargs):
        captured.update(kwargs)
        return None

    monkeypatch.setattr(ToolBox, "query_email", fake_query_email)
    field = make_template_field(
        source=FieldSource.GMAIL,
        source_params=GmailSourceParams(
            subject_query="Order",
            scope_to_current_case=False,
        ),
    )
    await _handle_gmail_email(field, _make_ctx())
    assert captured["case_number"] is None


# ─── _handle_case_vector_auto_query ───────────────────────────────────


@pytest.mark.unit
async def test_handle_case_vector_uses_explicit_text_query(monkeypatch):
    captured: dict = {}

    async def fake_query(**kwargs):
        captured.update(kwargs)
        return ["chunk-a"]

    monkeypatch.setattr(ToolBox, "query_case_specific", fake_query)
    field = make_template_field(
        property_name="prior_case_number",
        source=FieldSource.CASE_VECTOR,
        source_params=CaseVectorSourceParams(text_query="prior bankruptcy case 8 years"),
    )
    result = await _handle_case_vector_auto_query(field, _make_ctx())
    assert result == ["chunk-a"]
    assert captured["query"] == "prior bankruptcy case 8 years"


@pytest.mark.unit
async def test_handle_case_vector_falls_back_to_property_name_when_text_query_blank(monkeypatch):
    captured: dict = {}

    async def fake_query(**kwargs):
        captured.update(kwargs)
        return ["chunk-x"]

    monkeypatch.setattr(ToolBox, "query_case_specific", fake_query)
    field = make_template_field(
        property_name="debtor_name",
        source=FieldSource.CASE_VECTOR,
        source_params=CaseVectorSourceParams(text_query=""),
    )
    await _handle_case_vector_auto_query(field, _make_ctx())
    assert captured["query"] == "debtor name"


@pytest.mark.unit
async def test_handle_case_vector_falls_back_when_source_params_is_none(monkeypatch):
    captured: dict = {}

    async def fake_query(**kwargs):
        captured.update(kwargs)
        return ["chunk-y"]

    monkeypatch.setattr(ToolBox, "query_case_specific", fake_query)
    field = make_template_field(
        property_name="case_chapter",
        source=FieldSource.CASE_VECTOR,
        source_params=None,
    )
    await _handle_case_vector_auto_query(field, _make_ctx())
    assert captured["query"] == "case chapter"


# ─── _handle_reco_chips_from_dependent_variables ──────────────────────
#
# As of the timing fix, this handler emits a marker dict only — the
# actual composition from resolved_by_name happens in
# `UserInputResolver.apply` where Pass 2 LLM_DRAFT values are also
# available. The end-to-end composition is exercised in
# tests/core/agents/resolvers/test_user_input_resolver.py.


@pytest.mark.unit
async def test_handle_reco_chips_emits_marker_for_chip_from_deps_field():
    field = make_template_field(
        source=FieldSource.RECO_CHIPS_FROM_DEPENDENT_VARIABLES,
        source_params=RecoChipsFromDependentVariablesSourceParams(
            label="Change in circumstances",
            example_sentence="The Debtor will now be able to afford their plan...",
            dependent_variables=["trustee_reason"],
        ),
    )
    ctx = _make_ctx()
    result = await _handle_reco_chips_from_dependent_variables(field, ctx)
    assert isinstance(result, dict)
    assert result.get("__deferred_chip_compose__") is True


@pytest.mark.unit
async def test_handle_reco_chips_returns_none_for_wrong_source_params_type():
    field = make_template_field(
        source=FieldSource.RECO_CHIPS_FROM_DEPENDENT_VARIABLES,
        source_params=None,
    )
    ctx = _make_ctx()
    result = await _handle_reco_chips_from_dependent_variables(field, ctx)
    assert result is None
