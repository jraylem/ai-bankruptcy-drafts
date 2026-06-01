"""Tests for assert_part_of_packet_has_no_user_input_v2.

Validator must work against BOTH `TemplateFieldV2` (Pydantic) inputs
AND `TemplateFieldV2` ORM rows (with `params` as a dict). Both shapes
are exercised here."""

from types import SimpleNamespace

import pytest

from src.core.studio_v2.orchestration.validators import (
    assert_part_of_packet_has_no_user_input_v2,
)
from src.core.studio_v2.types.fields import TemplateFieldV2
from src.core.studio_v2.types.wizard_sources import (
    AuthorInputKind,
    PresentationShape,
    SourceKind,
    WizardSourceParams,
)


_FIELD_UUID = "00000000-0000-0000-0000-000000000001"
_TEMPLATE_UUID = "00000000-0000-0000-0000-000000000002"


def _pydantic_field(name, params):
    return TemplateFieldV2(
        id=_FIELD_UUID, template_id=_TEMPLATE_UUID,
        template_variable=name, params=params,
    )


def _orm_row(name, params_dict):
    """Mimic an ORM row with dict-shaped params (the JSONB shape)."""
    return SimpleNamespace(template_variable=name, params=params_dict)


# ─── Pydantic input ─────────────────────────────────────────────────


@pytest.mark.unit
def test_author_input_is_user_input_offender():
    field = _pydantic_field(
        "narrative",
        WizardSourceParams(
            source=SourceKind.AUTHOR_INPUT,
            author_input_kind=AuthorInputKind.PLAIN_TEXT,
        ),
    )
    assert assert_part_of_packet_has_no_user_input_v2([field]) == ["narrative"]


@pytest.mark.unit
@pytest.mark.parametrize(
    "source,shape,expected_offender",
    [
        (SourceKind.GMAIL, PresentationShape.DROPDOWN, True),
        (SourceKind.GMAIL, PresentationShape.CHIP, True),
        (SourceKind.GMAIL, PresentationShape.MULTI_SELECT, True),
        (SourceKind.CASE_FILE, PresentationShape.DROPDOWN, True),
        (SourceKind.CASE_FILE, PresentationShape.MULTI_SELECT, True),
        (SourceKind.ATTORNEY, PresentationShape.DROPDOWN, True),
        (SourceKind.ATTORNEY, PresentationShape.MULTI_SELECT, True),
        # raw shapes for these sources are NOT offenders.
        (SourceKind.GMAIL, PresentationShape.RAW, False),
        (SourceKind.CASE_FILE, PresentationShape.RAW, False),
        (SourceKind.ATTORNEY, PresentationShape.RAW, False),
    ],
)
def test_per_source_shape_classification(source, shape, expected_offender):
    field = _pydantic_field(
        "x", WizardSourceParams(source=source, presentation_shape=shape),
    )
    offenders = assert_part_of_packet_has_no_user_input_v2([field])
    if expected_offender:
        assert offenders == ["x"]
    else:
        assert offenders == []


@pytest.mark.unit
@pytest.mark.parametrize(
    "source",
    [
        SourceKind.CURRENT_DATE,
        SourceKind.CONSTANTS,
        SourceKind.DERIVED_FROM_VARIABLE,
        SourceKind.VALUE_FROM_PARENT_BUNDLE,
    ],
)
def test_safe_sources_never_offend(source):
    field = _pydantic_field(
        "x", WizardSourceParams(source=source, dependent_variable="y"),
    )
    assert assert_part_of_packet_has_no_user_input_v2([field]) == []


@pytest.mark.unit
def test_offenders_returned_sorted():
    fields = [
        _pydantic_field("zebra", WizardSourceParams(source=SourceKind.AUTHOR_INPUT)),
        _pydantic_field("alpha", WizardSourceParams(
            source=SourceKind.GMAIL,
            presentation_shape=PresentationShape.DROPDOWN,
        )),
    ]
    assert assert_part_of_packet_has_no_user_input_v2(fields) == ["alpha", "zebra"]


@pytest.mark.unit
def test_field_with_no_params_is_ignored():
    field = TemplateFieldV2(
        id=_FIELD_UUID, template_id=_TEMPLATE_UUID,
        template_variable="x", params=None,
    )
    assert assert_part_of_packet_has_no_user_input_v2([field]) == []


# ─── ORM row input (params as dict) ─────────────────────────────────


@pytest.mark.unit
def test_orm_row_dict_params_author_input():
    row = _orm_row("x", {"source": "author_input"})
    assert assert_part_of_packet_has_no_user_input_v2([row]) == ["x"]


@pytest.mark.unit
def test_orm_row_dict_params_gmail_dropdown():
    row = _orm_row(
        "x",
        {"source": "gmail", "presentation_shape": "dropdown"},
    )
    assert assert_part_of_packet_has_no_user_input_v2([row]) == ["x"]


@pytest.mark.unit
def test_orm_row_dict_params_gmail_raw_is_safe():
    row = _orm_row(
        "x",
        {"source": "gmail", "presentation_shape": "raw"},
    )
    assert assert_part_of_packet_has_no_user_input_v2([row]) == []


@pytest.mark.unit
def test_orm_row_dict_params_missing_shape_defaults_to_raw():
    row = _orm_row("x", {"source": "gmail"})
    assert assert_part_of_packet_has_no_user_input_v2([row]) == []


@pytest.mark.unit
def test_orm_row_with_none_params_ignored():
    row = _orm_row("x", None)
    assert assert_part_of_packet_has_no_user_input_v2([row]) == []
