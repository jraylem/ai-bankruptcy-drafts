"""Tests for StudioV2ToolContext — frozen dataclass + field access."""

from dataclasses import FrozenInstanceError

import pytest

from src.core.studio_v2.tools import StudioV2ToolContext


@pytest.mark.unit
def test_context_holds_case_and_oauth():
    fake_case = object()
    fake_oauth = object()
    ctx = StudioV2ToolContext(case=fake_case, firm_oauth=fake_oauth)
    assert ctx.case is fake_case
    assert ctx.firm_oauth is fake_oauth


@pytest.mark.unit
def test_context_firm_oauth_optional():
    ctx = StudioV2ToolContext(case=object())
    assert ctx.firm_oauth is None


@pytest.mark.unit
def test_context_is_frozen():
    ctx = StudioV2ToolContext(case=object())
    with pytest.raises(FrozenInstanceError):
        ctx.case = "different"  # type: ignore[misc]
