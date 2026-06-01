"""Tests for the child-only bundle_role guardrail on draft entry.

Phase 1B invariant: a template marked `bundle_role = 'child_only'` cannot
be drafted directly via Run Draft (HTTP 400 — production safety) but IS
allowed through dry-run so authors can validate the non-slot variables
(court_drive lookups, system_generated, etc.) before Phase 2 wires up
real bundling. Slot variables (inherit_from_parent) resolve to fallback
placeholders during a child-only dry-run.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from src.core.components.engines.draft import service as draft_service
from src.core.components.engines.template import dry_run as dry_run_module


def _make_child_only_row(template_id: str = "tpl_cos") -> SimpleNamespace:
    """Mimic the columns DraftTemplateRepository.get returns for a child-only row."""
    return SimpleNamespace(
        id=template_id,
        name="Cos no hearing",
        original_doc_url=None,
        template_doc_url=None,
        template_spec=[],
        agent_config={"template_id": template_id, "template_fields": []},
        bundle_role="child_only",
        bundle_companions=None,
    )


@pytest.mark.unit
async def test_execute_draft_for_case_rejects_child_only(monkeypatch):
    monkeypatch.setattr(
        draft_service.DraftTemplateRepository,
        "get",
        AsyncMock(return_value=_make_child_only_row("tpl_cos")),
    )

    with pytest.raises(HTTPException) as excinfo:
        await draft_service.execute_draft_for_case("tpl_cos", "26_10700")

    assert excinfo.value.status_code == 400
    assert "child-only" in excinfo.value.detail.lower()


@pytest.mark.unit
async def test_execute_dry_run_allows_child_only(monkeypatch):
    """Dry-run on a child-only template is allowed — slots resolve to
    fallback placeholders. Authors use this to validate the non-slot
    variables before Phase 2 wires up real bundling."""
    monkeypatch.setattr(
        dry_run_module.DraftTemplateRepository,
        "get",
        AsyncMock(return_value=_make_child_only_row("tpl_cos")),
    )
    # Stub everything downstream so we only assert the guardrail entry path
    # doesn't reject child_only — the actual run is mocked out.
    monkeypatch.setattr(
        dry_run_module,
        "build_agent_config",
        AsyncMock(side_effect=RuntimeError("downstream — stop here")),
    )

    with pytest.raises(RuntimeError, match="downstream"):
        await dry_run_module.execute_dry_run(
            template_id="tpl_cos",
            template_spec=[],
            case_id="26_10700",
        )


@pytest.mark.unit
async def test_resume_dry_run_allows_child_only(monkeypatch):
    """Same as execute_dry_run — resume is also allowed for child-only."""
    monkeypatch.setattr(
        dry_run_module.DraftTemplateRepository,
        "get",
        AsyncMock(return_value=_make_child_only_row("tpl_cos")),
    )
    monkeypatch.setattr(
        dry_run_module,
        "build_agent_config",
        AsyncMock(side_effect=RuntimeError("downstream — stop here")),
    )

    with pytest.raises(RuntimeError, match="downstream"):
        await dry_run_module.resume_dry_run(
            template_id="tpl_cos",
            template_spec=[],
            case_id="26_10700",
            resolved_values=[],
            user_picks={},
        )
