"""Tests for the user-input envelope emitters
(emit_attorney_pick_envelope + emit_author_input_envelope).

ATTORNEYS roster loading is patched."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.core.studio_v2.resolvers.user_input import (
    emit_attorney_pick_envelope,
    emit_author_input_envelope,
)
from src.core.studio_v2.types.wizard_sources import (
    AuthorInputKind,
    PresentationShape,
    SourceKind,
    WizardSourceParams,
)


# ─── emit_attorney_pick_envelope ─────────────────────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
async def test_attorney_pick_dropdown_loads_roster():
    fake_roster = [
        SimpleNamespace(id="att-1", full_name="Chad Van Horn, Esq."),
        SimpleNamespace(id="att-2", full_name="Patrick Cordero"),
    ]
    params = WizardSourceParams(
        source=SourceKind.ATTORNEY,
        presentation_shape=PresentationShape.DROPDOWN,
        label="Pick the attorney",
    )
    with patch(
        "src.core.studio_v2.resolvers.user_input.AttorneyRosterRepository.list",
        new=AsyncMock(return_value=fake_roster),
    ):
        env = await emit_attorney_pick_envelope(
            template_variable="attorney_name",
            params=params,
            multi_select=False,
        )
    assert env.kind == "attorney_pick"
    assert env.label == "Pick the attorney"
    assert env.multi_select is False
    assert len(env.options) == 2
    assert env.options[0].id == "att-1"
    assert env.options[0].display_name == "Chad Van Horn, Esq."


@pytest.mark.unit
@pytest.mark.asyncio
async def test_attorney_pick_multi_select_carries_pick_bounds():
    """multi_select=True respects params.min_picks / max_picks."""
    fake_roster = [SimpleNamespace(id="att-1", full_name="Chad")]
    params = WizardSourceParams(
        source=SourceKind.ATTORNEY,
        presentation_shape=PresentationShape.MULTI_SELECT,
        min_picks=2, max_picks=4,
    )
    with patch(
        "src.core.studio_v2.resolvers.user_input.AttorneyRosterRepository.list",
        new=AsyncMock(return_value=fake_roster),
    ):
        env = await emit_attorney_pick_envelope(
            template_variable="cosignatories",
            params=params,
            multi_select=True,
        )
    assert env.multi_select is True
    assert env.min_picks == 2
    assert env.max_picks == 4


@pytest.mark.unit
@pytest.mark.asyncio
async def test_attorney_pick_roster_failure_returns_empty_options():
    """DB failure → empty options, no crash. FE then shows an empty
    picker rather than the request 500ing."""
    params = WizardSourceParams(
        source=SourceKind.ATTORNEY,
        presentation_shape=PresentationShape.DROPDOWN,
    )
    with patch(
        "src.core.studio_v2.resolvers.user_input.AttorneyRosterRepository.list",
        new=AsyncMock(side_effect=RuntimeError("DB down")),
    ):
        env = await emit_attorney_pick_envelope(
            template_variable="attorney_name",
            params=params,
            multi_select=False,
        )
    assert env.options == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_attorney_pick_dropdown_label_falls_back_to_humanized_name():
    """When params.label is None, humanize the variable name."""
    params = WizardSourceParams(
        source=SourceKind.ATTORNEY,
        presentation_shape=PresentationShape.DROPDOWN,
        label=None,
    )
    with patch(
        "src.core.studio_v2.resolvers.user_input.AttorneyRosterRepository.list",
        new=AsyncMock(return_value=[]),
    ):
        env = await emit_attorney_pick_envelope(
            template_variable="signing_attorney",
            params=params,
            multi_select=False,
        )
    assert "signing attorney" in env.label.lower()


# ─── emit_author_input_envelope ─────────────────────────────────────


@pytest.mark.unit
def test_author_plain_text_default():
    params = WizardSourceParams(
        source=SourceKind.AUTHOR_INPUT,
        author_input_kind=AuthorInputKind.PLAIN_TEXT,
        label="Enter the basis",
        example_format="e.g. lack of standing",
        output_expectation="Concise single sentence.",
    )
    env = emit_author_input_envelope(
        template_variable="objection_basis",
        params=params,
    )
    assert env.kind == "author_text"
    assert env.label == "Enter the basis"
    assert env.placeholder == "e.g. lack of standing"
    assert env.example_output_sentence == "Concise single sentence."


@pytest.mark.unit
def test_author_date():
    """Date envelope does NOT carry a format field — Behavior Contract #6."""
    params = WizardSourceParams(
        source=SourceKind.AUTHOR_INPUT,
        author_input_kind=AuthorInputKind.DATE,
        label="Pick the service date",
    )
    env = emit_author_input_envelope(
        template_variable="service_date",
        params=params,
    )
    assert env.kind == "author_date"
    assert env.label == "Pick the service date"
    payload = env.model_dump()
    assert "format" not in payload
    assert "date_format" not in payload


@pytest.mark.unit
def test_author_with_docs():
    params = WizardSourceParams(
        source=SourceKind.AUTHOR_INPUT,
        author_input_kind=AuthorInputKind.WITH_DOCS,
        label="Explain the hardship",
    )
    env = emit_author_input_envelope(
        template_variable="hardship_narrative",
        params=params,
    )
    assert env.kind == "author_docs"
    assert env.label == "Explain the hardship"
    assert ".pdf" in env.accepted_file_types
    assert ".docx" in env.accepted_file_types


@pytest.mark.unit
def test_author_input_none_kind_falls_back_to_plain_text():
    """Defensive: legacy spec with author_input_kind=None defaults to plain_text."""
    params = WizardSourceParams(
        source=SourceKind.AUTHOR_INPUT,
        author_input_kind=None,
    )
    env = emit_author_input_envelope(
        template_variable="legacy_field",
        params=params,
    )
    assert env.kind == "author_text"


@pytest.mark.unit
def test_author_label_falls_back_to_humanized_name():
    params = WizardSourceParams(
        source=SourceKind.AUTHOR_INPUT,
        author_input_kind=AuthorInputKind.PLAIN_TEXT,
        label=None,
    )
    env = emit_author_input_envelope(
        template_variable="case_summary",
        params=params,
    )
    assert "case summary" in env.label.lower()
