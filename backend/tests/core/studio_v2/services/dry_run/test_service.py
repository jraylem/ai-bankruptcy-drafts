"""Tests for execute_dry_run_v2 + resume_dry_run_v2.

Patches:
- TemplatesV2Repository.get → return a synthetic persisted row
- CaseRepository.get → return a fake case object
- r2_service.download_file → return small docx bytes
- run_initial_stages_v2 / run_resume_stages_v2 / finalize_run_v2 /
  run_bundle_v2 → fabricate orchestration results

So we exercise the service's orchestration WITHOUT real DB / R2 / LLM.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from src.core.studio_v2.services.dry_run import execute_dry_run_v2, resume_dry_run_v2
from src.core.studio_v2.types.bundling import (
    FixedCompanion,
    TemplateConfigV2,
    TemplateRole,
)
from src.core.studio_v2.types.fields import TemplateSpecV2
from src.core.studio_v2.types.orchestration import (
    AwaitingInputResponseV2,
    BundleChildRunV2,
    DryRunResponseV2,
    FinalizedRunV2,
    InitialStagesResultV2,
)
from src.core.studio_v2.types.pending import PendingAuthorTextV2
from src.core.studio_v2.types.resolution import ResolvedTemplateValueV2


_TEMPLATE_UUID = "00000000-0000-0000-0000-000000000099"


def _spec(fields=None):
    return TemplateSpecV2(template_id=_TEMPLATE_UUID, fields=fields or [])


def _persisted_row(*, config: dict | None = None):
    return SimpleNamespace(
        id=_TEMPLATE_UUID,
        name="test template",
        config=config or {"role": "single", "companions": []},
    )


def _case():
    return SimpleNamespace(
        id="case-1", case_number="26-12345", case_name="Doe, John",
        case_file_collection=None, petition_pdf_url=None,
    )


def _finalized():
    return FinalizedRunV2(
        resolved_values=[ResolvedTemplateValueV2(
            template_variable="x", value="v",
        )],
        generated_doc_url="https://r2/parent.docx",
        r2_object_key="cases/case-1/dry_run/abc.docx",
        unresolved=[],
        warnings=[],
        filled_bytes=b"PK\x00fake",
    )


# ─── execute_dry_run_v2 ─────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
async def test_missing_template_id_400():
    with pytest.raises(HTTPException) as exc:
        await execute_dry_run_v2(
            template_id="", template_spec=_spec(), case_id="case-1",
        )
    assert exc.value.status_code == 400


@pytest.mark.unit
@pytest.mark.asyncio
async def test_missing_case_id_400():
    with pytest.raises(HTTPException) as exc:
        await execute_dry_run_v2(
            template_id=_TEMPLATE_UUID, template_spec=_spec(), case_id="",
        )
    assert exc.value.status_code == 400


@pytest.mark.unit
@pytest.mark.asyncio
async def test_template_not_found_404():
    with patch(
        "src.core.studio_v2.services.dry_run.service.TemplatesV2Repository.get",
        new=AsyncMock(return_value=None),
    ):
        with pytest.raises(HTTPException) as exc:
            await execute_dry_run_v2(
                template_id=_TEMPLATE_UUID, template_spec=_spec(),
                case_id="case-1",
            )
    assert exc.value.status_code == 404
    assert "Template" in str(exc.value.detail)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_case_not_found_404():
    with patch(
        "src.core.studio_v2.services.dry_run.service.TemplatesV2Repository.get",
        new=AsyncMock(return_value=_persisted_row()),
    ), patch(
        "src.core.studio_v2.services.dry_run.service.CaseRepository.get",
        new=AsyncMock(return_value=None),
    ):
        with pytest.raises(HTTPException) as exc:
            await execute_dry_run_v2(
                template_id=_TEMPLATE_UUID, template_spec=_spec(),
                case_id="missing",
            )
    assert exc.value.status_code == 404
    assert "Case" in str(exc.value.detail)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dry_run_pauses_with_awaiting_input_when_pending():
    pending = {"narrative": PendingAuthorTextV2(label="Type the narrative")}
    with patch(
        "src.core.studio_v2.services.dry_run.service.TemplatesV2Repository.get",
        new=AsyncMock(return_value=_persisted_row()),
    ), patch(
        "src.core.studio_v2.services.dry_run.service.CaseRepository.get",
        new=AsyncMock(return_value=_case()),
    ), patch(
        "src.core.studio_v2.services.dry_run.service.r2_service.download_file",
        new=AsyncMock(return_value=b"PK\x00fake"),
    ), patch(
        "src.core.studio_v2.services.dry_run.service.run_initial_stages_v2",
        new=AsyncMock(return_value=InitialStagesResultV2(
            all_resolved=[], pending_inputs=pending,
        )),
    ):
        result = await execute_dry_run_v2(
            template_id=_TEMPLATE_UUID, template_spec=_spec(),
            case_id="case-1",
        )
    assert isinstance(result, AwaitingInputResponseV2)
    assert result.template_id == _TEMPLATE_UUID
    assert result.case_id == "case-1"
    assert "narrative" in result.pending_inputs
    # template_spec is ECHOED so the FE can re-send on resume.
    assert result.template_spec is not None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dry_run_completes_with_dry_run_response_when_no_pending():
    with patch(
        "src.core.studio_v2.services.dry_run.service.TemplatesV2Repository.get",
        new=AsyncMock(return_value=_persisted_row()),
    ), patch(
        "src.core.studio_v2.services.dry_run.service.CaseRepository.get",
        new=AsyncMock(return_value=_case()),
    ), patch(
        "src.core.studio_v2.services.dry_run.service.r2_service.download_file",
        new=AsyncMock(return_value=b"PK\x00fake"),
    ), patch(
        "src.core.studio_v2.services.dry_run.service.run_initial_stages_v2",
        new=AsyncMock(return_value=InitialStagesResultV2(
            all_resolved=[ResolvedTemplateValueV2(template_variable="x", value="v")],
            pending_inputs=None,
        )),
    ), patch(
        "src.core.studio_v2.services.dry_run.service.finalize_run_v2",
        new=AsyncMock(return_value=_finalized()),
    ):
        result = await execute_dry_run_v2(
            template_id=_TEMPLATE_UUID, template_spec=_spec(),
            case_id="case-1",
        )
    assert isinstance(result, DryRunResponseV2)
    assert result.status == "completed"
    assert result.generated_doc_url == "https://r2/parent.docx"
    assert result.children == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dry_run_runs_bundling_when_master_role_with_companions():
    """When the candidate bundle_role is master + companions are
    present, run_bundle_v2 fires after finalize and its children land
    in the response."""
    candidate_companions = [
        {"kind": "fixed", "id": "c1", "label": "Cover",
         "child_template_id": "00000000-0000-0000-0000-000000000010"},
    ]
    fake_child = BundleChildRunV2(
        template_id="00000000-0000-0000-0000-000000000010",
        template_name="Cover",
        companion_label="Cover",
        finalized=_finalized(),
    )
    with patch(
        "src.core.studio_v2.services.dry_run.service.TemplatesV2Repository.get",
        new=AsyncMock(return_value=_persisted_row()),
    ), patch(
        "src.core.studio_v2.services.dry_run.service.CaseRepository.get",
        new=AsyncMock(return_value=_case()),
    ), patch(
        "src.core.studio_v2.services.dry_run.service.r2_service.download_file",
        new=AsyncMock(return_value=b"PK\x00fake"),
    ), patch(
        "src.core.studio_v2.services.dry_run.service.run_initial_stages_v2",
        new=AsyncMock(return_value=InitialStagesResultV2(
            all_resolved=[], pending_inputs=None,
        )),
    ), patch(
        "src.core.studio_v2.services.dry_run.service.finalize_run_v2",
        new=AsyncMock(return_value=_finalized()),
    ), patch(
        "src.core.studio_v2.services.dry_run.service.run_bundle_v2",
        new=AsyncMock(return_value=[fake_child]),
    ) as bundle_mock:
        result = await execute_dry_run_v2(
            template_id=_TEMPLATE_UUID, template_spec=_spec(),
            case_id="case-1",
            candidate_bundle_role="master",
            candidate_bundle_companions=candidate_companions,
        )
    bundle_mock.assert_awaited_once()
    assert isinstance(result, DryRunResponseV2)
    assert len(result.children) == 1
    assert result.children[0].template_name == "Cover"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dry_run_skips_bundling_when_role_is_single():
    """Even with persisted companions, role=single skips bundling."""
    persisted = _persisted_row(config={
        "role": "master",
        "companions": [{"kind": "fixed", "id": "c1", "label": "x",
                        "child_template_id": "00000000-0000-0000-0000-000000000010"}],
    })
    with patch(
        "src.core.studio_v2.services.dry_run.service.TemplatesV2Repository.get",
        new=AsyncMock(return_value=persisted),
    ), patch(
        "src.core.studio_v2.services.dry_run.service.CaseRepository.get",
        new=AsyncMock(return_value=_case()),
    ), patch(
        "src.core.studio_v2.services.dry_run.service.r2_service.download_file",
        new=AsyncMock(return_value=b"PK\x00fake"),
    ), patch(
        "src.core.studio_v2.services.dry_run.service.run_initial_stages_v2",
        new=AsyncMock(return_value=InitialStagesResultV2(
            all_resolved=[], pending_inputs=None,
        )),
    ), patch(
        "src.core.studio_v2.services.dry_run.service.finalize_run_v2",
        new=AsyncMock(return_value=_finalized()),
    ), patch(
        "src.core.studio_v2.services.dry_run.service.run_bundle_v2",
        new=AsyncMock(return_value=[]),
    ) as bundle_mock:
        # Override candidate role to single — should skip bundling.
        result = await execute_dry_run_v2(
            template_id=_TEMPLATE_UUID, template_spec=_spec(),
            case_id="case-1",
            candidate_bundle_role="single",
        )
    bundle_mock.assert_not_called()
    assert result.children == []


# ─── resume_dry_run_v2 ──────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
async def test_resume_finalizes_and_returns_dry_run_response():
    """Resume always returns DryRunResponseV2 (never pauses again)."""
    resolved = [ResolvedTemplateValueV2(template_variable="x", value="picked")]
    with patch(
        "src.core.studio_v2.services.dry_run.service.TemplatesV2Repository.get",
        new=AsyncMock(return_value=_persisted_row()),
    ), patch(
        "src.core.studio_v2.services.dry_run.service.CaseRepository.get",
        new=AsyncMock(return_value=_case()),
    ), patch(
        "src.core.studio_v2.services.dry_run.service.r2_service.download_file",
        new=AsyncMock(return_value=b"PK\x00fake"),
    ), patch(
        "src.core.studio_v2.services.dry_run.service.run_resume_stages_v2",
        new=AsyncMock(return_value=resolved),
    ) as resume_mock, patch(
        "src.core.studio_v2.services.dry_run.service.finalize_run_v2",
        new=AsyncMock(return_value=_finalized()),
    ):
        result = await resume_dry_run_v2(
            template_id=_TEMPLATE_UUID,
            template_spec=_spec(),
            case_id="case-1",
            resolved_values=[],
            user_picks={},
            pending_inputs=None,
        )
    resume_mock.assert_awaited_once()
    assert isinstance(result, DryRunResponseV2)
    assert result.status == "completed"
    # The resolved_values from finalize are surfaced on the response.
    assert any(rv.template_variable == "x" for rv in result.resolved_values)


# ─── candidate bundling config validation ───────────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
async def test_invalid_candidate_bundle_role_400():
    with patch(
        "src.core.studio_v2.services.dry_run.service.TemplatesV2Repository.get",
        new=AsyncMock(return_value=_persisted_row()),
    ), patch(
        "src.core.studio_v2.services.dry_run.service.CaseRepository.get",
        new=AsyncMock(return_value=_case()),
    ), patch(
        "src.core.studio_v2.services.dry_run.service.r2_service.download_file",
        new=AsyncMock(return_value=b"PK\x00fake"),
    ), patch(
        "src.core.studio_v2.services.dry_run.service.run_initial_stages_v2",
        new=AsyncMock(return_value=InitialStagesResultV2(
            all_resolved=[], pending_inputs=None,
        )),
    ), patch(
        "src.core.studio_v2.services.dry_run.service.finalize_run_v2",
        new=AsyncMock(return_value=_finalized()),
    ):
        with pytest.raises(HTTPException) as exc:
            await execute_dry_run_v2(
                template_id=_TEMPLATE_UUID, template_spec=_spec(),
                case_id="case-1",
                candidate_bundle_role="not-a-real-role",
            )
    assert exc.value.status_code == 400
    assert "Invalid bundle_role" in str(exc.value.detail)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_invalid_candidate_companions_400():
    with patch(
        "src.core.studio_v2.services.dry_run.service.TemplatesV2Repository.get",
        new=AsyncMock(return_value=_persisted_row()),
    ), patch(
        "src.core.studio_v2.services.dry_run.service.CaseRepository.get",
        new=AsyncMock(return_value=_case()),
    ), patch(
        "src.core.studio_v2.services.dry_run.service.r2_service.download_file",
        new=AsyncMock(return_value=b"PK\x00fake"),
    ), patch(
        "src.core.studio_v2.services.dry_run.service.run_initial_stages_v2",
        new=AsyncMock(return_value=InitialStagesResultV2(
            all_resolved=[], pending_inputs=None,
        )),
    ), patch(
        "src.core.studio_v2.services.dry_run.service.finalize_run_v2",
        new=AsyncMock(return_value=_finalized()),
    ):
        with pytest.raises(HTTPException) as exc:
            await execute_dry_run_v2(
                template_id=_TEMPLATE_UUID, template_spec=_spec(),
                case_id="case-1",
                candidate_bundle_role="master",
                # Missing required `kind` discriminator field.
                candidate_bundle_companions=[{"id": "c1", "label": "x"}],
            )
    assert exc.value.status_code == 400
    assert "Candidate bundle_companions" in str(exc.value.detail)
