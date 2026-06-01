"""Tests for `TemplateAgentV2.run` — the two-call extract → map-constants
orchestration. The LLM calls are mocked so we can drive the branch
matrix (extract failure / empty / mapping failure / mapping count
mismatch / success) without burning Anthropic tokens.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from src.core.studio_v2.agents.template.agent import (
    TemplateAgentV2,
    TemplateAgentV2Output,
)
from src.core.studio_v2.agents.template.schemas import TemplateFieldV2Extract
from src.core.studio_v2.types.wizard_sources import (
    SourceKind,
    WizardSourceParams,
)


def _make_field(name: str = "debtor_name") -> TemplateFieldV2Extract:
    return TemplateFieldV2Extract(
        template_variable=name,
        template_index=0,
        template_property_marker="John Doe",
        template_property_marker_aliases=[],
        template_variable_string=None,
        template_identifying_text_match="John Doe",
        description=None,
        params=WizardSourceParams(
            source=SourceKind.CASE_FILE,
            extraction_prompt="Extract the debtor's name from the petition.",
        ),
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_raises_502_when_extract_llm_fails():
    """Extract-phase LLM raises → caller gets HTTP 502 with the
    underlying error in the detail."""
    with patch.object(
        TemplateAgentV2,
        "_invoke",
        new=AsyncMock(side_effect=RuntimeError("anthropic 503")),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await TemplateAgentV2.run(
                document_content="A document",
                template_role="single",
            )
        assert exc_info.value.status_code == 502
        assert "anthropic 503" in exc_info.value.detail


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_raises_422_when_extract_returns_none():
    """Extract returns None → 422 'no variables extracted'."""
    with patch.object(
        TemplateAgentV2,
        "_invoke",
        new=AsyncMock(return_value=None),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await TemplateAgentV2.run(
                document_content="A document",
                template_role="single",
            )
        assert exc_info.value.status_code == 422
        assert "no variables" in exc_info.value.detail


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_raises_422_when_extract_returns_empty_spec():
    """Extract returns an Output with empty template_spec → 422."""
    empty_output = TemplateAgentV2Output(template_spec=[])
    with patch.object(
        TemplateAgentV2,
        "_invoke",
        new=AsyncMock(return_value=empty_output),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await TemplateAgentV2.run(document_content="X")
        assert exc_info.value.status_code == 422


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_returns_extract_only_when_reference_data_fetch_fails():
    """ReferenceDataRepository.list raises → return the extract-only
    result (constants-mapping skipped)."""
    extract_output = TemplateAgentV2Output(template_spec=[_make_field()])
    with patch.object(
        TemplateAgentV2,
        "_invoke",
        new=AsyncMock(return_value=extract_output),
    ), patch(
        "src.core.studio_v2.agents.template.agent.ReferenceDataRepository.list",
        new=AsyncMock(side_effect=RuntimeError("db down")),
    ):
        result = await TemplateAgentV2.run(document_content="X")
        assert result is extract_output
        assert len(result.template_spec) == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_returns_extract_only_when_no_reference_data():
    """ReferenceDataRepository.list returns empty list → skip mapping
    pass + return extract result."""
    extract_output = TemplateAgentV2Output(template_spec=[_make_field()])
    with patch.object(
        TemplateAgentV2,
        "_invoke",
        new=AsyncMock(return_value=extract_output),
    ), patch(
        "src.core.studio_v2.agents.template.agent.ReferenceDataRepository.list",
        new=AsyncMock(return_value=[]),
    ):
        result = await TemplateAgentV2.run(document_content="X")
        assert result is extract_output


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_returns_extract_only_when_mapping_llm_fails():
    """Mapping-phase LLM raises → returns extract result. Failure in
    the mapping pass is best-effort and must not abort the run."""
    extract_output = TemplateAgentV2Output(template_spec=[_make_field()])

    invoke_mock = AsyncMock(
        side_effect=[extract_output, RuntimeError("mapping LLM down")],
    )

    fake_ref_data = [
        type(
            "RefData",
            (),
            {
                "short_code": "firm_phone",
                "display_name": "Firm phone",
                "description": "Main line",
                "value": "555-1212",
            },
        )(),
    ]
    with patch.object(
        TemplateAgentV2, "_invoke", new=invoke_mock,
    ), patch(
        "src.core.studio_v2.agents.template.agent.ReferenceDataRepository.list",
        new=AsyncMock(return_value=fake_ref_data),
    ):
        result = await TemplateAgentV2.run(document_content="X")
        assert result is extract_output
        assert invoke_mock.call_count == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_returns_extract_only_when_mapping_count_mismatches():
    """Mapping returned a different number of entries (LLM hallucination
    / drop / add) → fall back to extract-only. Mismatched lengths can't
    be safely zipped back into the spec."""
    extract_output = TemplateAgentV2Output(
        template_spec=[_make_field("a"), _make_field("b")],
    )
    # Mapping returns 1 entry instead of 2 — count mismatch.
    mapping_output = TemplateAgentV2Output(template_spec=[_make_field("a")])

    invoke_mock = AsyncMock(side_effect=[extract_output, mapping_output])
    fake_ref_data = [
        type(
            "RefData",
            (),
            {
                "short_code": "firm_phone",
                "display_name": "Firm phone",
                "description": "Main line",
                "value": "555-1212",
            },
        )(),
    ]
    with patch.object(
        TemplateAgentV2, "_invoke", new=invoke_mock,
    ), patch(
        "src.core.studio_v2.agents.template.agent.ReferenceDataRepository.list",
        new=AsyncMock(return_value=fake_ref_data),
    ):
        result = await TemplateAgentV2.run(document_content="X")
        assert result is extract_output  # fell back


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_returns_mapping_output_on_success():
    """Both calls succeed + counts match → mapping output is returned."""
    extract_output = TemplateAgentV2Output(template_spec=[_make_field("a")])
    mapping_output = TemplateAgentV2Output(template_spec=[_make_field("a")])

    invoke_mock = AsyncMock(side_effect=[extract_output, mapping_output])
    fake_ref_data = [
        type(
            "RefData",
            (),
            {
                "short_code": "firm_phone",
                "display_name": "Firm phone",
                "description": "Main line",
                "value": "555-1212",
            },
        )(),
    ]
    with patch.object(
        TemplateAgentV2, "_invoke", new=invoke_mock,
    ), patch(
        "src.core.studio_v2.agents.template.agent.ReferenceDataRepository.list",
        new=AsyncMock(return_value=fake_ref_data),
    ):
        result = await TemplateAgentV2.run(document_content="X")
        assert result is mapping_output
