"""Tests for `publish_template_v2` — Phase 3 publish gate.

Mocks both repositories so we exercise the validation + snapshot
logic without a live DB session. Covers:

- 404 when template not found (soft-deleted or missing).
- 400 with VALIDATION_FAILED detail when validators surface errors.
- happy path: clean validation → published_spec snapshot via repo,
  published_at set, refreshed row returned.
- 404 race when the row gets deleted between the initial fetch and
  the update_published_snapshot commit.
- `_orm_field_to_pydantic` converts both populated and None `params`
  rows correctly.
- `_build_published_spec` snapshot shape includes template id +
  name + config + every field as model_dump(mode=json).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from src.core.studio_v2.services.composer.publish import (
    _build_published_spec,
    _orm_field_to_pydantic,
    publish_template_v2,
)
from src.core.studio_v2.types.fields import TemplateFieldV2
from src.core.studio_v2.types.wizard_sources import (
    PresentationShape,
    SourceKind,
    WizardSourceParams,
)


_TEMPLATE_UUID = "00000000-0000-0000-0000-000000000001"
_FIELD_UUID = "00000000-0000-0000-0000-000000000002"


def _fake_template(*, config: dict | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        id=_TEMPLATE_UUID,
        name="Demo Template",
        config=config if config is not None else {"role": "single", "companions": []},
        published_at=None,
        published_spec=None,
    )


def _fake_field_row(
    name: str = "debtor_name",
    params: dict | None = None,
    template_property_marker: str | None = "JANE SMITH",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=_FIELD_UUID,
        template_id=_TEMPLATE_UUID,
        template_variable=name,
        template_property_marker=template_property_marker,
        template_property_marker_aliases=None,
        template_identifying_text_match=None,
        description=None,
        template_index=0,
        params=params,
    )


# ─── 404 ────────────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
async def test_publish_returns_404_when_template_missing():
    with patch(
        "src.core.studio_v2.services.composer.publish.TemplatesV2Repository.get",
        new=AsyncMock(return_value=None),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await publish_template_v2(_TEMPLATE_UUID)
    assert exc_info.value.status_code == 404


# ─── validation failure ────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
async def test_publish_returns_400_with_validation_errors():
    """Validator surfacing errors blocks publish + returns structured
    detail the FE picks up via api.ts's validationErrors path."""
    template = _fake_template()
    bad_field = _fake_field_row(
        params={
            "source": SourceKind.DERIVED_FROM_VARIABLE.value,
            "presentation_shape": PresentationShape.RAW.value,
            "dependent_variable": "self_reference_not_allowed",
        },
        template_property_marker="X",
    )
    # Set template_variable so the self-reference check triggers
    bad_field.template_variable = "self_reference_not_allowed"

    with patch(
        "src.core.studio_v2.services.composer.publish.TemplatesV2Repository.get",
        new=AsyncMock(return_value=template),
    ), patch(
        "src.core.studio_v2.services.composer.publish.TemplateFieldsV2Repository.list_for_template",
        new=AsyncMock(return_value=[bad_field]),
    ), patch(
        "src.core.studio_v2.orchestration.validators.ReferenceDataRepository.list",
        new=AsyncMock(return_value=[]),
    ), patch(
        "src.core.studio_v2.orchestration.validators.AttorneyRosterRepository.list",
        new=AsyncMock(return_value=[]),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await publish_template_v2(_TEMPLATE_UUID)

    assert exc_info.value.status_code == 400
    detail = exc_info.value.detail
    assert detail["code"] == "VALIDATION_FAILED"
    assert isinstance(detail["validation_errors"], list)
    assert len(detail["validation_errors"]) > 0


# ─── happy path ────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
async def test_publish_happy_path_calls_update_published_snapshot():
    """Clean spec → published_spec snapshot via repo + return refreshed row."""
    template = _fake_template()
    field = _fake_field_row(
        params={
            "source": SourceKind.GMAIL.value,
            "presentation_shape": PresentationShape.RAW.value,
            "extraction_prompt": "x",
        },
    )
    refreshed = _fake_template(config=template.config)
    refreshed.published_at = "2026-05-27T12:00:00Z"

    snapshot_mock = AsyncMock(return_value=refreshed)
    with patch(
        "src.core.studio_v2.services.composer.publish.TemplatesV2Repository.get",
        new=AsyncMock(return_value=template),
    ), patch(
        "src.core.studio_v2.services.composer.publish.TemplateFieldsV2Repository.list_for_template",
        new=AsyncMock(return_value=[field]),
    ), patch(
        "src.core.studio_v2.services.composer.publish.TemplatesV2Repository.update_published_snapshot",
        new=snapshot_mock,
    ), patch(
        "src.core.studio_v2.orchestration.validators.ReferenceDataRepository.list",
        new=AsyncMock(return_value=[]),
    ), patch(
        "src.core.studio_v2.orchestration.validators.AttorneyRosterRepository.list",
        new=AsyncMock(return_value=[]),
    ):
        result = await publish_template_v2(_TEMPLATE_UUID)

    assert result is refreshed
    snapshot_mock.assert_awaited_once()
    call_kwargs = snapshot_mock.await_args.kwargs
    assert call_kwargs["template_id"] == _TEMPLATE_UUID
    spec = call_kwargs["published_spec"]
    assert spec["template_id"] == _TEMPLATE_UUID
    assert spec["name"] == "Demo Template"
    assert spec["config"] == {"role": "single", "companions": []}
    assert len(spec["fields"]) == 1
    assert spec["fields"][0]["template_variable"] == "debtor_name"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_publish_raises_404_when_update_races_to_deletion():
    """Row was active at the initial fetch but deleted before the
    snapshot UPDATE committed — repo returns None."""
    template = _fake_template()
    field = _fake_field_row(
        params={
            "source": SourceKind.GMAIL.value,
            "presentation_shape": PresentationShape.RAW.value,
            "extraction_prompt": "x",
        },
    )

    with patch(
        "src.core.studio_v2.services.composer.publish.TemplatesV2Repository.get",
        new=AsyncMock(return_value=template),
    ), patch(
        "src.core.studio_v2.services.composer.publish.TemplateFieldsV2Repository.list_for_template",
        new=AsyncMock(return_value=[field]),
    ), patch(
        "src.core.studio_v2.services.composer.publish.TemplatesV2Repository.update_published_snapshot",
        new=AsyncMock(return_value=None),
    ), patch(
        "src.core.studio_v2.orchestration.validators.ReferenceDataRepository.list",
        new=AsyncMock(return_value=[]),
    ), patch(
        "src.core.studio_v2.orchestration.validators.AttorneyRosterRepository.list",
        new=AsyncMock(return_value=[]),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await publish_template_v2(_TEMPLATE_UUID)
    assert exc_info.value.status_code == 404


# ─── helpers ────────────────────────────────────────────────────────


@pytest.mark.unit
def test_orm_field_to_pydantic_with_params():
    row = _fake_field_row(
        params={
            "source": SourceKind.GMAIL.value,
            "presentation_shape": PresentationShape.RAW.value,
            "extraction_prompt": "find the debtor",
        },
    )
    result = _orm_field_to_pydantic(row)
    assert isinstance(result, TemplateFieldV2)
    assert result.template_variable == "debtor_name"
    assert isinstance(result.params, WizardSourceParams)
    assert result.params.source == SourceKind.GMAIL


@pytest.mark.unit
def test_orm_field_to_pydantic_with_none_params():
    row = _fake_field_row(params=None)
    result = _orm_field_to_pydantic(row)
    assert isinstance(result, TemplateFieldV2)
    assert result.params is None


@pytest.mark.unit
def test_build_published_spec_includes_template_metadata():
    template = _fake_template(config={"role": "master", "companions": []})
    field = TemplateFieldV2(
        id=_FIELD_UUID,
        template_id=_TEMPLATE_UUID,
        template_variable="debtor_name",
        template_property_marker="JANE SMITH",
        template_index=0,
        params=None,
    )
    spec = _build_published_spec(template, [field])
    assert spec["template_id"] == _TEMPLATE_UUID
    assert spec["name"] == "Demo Template"
    assert spec["config"] == {"role": "master", "companions": []}
    assert len(spec["fields"]) == 1
    assert spec["fields"][0]["template_variable"] == "debtor_name"
    assert spec["fields"][0]["template_property_marker"] == "JANE SMITH"


@pytest.mark.unit
def test_build_published_spec_handles_none_config():
    template = SimpleNamespace(
        id=_TEMPLATE_UUID,
        name="No Config",
        config=None,
        published_at=None,
        published_spec=None,
    )
    spec = _build_published_spec(template, [])
    assert spec["config"] == {}
    assert spec["fields"] == []
