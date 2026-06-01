"""Tests for the 4 deterministic resolvers (current_date, constants,
attorney, inherit_from_parent). Real DB calls mocked via patch."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from src.core.studio_v2.resolvers.attorney import resolve_attorney_static
from src.core.studio_v2.resolvers.constants import resolve_constant
from src.core.studio_v2.resolvers.current_date import resolve_current_date
from src.core.studio_v2.resolvers.inherit_from_parent import (
    resolve_inherit_from_parent,
)
from src.core.studio_v2.types.bundling import (
    ExtractFromDraftSlotConfig,
    LiteralSlotConfig,
    ParentVariableSlotConfig,
)
from src.core.studio_v2.types.orchestration import ParentBundleContextV2
from src.core.studio_v2.types.wizard_sources import (
    PresentationShape,
    SourceKind,
    WizardSourceParams,
)


# ─── current_date ─────────────────────────────────────────────────────


@pytest.mark.unit
def test_current_date_returns_iso():
    params = WizardSourceParams(source=SourceKind.CURRENT_DATE)
    fixed = datetime(2026, 5, 24, 10, 30, tzinfo=timezone.utc)
    rv = resolve_current_date(template_variable="document_date", params=params, now=fixed)
    assert rv.value == "2026-05-24"
    assert rv.confidence == "high"
    assert "finalizer" in rv.note.lower()


# ─── constants ────────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
async def test_constants_lookup_success():
    params = WizardSourceParams(
        source=SourceKind.CONSTANTS,
        constants_short_code="FIRM_ADDRESS",
    )
    fake_row = type("Row", (), {"value": "330 Clematis St, Suite 222"})()
    with patch(
        "src.core.studio_v2.resolvers.constants.ReferenceDataRepository.get",
        new=AsyncMock(return_value=fake_row),
    ):
        rv = await resolve_constant(template_variable="firm_address", params=params)
    assert rv.value == "330 Clematis St, Suite 222"
    assert rv.confidence == "high"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_constants_missing_short_code():
    params = WizardSourceParams(
        source=SourceKind.CONSTANTS, constants_short_code=None,
    )
    rv = await resolve_constant(template_variable="firm_address", params=params)
    assert rv.value == ""
    assert rv.confidence == "none"
    assert "no constants_short_code" in rv.note


@pytest.mark.unit
@pytest.mark.asyncio
async def test_constants_row_not_found():
    params = WizardSourceParams(
        source=SourceKind.CONSTANTS, constants_short_code="MISSING_CODE",
    )
    with patch(
        "src.core.studio_v2.resolvers.constants.ReferenceDataRepository.get",
        new=AsyncMock(return_value=None),
    ):
        rv = await resolve_constant(template_variable="x", params=params)
    assert rv.value == ""
    assert "not found" in rv.note


# ─── attorney (raw mode) ─────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
async def test_attorney_pinned_lookup_success():
    params = WizardSourceParams(
        source=SourceKind.ATTORNEY,
        presentation_shape=PresentationShape.RAW,
        attorney_id="att-uuid-1",
    )
    fake_attorney = type("A", (), {"id": "att-uuid-1", "full_name": "Chad Van Horn, Esq."})()
    with patch(
        "src.core.studio_v2.resolvers.attorney.AttorneyRosterRepository.get",
        new=AsyncMock(return_value=fake_attorney),
    ):
        rv = await resolve_attorney_static(template_variable="attorney_name", params=params)
    assert rv.value == "Chad Van Horn, Esq."
    assert rv.confidence == "high"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_attorney_missing_id():
    params = WizardSourceParams(
        source=SourceKind.ATTORNEY,
        presentation_shape=PresentationShape.RAW,
        attorney_id=None,
    )
    rv = await resolve_attorney_static(template_variable="attorney_name", params=params)
    assert rv.value == ""
    assert "no attorney_id" in rv.note


@pytest.mark.unit
@pytest.mark.asyncio
async def test_attorney_id_not_in_roster():
    params = WizardSourceParams(
        source=SourceKind.ATTORNEY,
        presentation_shape=PresentationShape.RAW,
        attorney_id="att-deleted",
    )
    with patch(
        "src.core.studio_v2.resolvers.attorney.AttorneyRosterRepository.get",
        new=AsyncMock(return_value=None),
    ):
        rv = await resolve_attorney_static(template_variable="x", params=params)
    assert rv.value == ""
    assert "not in ATTORNEYS roster" in rv.note


@pytest.mark.unit
@pytest.mark.asyncio
async def test_attorney_roster_lookup_db_error_degrades():
    """DB exception during roster lookup → low-confidence empty
    row with error in note, no crash."""
    params = WizardSourceParams(
        source=SourceKind.ATTORNEY,
        presentation_shape=PresentationShape.RAW,
        attorney_id="att-1",
    )
    with patch(
        "src.core.studio_v2.resolvers.attorney.AttorneyRosterRepository.get",
        new=AsyncMock(side_effect=RuntimeError("db down")),
    ):
        rv = await resolve_attorney_static(template_variable="x", params=params)
    assert rv.value == ""
    assert rv.confidence == "none"
    assert "roster lookup failed" in rv.note


@pytest.mark.unit
@pytest.mark.asyncio
async def test_constants_lookup_db_error_degrades():
    """DB exception during reference_data lookup → low-confidence
    empty row with error in note, no crash."""
    from src.core.studio_v2.resolvers.constants import resolve_constant

    params = WizardSourceParams(
        source=SourceKind.CONSTANTS,
        constants_short_code="FIRM_ADDRESS",
    )
    with patch(
        "src.core.studio_v2.resolvers.constants.ReferenceDataRepository.get",
        new=AsyncMock(side_effect=RuntimeError("db down")),
    ):
        rv = await resolve_constant(template_variable="x", params=params)
    assert rv.value == ""
    assert rv.confidence == "none"
    assert "lookup failed" in rv.note


# ─── inherit_from_parent (value_from_parent_bundle) ──────────────────


@pytest.mark.unit
@pytest.mark.asyncio
async def test_inherit_parent_variable_slot():
    params = WizardSourceParams(source=SourceKind.VALUE_FROM_PARENT_BUNDLE)
    parent_ctx = ParentBundleContextV2(
        resolved_values={"debtor_name": "Jane Doe"},
        slot_configurations={
            "debtor_name": ParentVariableSlotConfig(parent_variable="debtor_name"),
        },
    )
    rv = await resolve_inherit_from_parent(
        template_variable="debtor_name",
        params=params,
        parent_context=parent_ctx,
    )
    assert rv.value == "Jane Doe"
    assert rv.confidence == "high"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_inherit_literal_slot():
    params = WizardSourceParams(source=SourceKind.VALUE_FROM_PARENT_BUNDLE)
    parent_ctx = ParentBundleContextV2(
        slot_configurations={
            "service_kind": LiteralSlotConfig(literal_value="CM/ECF"),
        },
    )
    rv = await resolve_inherit_from_parent(
        template_variable="service_kind",
        params=params,
        parent_context=parent_ctx,
    )
    assert rv.value == "CM/ECF"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_inherit_extract_from_draft_calls_extract_agent():
    """Slice D wires the real ExtractFromDraftAgentV2 into the
    extract_from_draft slot path."""
    from unittest.mock import AsyncMock as _AsyncMock, patch as _patch

    params = WizardSourceParams(source=SourceKind.VALUE_FROM_PARENT_BUNDLE)
    parent_ctx = ParentBundleContextV2(
        draft_text="UNITED STATES BANKRUPTCY COURT\nIn re: Jane Doe, Debtor.",
        slot_configurations={
            "debtor_caption": ExtractFromDraftSlotConfig(
                extract_instruction="Pull the In re caption verbatim.",
            ),
        },
    )
    with _patch(
        "src.core.studio_v2.agents.extract_from_draft.ExtractFromDraftAgentV2.run",
        new=_AsyncMock(return_value="Jane Doe, Debtor."),
    ) as agent_mock:
        rv = await resolve_inherit_from_parent(
            template_variable="debtor_caption",
            params=params,
            parent_context=parent_ctx,
        )
    agent_mock.assert_awaited_once()
    assert rv.value == "Jane Doe, Debtor."
    assert rv.confidence == "high"
    assert "extract_from_draft" in rv.note


@pytest.mark.unit
@pytest.mark.asyncio
async def test_inherit_extract_from_draft_empty_draft_text_uses_fallback():
    from unittest.mock import AsyncMock as _AsyncMock, patch as _patch

    params = WizardSourceParams(
        source=SourceKind.VALUE_FROM_PARENT_BUNDLE,
        parent_bundle_fallback="(fallback)",
    )
    parent_ctx = ParentBundleContextV2(
        draft_text="",
        slot_configurations={
            "x": ExtractFromDraftSlotConfig(extract_instruction="extract X"),
        },
    )
    with _patch(
        "src.core.studio_v2.agents.extract_from_draft.ExtractFromDraftAgentV2.run",
        new=_AsyncMock(),
    ) as agent_mock:
        rv = await resolve_inherit_from_parent(
            template_variable="x", params=params, parent_context=parent_ctx,
        )
    agent_mock.assert_not_called()
    assert rv.value == "(fallback)"
    assert "parent_context.draft_text is empty" in rv.note


@pytest.mark.unit
@pytest.mark.asyncio
async def test_inherit_extract_from_draft_agent_empty_uses_fallback():
    """When the LLM returns empty (couldn't extract), fall through to
    parent_bundle_fallback."""
    from unittest.mock import AsyncMock as _AsyncMock, patch as _patch

    params = WizardSourceParams(
        source=SourceKind.VALUE_FROM_PARENT_BUNDLE,
        parent_bundle_fallback="(fallback)",
    )
    parent_ctx = ParentBundleContextV2(
        draft_text="some draft",
        slot_configurations={
            "x": ExtractFromDraftSlotConfig(extract_instruction="extract X"),
        },
    )
    with _patch(
        "src.core.studio_v2.agents.extract_from_draft.ExtractFromDraftAgentV2.run",
        new=_AsyncMock(return_value=""),
    ):
        rv = await resolve_inherit_from_parent(
            template_variable="x", params=params, parent_context=parent_ctx,
        )
    assert rv.value == "(fallback)"
    assert "agent returned empty" in rv.note


@pytest.mark.unit
@pytest.mark.asyncio
async def test_inherit_missing_slot_config_uses_fallback():
    params = WizardSourceParams(
        source=SourceKind.VALUE_FROM_PARENT_BUNDLE,
        parent_bundle_fallback="(unfilled)",
    )
    parent_ctx = ParentBundleContextV2()
    rv = await resolve_inherit_from_parent(
        template_variable="x", params=params, parent_context=parent_ctx,
    )
    assert rv.value == "(unfilled)"
    assert rv.confidence == "low"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_inherit_missing_parent_context_uses_fallback():
    params = WizardSourceParams(
        source=SourceKind.VALUE_FROM_PARENT_BUNDLE,
        parent_bundle_fallback="(no parent)",
    )
    rv = await resolve_inherit_from_parent(
        template_variable="x", params=params, parent_context=None,
    )
    assert rv.value == "(no parent)"
