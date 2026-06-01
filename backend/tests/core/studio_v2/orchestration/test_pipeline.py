"""Tests for run_initial_stages_v2 + run_resume_stages_v2.

WizardResolver.dispatch is patched per-test so we exercise the
orchestration logic (wave ordering, pause/resume split, derive
ordering) without making real LLM calls.
"""

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from src.core.studio_v2.orchestration.pipeline import (
    run_initial_stages_v2,
    run_resume_stages_v2,
)
from src.core.studio_v2.types.fields import TemplateFieldV2, TemplateSpecV2
from src.core.studio_v2.types.pending import PendingDropdownV2
from src.core.studio_v2.types.picks import SingleValuePickV2
from src.core.studio_v2.types.resolution import ResolvedTemplateValueV2
from src.core.studio_v2.types.wizard_sources import (
    AuthorInputKind,
    PresentationShape,
    SourceKind,
    WizardSourceParams,
)


_TEMPLATE_UUID = "00000000-0000-0000-0000-000000000099"
_FIELD_UUID = "00000000-0000-0000-0000-000000000001"


def _field(name, params, index=0):
    return TemplateFieldV2(
        id=_FIELD_UUID, template_id=_TEMPLATE_UUID,
        template_variable=name, template_index=index, params=params,
    )


def _spec(fields):
    return TemplateSpecV2(template_id=_TEMPLATE_UUID, fields=fields)


class _FakeCase:
    id = "case-1"
    case_number = "26-12345"
    case_name = "Doe"
    case_file_collection = None
    petition_pdf_url = None
    legacy_id = None


def _stub_dispatch(per_field_results):
    """Build a side_effect for WizardResolver.dispatch that returns
    a pre-built result per field.template_variable. Unknown fields
    default to an empty resolved row."""
    async def fake(*, field, **_):
        return per_field_results.get(
            field.template_variable,
            ResolvedTemplateValueV2(
                template_variable=field.template_variable, value="(default)",
            ),
        )
    return fake


# ─── run_initial_stages_v2 ───────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
async def test_initial_stages_returns_all_resolved_when_no_pending():
    spec = _spec([
        _field("doc_date", WizardSourceParams(source=SourceKind.CURRENT_DATE)),
        _field("attorney", WizardSourceParams(
            source=SourceKind.ATTORNEY,
            presentation_shape=PresentationShape.RAW,
            attorney_id="att-1",
        )),
    ])
    per_field = {
        "doc_date": ResolvedTemplateValueV2(template_variable="doc_date", value="2026-04-30"),
        "attorney": ResolvedTemplateValueV2(template_variable="attorney", value="Chad"),
    }
    with patch(
        "src.core.studio_v2.orchestration.pipeline.WizardResolver.dispatch",
        new=AsyncMock(side_effect=_stub_dispatch(per_field)),
    ):
        result = await run_initial_stages_v2(
            spec=spec, case=_FakeCase(), toolset=[],
        )
    assert result.pending_inputs is None
    assert {rv.template_variable for rv in result.all_resolved} == {"doc_date", "attorney"}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_initial_stages_returns_pending_when_user_input():
    spec = _spec([
        _field("creditor", WizardSourceParams(
            source=SourceKind.GMAIL,
            presentation_shape=PresentationShape.DROPDOWN,
            extraction_prompt="all creditors",
        )),
    ])
    pending = PendingDropdownV2(
        label="Pick creditor",
        options=["Acme", "Wells"],
        raw_contexts=["chunk a", "chunk b"],
    )
    with patch(
        "src.core.studio_v2.orchestration.pipeline.WizardResolver.dispatch",
        new=AsyncMock(return_value=pending),
    ):
        result = await run_initial_stages_v2(
            spec=spec, case=_FakeCase(), toolset=[],
        )
    assert result.pending_inputs is not None
    assert "creditor" in result.pending_inputs
    assert result.pending_inputs["creditor"].kind == "dropdown"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_initial_stages_early_derive_when_parent_resolved():
    """A derived child of a CURRENT_DATE parent must resolve in the
    initial pass (early auto-derive)."""
    parent = _field("doc_date", WizardSourceParams(source=SourceKind.CURRENT_DATE))
    child = _field(
        "year",
        WizardSourceParams(
            source=SourceKind.DERIVED_FROM_VARIABLE,
            dependent_variable="doc_date",
            extraction_prompt="extract the year",
        ),
        index=1,
    )
    spec = _spec([parent, child])
    per_field = {
        "doc_date": ResolvedTemplateValueV2(
            template_variable="doc_date", value="April 30, 2026",
            raw_context="2026-04-30 ISO source",
        ),
        "year": ResolvedTemplateValueV2(template_variable="year", value="2026"),
    }
    with patch(
        "src.core.studio_v2.orchestration.pipeline.WizardResolver.dispatch",
        new=AsyncMock(side_effect=_stub_dispatch(per_field)),
    ):
        result = await run_initial_stages_v2(
            spec=spec, case=_FakeCase(), toolset=[],
        )
    by_name = {rv.template_variable: rv for rv in result.all_resolved}
    assert by_name["year"].value == "2026"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_initial_stages_defers_user_input_rooted_derives():
    """A derive whose root parent is USER_INPUT must NOT resolve in
    the initial pass — it waits for resume."""
    user_field = _field("creditor", WizardSourceParams(
        source=SourceKind.GMAIL,
        presentation_shape=PresentationShape.DROPDOWN,
    ))
    derive_field = _field(
        "amount",
        WizardSourceParams(
            source=SourceKind.DERIVED_FROM_VARIABLE,
            dependent_variable="creditor",
            extraction_prompt="extract amount",
        ),
        index=1,
    )
    spec = _spec([user_field, derive_field])

    # WizardResolver.dispatch is patched — for the user_field it'd
    # return PendingDropdownV2; for amount it'd return a value if
    # called. We confirm it's NOT called for `amount` in the initial pass.
    pending = PendingDropdownV2(label="x", options=["A"], raw_contexts=["chunk"])

    dispatch_calls: list[str] = []
    async def fake(*, field, **_):
        dispatch_calls.append(field.template_variable)
        if field.template_variable == "creditor":
            return pending
        return ResolvedTemplateValueV2(template_variable=field.template_variable, value="x")

    with patch(
        "src.core.studio_v2.orchestration.pipeline.WizardResolver.dispatch",
        new=AsyncMock(side_effect=fake),
    ):
        result = await run_initial_stages_v2(
            spec=spec, case=_FakeCase(), toolset=[],
        )
    # `amount` (USER_INPUT-rooted derive) should NOT have been dispatched.
    assert "amount" not in dispatch_calls
    # `creditor` SHOULD have been — and it paused.
    assert "creditor" in dispatch_calls
    assert result.pending_inputs is not None
    assert "creditor" in result.pending_inputs


# ─── run_resume_stages_v2 ────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
async def test_resume_stages_expand_picks_then_late_derive():
    """User picks the creditor → expand_picks emits a resolved row;
    then the USER_INPUT-rooted derive runs in step 2."""
    user_field = _field("creditor", WizardSourceParams(
        source=SourceKind.GMAIL,
        presentation_shape=PresentationShape.DROPDOWN,
    ))
    derive_field = _field(
        "amount",
        WizardSourceParams(
            source=SourceKind.DERIVED_FROM_VARIABLE,
            dependent_variable="creditor",
            extraction_prompt="extract amount",
        ),
        index=1,
    )
    spec = _spec([user_field, derive_field])
    pending_inputs = {
        "creditor": PendingDropdownV2(
            label="x", options=["Acme Bank"], raw_contexts=["chunk for acme"],
        ),
    }
    user_picks = {"creditor": SingleValuePickV2(value="Acme Bank")}

    async def fake_dispatch(*, field, by_name=None, **_):
        # The derive should be called with by_name containing creditor=Acme Bank.
        if field.template_variable == "amount":
            parent = by_name["creditor"]
            assert parent.value == "Acme Bank"
            assert parent.raw_context == "chunk for acme"
            return ResolvedTemplateValueV2(template_variable="amount", value="$1,200")
        return ResolvedTemplateValueV2(template_variable=field.template_variable, value="x")

    with patch(
        "src.core.studio_v2.orchestration.pipeline.WizardResolver.dispatch",
        new=AsyncMock(side_effect=fake_dispatch),
    ):
        out = await run_resume_stages_v2(
            spec=spec, case=_FakeCase(),
            resolved_values=[],  # nothing was pre-resolved
            user_picks=user_picks,
            pending_inputs=pending_inputs,
            toolset=[],
        )

    by_name = {rv.template_variable: rv for rv in out}
    assert by_name["creditor"].value == "Acme Bank"
    assert by_name["creditor"].raw_context == "chunk for acme"
    assert by_name["amount"].value == "$1,200"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_resume_stages_idempotent_on_chain_of_derives():
    """A chain (root → derive1 → derive2) all derives in step 4's
    fixed-point loop after resume."""
    root = _field(
        "creditor",
        WizardSourceParams(
            source=SourceKind.GMAIL,
            presentation_shape=PresentationShape.DROPDOWN,
        ),
    )
    derive1 = _field(
        "amount",
        WizardSourceParams(
            source=SourceKind.DERIVED_FROM_VARIABLE,
            dependent_variable="creditor",
            extraction_prompt="extract amount",
        ),
        index=1,
    )
    derive2 = _field(
        "amount_fmt",
        WizardSourceParams(
            source=SourceKind.DERIVED_FROM_VARIABLE,
            dependent_variable="amount",
            extraction_prompt="format with $",
        ),
        index=2,
    )
    spec = _spec([root, derive1, derive2])
    user_picks = {"creditor": SingleValuePickV2(value="Acme")}
    pending_inputs = {"creditor": PendingDropdownV2(label="x", options=["Acme"], raw_contexts=[""])}

    async def fake_dispatch(*, field, **_):
        if field.template_variable == "amount":
            return ResolvedTemplateValueV2(template_variable="amount", value="1200")
        if field.template_variable == "amount_fmt":
            return ResolvedTemplateValueV2(template_variable="amount_fmt", value="$1,200")
        return ResolvedTemplateValueV2(template_variable=field.template_variable, value="x")

    with patch(
        "src.core.studio_v2.orchestration.pipeline.WizardResolver.dispatch",
        new=AsyncMock(side_effect=fake_dispatch),
    ):
        out = await run_resume_stages_v2(
            spec=spec, case=_FakeCase(),
            resolved_values=[], user_picks=user_picks,
            pending_inputs=pending_inputs, toolset=[],
        )

    by_name = {rv.template_variable: rv for rv in out}
    assert by_name["amount"].value == "1200"
    assert by_name["amount_fmt"].value == "$1,200"
