"""`cost_attribution` contextvar manager + `build_cost_context_for_agent`."""

from __future__ import annotations

import pytest

from src.core.common.cost_tracking import (
    build_cost_context_for_agent,
    cost_attribution,
    get_current_attribution,
)


@pytest.mark.unit
class TestCostAttribution:
    def test_default_is_empty(self):
        attr = get_current_attribution()
        assert attr.firm_id is None
        assert attr.case_id is None
        assert attr.user_id is None
        assert attr.session_id is None

    def test_scope_sets_then_unsets(self):
        # Outside scope: empty.
        assert get_current_attribution().firm_id is None

        with cost_attribution(
            firm_id="firm-1", case_id="case-x", user_id="u1",
        ):
            attr = get_current_attribution()
            assert attr.firm_id == "firm-1"
            assert attr.case_id == "case-x"
            assert attr.user_id == "u1"

        # After scope exits: empty again.
        assert get_current_attribution().firm_id is None

    def test_nested_scope_overrides(self):
        with cost_attribution(firm_id="firm-1", case_id="case-A"):
            with cost_attribution(case_id="case-B"):
                attr = get_current_attribution()
                # Inner case_id wins; outer firm_id inherited.
                assert attr.firm_id == "firm-1"
                assert attr.case_id == "case-B"
            # Inner pops, outer restored.
            assert get_current_attribution().case_id == "case-A"


@pytest.mark.unit
class TestBuildCostContextForAgent:
    def test_combines_scope_and_kind(self):
        with cost_attribution(firm_id="firm-1", case_id="c1", user_id="u1"):
            ctx = build_cost_context_for_agent(
                kind="draft", agent_name="DraftAgent",
            )
            assert ctx.kind == "draft"
            assert ctx.firm_id == "firm-1"
            assert ctx.case_id == "c1"
            assert ctx.user_id == "u1"
            assert ctx.agent_name == "DraftAgent"

    def test_works_without_scope(self):
        ctx = build_cost_context_for_agent(kind="chat")
        assert ctx.kind == "chat"
        assert ctx.firm_id is None

    def test_to_metadata_omits_falsy(self):
        with cost_attribution(firm_id="firm-1", case_id="c1"):
            ctx = build_cost_context_for_agent(kind="draft")
            md = ctx.to_metadata()
            assert md == {"case_id": "c1"}  # firm_id is on top-level, agent_name not set
