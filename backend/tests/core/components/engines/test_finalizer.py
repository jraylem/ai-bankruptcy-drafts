"""Tests for the shared finalizer used by dry-run and draft flows.

Mocks every external seam (R2, UserInputHealAgent, DocxTemplateService.fill_template)
so we can assert the finalizer orchestrates them in the right order with the
right args, and builds the returned FinalizedRun correctly.
"""

from unittest.mock import AsyncMock

import pytest

from src.core.agents.llm.user_input_heal import UserInputHealAgent
from src.core.agents.types.resolution import ResolvedTemplateValue
from src.core.agents.types.spec import AgentConfig
from src.core.common.documents.docx_template import DocxTemplateService
from src.core.common.storage import r2 as r2_module
from src.core.agents.orchestration import finalizer as finalizer_module
from src.core.agents.orchestration.finalizer import (
    FinalizedRun,
    _build_warnings,
    finalize_run,
)
from tests.core.factories import make_resolved_value


def _install_finalize_mocks(
    monkeypatch,
    *,
    template_bytes: bytes = b"%PDF-fake-template",
    healed_values: list[ResolvedTemplateValue] | None = None,
    unresolved: list[str] | None = None,
    filled_bytes: bytes = b"%DOCX-fake-filled",
    presigned_url: str = "https://r2.example/file.docx?signed",
):
    """Wire up AsyncMocks for every external call the finalizer makes and
    return a dict of the captured mocks so each test can assert on them."""
    download = AsyncMock(return_value=template_bytes)
    upload = AsyncMock(return_value="key")
    presign = AsyncMock(return_value=presigned_url)
    heal = AsyncMock(return_value=healed_values if healed_values is not None else [])
    fill = lambda **kwargs: (filled_bytes, unresolved or [])  # noqa: E731

    monkeypatch.setattr(r2_module.r2_service, "download_file", download)
    monkeypatch.setattr(r2_module.r2_service, "upload_file", upload)
    monkeypatch.setattr(r2_module.r2_service, "get_presigned_url", presign)
    monkeypatch.setattr(UserInputHealAgent, "heal_resolved_values", heal)
    monkeypatch.setattr(DocxTemplateService, "fill_template", fill)

    return {"download": download, "upload": upload, "presign": presign, "heal": heal}


# ─── finalize_run orchestration ────────────────────────────────────────


@pytest.mark.unit
async def test_finalize_run_downloads_heals_fills_uploads_in_order(monkeypatch):
    """Verify each external call fires with the expected args. Order is
    enforced by dependency: heal needs template_bytes, fill needs healed
    values, upload needs filled bytes."""
    healed = [make_resolved_value(property_name="x", value="V")]
    mocks = _install_finalize_mocks(monkeypatch, healed_values=healed)

    agent_config = AgentConfig(template_id="tpl", template_fields=[])
    input_resolved = [make_resolved_value(property_name="x", value="raw")]

    result = await finalize_run(
        template_id="tpl",
        case_id="26_14090",
        agent_config=agent_config,
        all_resolved=input_resolved,
        output_prefix="dry_run",
    )

    mocks["download"].assert_awaited_once_with(
        template_id="tpl", filename="template.docx", prefix="template"
    )
    heal_call = mocks["heal"].await_args
    assert heal_call.kwargs["agent_config"] is agent_config
    assert heal_call.kwargs["resolved_values"] == input_resolved
    upload_call = mocks["upload"].await_args
    assert upload_call.kwargs["template_id"] == "26_14090"
    assert upload_call.kwargs["prefix"] == "cases"
    assert upload_call.kwargs["filename"].startswith("dry_run/")
    assert upload_call.kwargs["filename"].endswith(".docx")
    # Presigned URL is fetched for the same filename the upload wrote.
    presign_call = mocks["presign"].await_args
    assert presign_call.kwargs["filename"] == upload_call.kwargs["filename"]

    assert isinstance(result, FinalizedRun)
    assert result.resolved_values == healed
    assert result.generated_doc_url == "https://r2.example/file.docx?signed"


@pytest.mark.unit
@pytest.mark.parametrize("output_prefix", ["dry_run", "draft", "custom_prefix"])
async def test_finalize_run_output_prefix_is_threaded_into_filename(monkeypatch, output_prefix):
    mocks = _install_finalize_mocks(monkeypatch)

    await finalize_run(
        template_id="tpl",
        case_id="26_14090",
        agent_config=AgentConfig(template_id="tpl", template_fields=[]),
        all_resolved=[],
        output_prefix=output_prefix,
    )

    upload_filename = mocks["upload"].await_args.kwargs["filename"]
    assert upload_filename.startswith(f"{output_prefix}/")


@pytest.mark.unit
async def test_finalize_run_returns_heal_output_not_raw_input(monkeypatch):
    """The healed values (not the input ones) surface in FinalizedRun and are
    what fill_template sees. Verifies heal runs before fill, not the other way."""
    raw = [make_resolved_value(property_name="x", value="RAW")]
    healed = [make_resolved_value(property_name="x", value="HEALED")]

    captured_fill_values = {}

    def capture_fill(*, template_bytes, template_fields, resolved_values):
        captured_fill_values["resolved_values"] = resolved_values
        return (b"filled", [])

    monkeypatch.setattr(r2_module.r2_service, "download_file", AsyncMock(return_value=b"tpl"))
    monkeypatch.setattr(
        r2_module.r2_service,
        "upload_file",
        AsyncMock(return_value="cases/case/dry_run/uuid.docx"),
    )
    monkeypatch.setattr(r2_module.r2_service, "get_presigned_url", AsyncMock(return_value="url"))
    monkeypatch.setattr(UserInputHealAgent, "heal_resolved_values", AsyncMock(return_value=healed))
    monkeypatch.setattr(DocxTemplateService, "fill_template", capture_fill)

    result = await finalize_run(
        template_id="tpl",
        case_id="case",
        agent_config=AgentConfig(template_id="tpl", template_fields=[]),
        all_resolved=raw,
        output_prefix="dry_run",
    )

    # fill_template saw the healed dict, not the raw one
    assert captured_fill_values["resolved_values"] == {"x": "HEALED"}
    # FinalizedRun returns the healed list
    assert result.resolved_values == healed
    # Not the raw input
    assert result.resolved_values != raw


@pytest.mark.unit
async def test_finalize_run_warnings_for_unresolved_and_low_confidence(monkeypatch):
    """Two unresolved placeholders + one low-confidence resolved value → 3 warnings."""
    healed = [
        make_resolved_value(property_name="ok_field", value="V", confidence="high"),
        make_resolved_value(
            property_name="shaky_field",
            value="maybe",
            reasoning="not sure",
            confidence="low",
        ),
    ]
    _install_finalize_mocks(
        monkeypatch,
        healed_values=healed,
        unresolved=["[[first_missing]]", "[[second_missing]]"],
    )

    result = await finalize_run(
        template_id="tpl",
        case_id="case",
        agent_config=AgentConfig(template_id="tpl", template_fields=[]),
        all_resolved=[],
        output_prefix="dry_run",
    )

    assert result.unresolved == ["[[first_missing]]", "[[second_missing]]"]
    assert len(result.warnings) == 3
    assert any("Unresolved placeholder: [[first_missing]]" in w for w in result.warnings)
    assert any("Unresolved placeholder: [[second_missing]]" in w for w in result.warnings)
    assert any(
        "Low-confidence extraction for 'shaky_field'" in w and "not sure" in w
        for w in result.warnings
    )


# ─── _build_warnings pure function ─────────────────────────────────────


@pytest.mark.unit
def test_build_warnings_empty_when_no_issues():
    resolved = [
        make_resolved_value(property_name="a", confidence="high"),
        make_resolved_value(property_name="b", confidence="high"),
    ]
    assert _build_warnings(resolved, unresolved=[]) == []


@pytest.mark.unit
def test_build_warnings_unresolved_only():
    result = _build_warnings(
        resolved_values=[make_resolved_value(confidence="high")],
        unresolved=["[[a]]", "[[b]]"],
    )
    assert result == [
        "Unresolved placeholder: [[a]]",
        "Unresolved placeholder: [[b]]",
    ]
