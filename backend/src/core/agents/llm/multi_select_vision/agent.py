"""Multi-select vision-fallback agent.

Re-extracts multi_select_from_case_vector options directly from the
case's petition PDF using claude-opus-4-6's Document content block.
Triggered by `UserInputResolver.apply` when DropdownAgent's pgvector
extraction returns fewer options than the source's `min_picks` AND the
case has a petition PDF available.

Returns `list[str]` to the caller (option strings matching
`example_formats`). The structured output also carries per-option
reasoning + an overall `extraction_notes` field — captured in the
LangSmith trace and logged at INFO — so authors can debug why specific
rows in the PDF were extracted, skipped, or missed entirely.
"""

import logging

from pydantic import BaseModel, Field

from src.core.common.constants import CLAUDE_MODEL_VISION

from ...types.sources import MultiSelectFromCaseVectorSourceParams
from ..base import Agent
from .prompt_builder import build_multi_select_vision_prompt

logger = logging.getLogger(__name__)


class _ExtractedOption(BaseModel):
    """One option extracted from the petition PDF, with reasoning trail."""
    value: str = Field(
        description=(
            "The option string, matching exactly one of the example_formats. "
            "This is what the user sees in the multi-select card UI."
        ),
    )
    reasoning: str = Field(
        default="",
        description=(
            "Brief explanation of why this row was extracted: which "
            "schedule / page / row number it came from, which "
            "example_format shape it matched, and any field-trimming "
            "decisions made (e.g. dropped trailing $ amount). "
            "Debug-only — not shown in the FE."
        ),
    )
    supersedes: str | None = Field(
        default=None,
        description=(
            "When this option refers to the SAME real-world entity as one "
            "in <existing_options> but `value` is a better-shaped match for "
            "the example_formats than the baseline version (e.g. baseline "
            "is '2018 Mercedes G-Wagon' and you produced '2018 Mercedes "
            "G-Wagon - VIN# X' which fully matches the format), set this "
            "to the EXACT baseline string this option replaces. The "
            "resolver drops the matching baseline string and keeps your "
            "richer version. Leave null when the option is brand new."
        ),
    )


class _ExtractedMultiSelectOptions(BaseModel):
    """Structured-output target for the multi-select vision agent.

    Carries the option list AND a debug trail (per-option reasoning +
    overall extraction_notes) so authors can diagnose under-extraction
    or wrong-section pulls from LangSmith without re-running.
    """

    extraction_notes: str = Field(
        default="",
        description=(
            "Overall notes on the extraction pass: which schedule(s) the "
            "LLM searched, how many candidate rows were considered, why "
            "any plausible rows were rejected (e.g. didn't match any "
            "example_format), and whether the cap of 20 options was hit. "
            "Debug-only — not shown in the FE."
        ),
    )
    options: list[_ExtractedOption] = Field(default_factory=list, max_length=20)


class VisionExtractionResult(BaseModel):
    """Caller-facing return shape from `MultiSelectVisionAgent.run`.

    `options` is the list of vision-extracted `value` strings to surface
    to the user. `superseded_baseline` is the list of baseline strings
    the resolver should DROP because vision returned a better-shaped
    version of the same canonical item — keeps the contract simple
    (`list[str]`) for the values while letting the resolver run the
    supersede merge in one place.
    """
    options: list[str] = Field(default_factory=list)
    superseded_baseline: list[str] = Field(default_factory=list)


class MultiSelectVisionAgent(Agent[_ExtractedMultiSelectOptions]):
    """Re-extract multi_select options from the petition PDF when pgvector
    chunk retrieval came up short. Vision-capable LLM reads checkboxes,
    tabular data, and form layout that the chunked text loses."""

    output_type = _ExtractedMultiSelectOptions
    model = CLAUDE_MODEL_VISION
    max_tokens = 8000
    tags = ["core", "agent", "multi_select_vision"]
    cost_kind = "multi_select_vision"

    @classmethod
    async def run(
        cls,
        petition_pdf_b64: str,
        params: MultiSelectFromCaseVectorSourceParams,
        variable_name: str | None = None,
        baseline_options: list[str] | None = None,
    ) -> VisionExtractionResult:
        """Run the vision pass over the attached petition PDF.

        Returns a `VisionExtractionResult` carrying `options` (vision-
        extracted value strings to add) and `superseded_baseline` (baseline
        strings to drop because vision produced a better-shaped version of
        the same canonical item). Returns an empty result on any failure
        (logged) so the caller can fall through to whatever DropdownAgent
        originally produced — never breaks the pipeline.

        `baseline_options`, when provided, is rendered as an
        `<existing_options>` block in the prompt. The LLM is instructed
        to either SKIP items already represented in the baseline, OR
        return its better-shaped version with `supersedes` set — the
        resolver then drops the matching baseline string. Handles the
        bug where baseline had 'Mercedes G-Wagon' but vision could
        produce '2018 Mercedes G-Wagon - VIN# X' that fully matches
        example_formats: keep the richer one, drop the bare one.

        Per-option reasoning + overall extraction_notes are logged at INFO
        and captured in the LangSmith trace as part of the structured
        output, so authors can debug under-extraction without re-running.
        """
        if not petition_pdf_b64:
            return VisionExtractionResult()
        prompt_text = build_multi_select_vision_prompt(
            params,
            baseline_options=baseline_options,
        )
        content_blocks: list[dict] = [
            {
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": "application/pdf",
                    "data": petition_pdf_b64,
                },
            },
            {"type": "text", "text": prompt_text},
        ]
        try:
            result = await cls._invoke_multimodal(
                content_blocks,
                run_name="MultiSelectVisionAgent",
                metadata={
                    "variable": variable_name or "",
                    "format_count": str(len(params.example_formats)),
                },
            )
            if result is None:
                return VisionExtractionResult()
            cls._log_extraction_trail(variable_name, result)
            return VisionExtractionResult(
                options=[opt.value for opt in result.options],
                superseded_baseline=[
                    opt.supersedes for opt in result.options
                    if opt.supersedes and opt.supersedes.strip()
                ],
            )
        except Exception as e:
            logger.error(
                f"MultiSelectVisionAgent failed for '{variable_name or '<unknown>'}': {e}"
            )
            return VisionExtractionResult()

    @classmethod
    def _log_extraction_trail(
        cls,
        variable_name: str | None,
        result: _ExtractedMultiSelectOptions,
    ) -> None:
        """Log the extraction reasoning at INFO so it surfaces in app logs.

        LangSmith already captures the structured output, but echoing the
        same data into our logs makes it grep-able and visible without
        leaving the terminal.
        """
        var = variable_name or "<unknown>"
        if result.extraction_notes:
            logger.info(
                "MultiSelectVisionAgent[%s] extraction_notes: %s",
                var, result.extraction_notes,
            )
        for idx, opt in enumerate(result.options):
            logger.info(
                "MultiSelectVisionAgent[%s] option[%d]=%r reasoning=%s supersedes=%s",
                var,
                idx,
                opt.value,
                opt.reasoning or "<none>",
                opt.supersedes or "<none>",
            )
        if not result.options:
            logger.info(
                "MultiSelectVisionAgent[%s] returned 0 options", var,
            )
