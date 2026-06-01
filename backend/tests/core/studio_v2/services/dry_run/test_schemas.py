"""Tests for the dry-run request schemas — covers shape, defaults,
extra=forbid, and Pydantic discrimination of user_picks."""

import pytest
from pydantic import ValidationError

from src.core.studio_v2.services.dry_run.schemas import (
    DryRunRequestV2,
    DryRunResumeRequestV2,
)
from src.core.studio_v2.types.fields import TemplateSpecV2


_TEMPLATE_UUID = "00000000-0000-0000-0000-000000000099"


@pytest.mark.unit
def test_dry_run_request_minimal_round_trip():
    req = DryRunRequestV2(
        template_id=_TEMPLATE_UUID,
        case_id="case-1",
        template_spec=TemplateSpecV2(template_id=_TEMPLATE_UUID, fields=[]),
    )
    payload = req.model_dump(mode="json")
    assert payload["template_id"] == _TEMPLATE_UUID
    assert payload["bundle_picks"] is None
    assert payload["bundle_role"] is None
    assert payload["bundle_companions"] is None


@pytest.mark.unit
def test_dry_run_request_with_bundle_overrides():
    req = DryRunRequestV2(
        template_id=_TEMPLATE_UUID,
        case_id="case-1",
        template_spec=TemplateSpecV2(template_id=_TEMPLATE_UUID, fields=[]),
        bundle_picks={"comp-b": "opt-1"},
        bundle_role="master",
        bundle_companions=[{"kind": "fixed", "id": "c1", "label": "x"}],
    )
    assert req.bundle_picks == {"comp-b": "opt-1"}
    assert req.bundle_role == "master"
    assert req.bundle_companions == [{"kind": "fixed", "id": "c1", "label": "x"}]


@pytest.mark.unit
def test_dry_run_request_extra_forbidden():
    with pytest.raises(ValidationError):
        DryRunRequestV2(
            template_id=_TEMPLATE_UUID,
            case_id="case-1",
            template_spec=TemplateSpecV2(template_id=_TEMPLATE_UUID, fields=[]),
            bogus_field="nope",
        )


@pytest.mark.unit
def test_resume_request_defaults():
    req = DryRunResumeRequestV2(
        template_id=_TEMPLATE_UUID,
        case_id="case-1",
        template_spec=TemplateSpecV2(template_id=_TEMPLATE_UUID, fields=[]),
    )
    assert req.resolved_values == []
    assert req.user_picks == {}
    assert req.pending_inputs is None


@pytest.mark.unit
def test_resume_request_user_picks_discriminated():
    """user_picks is a dict[var_name, UserSelectionV2] — Pydantic
    should pick the right pick type from the dict shape."""
    req = DryRunResumeRequestV2(
        template_id=_TEMPLATE_UUID,
        case_id="case-1",
        template_spec=TemplateSpecV2(template_id=_TEMPLATE_UUID, fields=[]),
        user_picks={
            "creditor": {"value": "Acme Bank"},
            "list": {"picked_values": ["A", "B"]},
            "narrative": {"user_text": "lost wages", "file_urls": []},
        },
    )
    from src.core.studio_v2.types.picks import (
        MultiSelectPickV2,
        SingleValuePickV2,
        SupportingDocsPickV2,
    )
    assert isinstance(req.user_picks["creditor"], SingleValuePickV2)
    assert isinstance(req.user_picks["list"], MultiSelectPickV2)
    assert isinstance(req.user_picks["narrative"], SupportingDocsPickV2)
