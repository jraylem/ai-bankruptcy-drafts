"""
Dropdown extraction agent.

LLM call site that takes a DropdownEmailSourceParams or
DropdownCaseVectorSourceParams plus raw fetched context and returns a
structured `_ExtractedOptions` carrying:
  - up to 20 dropdown options the user will later pick from verbatim,
  - a `completeness` self-assessment ("full" / "partial" / "unknown"),
  - one-sentence `completeness_reasoning` for the call.

The completeness signal lets `UserInputResolver.apply` decide when to
fire the petition-PDF vision fallback even though the option count
already satisfies `min_picks` — pgvector chunks for petition tabular
pages (Schedule A/B etc.) are often fragmentary, and trusting raw count
under-reports.

Peer of GroupDropdownAgent and RecoChipsAgent — uses the same
ChatAnthropic + with_structured_output pattern. Extractive (not
generative): options are pulled from the source material and must
resemble the author-supplied `example_format` / `example_formats`.

Orchestration (fanning out one call per dropdown field, reading
`.completeness`, gating the vision fallback) lives in
resolvers/user_input_resolver.py.
"""

import logging
from typing import Literal

from pydantic import BaseModel, Field

from ...context import FetchedContext
from ...types.sources import (
    DropdownCaseVectorSourceParams,
    DropdownEmailSourceParams,
    MultiSelectFromCaseVectorSourceParams,
    MultiSelectFromGmailSourceParams,
)
from ..base import Agent
from .prompt_builder import _EXTRACTION_PROMPT, _format_example_block

# Includes both multi-select params — they share the same `label` +
# `example_formats` shape and extract the same way; the only differences
# are the data source (case_file pgvector vs Gmail) at fetch time and
# multi-pick semantics handled in user_input_resolver.
DropdownParams = (
    DropdownEmailSourceParams
    | DropdownCaseVectorSourceParams
    | MultiSelectFromCaseVectorSourceParams
    | MultiSelectFromGmailSourceParams
)

logger = logging.getLogger(__name__)


Completeness = Literal["full", "partial", "unknown"]


class _ExtractedOptions(BaseModel):
    """Structured-output target for the dropdown extraction LLM call.

    `completeness` + `completeness_reasoning` are debug-only — never
    surfaced to end users. They're consumed by UserInputResolver to
    decide when to fire the petition-PDF vision fallback even though
    `len(options) >= min_picks`. Default values keep backward-compat:
    LLMs that don't fill the new fields fall through as "unknown".
    """

    completeness: Completeness = Field(
        default="unknown",
        description=(
            "Self-assessment of whether the source material contained the "
            "complete list of items relevant to the variable. 'full' = saw "
            "and extracted everything; 'partial' = saw fragmentary evidence "
            "(headers, totals, cross-references, related-schedule chunks) "
            "but not the itemized rows; 'unknown' = can't judge."
        ),
    )
    completeness_reasoning: str = Field(
        default="",
        description=(
            "ONE short sentence justifying the completeness call. "
            "Debug-only — captured in LangSmith and logged at INFO."
        ),
    )
    options: list[str] = Field(default_factory=list, max_length=20)


class DropdownAgent(Agent[_ExtractedOptions]):
    """Extract up to 20 single-column dropdown options from fetched source material for a USER_INPUT-stage field.

    Returns the full `_ExtractedOptions` so callers can read both the
    options and the completeness self-assessment. Returns an empty
    `_ExtractedOptions` (no options, completeness=`unknown`) on None /
    exception so the pipeline never breaks.
    """

    output_type = _ExtractedOptions
    max_tokens = 2000
    tags = ["core", "agent", "user_input"]
    cost_kind = "dropdown"

    @classmethod
    async def run(
        cls,
        variable_name: str,
        params: DropdownParams,
        fetched: FetchedContext,
    ) -> _ExtractedOptions:
        """Return the LLM's structured output (options + completeness signal).

        On None / exception: returns an empty `_ExtractedOptions` with
        `completeness="unknown"` so the caller's vision-fallback gate
        treats the failure as "couldn't judge → fire vision if possible".
        """
        prompt = _EXTRACTION_PROMPT.format(
            variable_name=variable_name,
            label=params.label,
            example_block=_format_example_block(params),
            source_material=repr(fetched.raw_result),
        )
        try:
            result = await cls._invoke(
                prompt,
                run_name="DropdownExtractor",
                metadata={"variable": variable_name},
            )
            if result is None:
                return _ExtractedOptions()
            cls._log_completeness(variable_name, result)
            return result
        except Exception as e:
            logger.error(f"Dropdown extraction failed for '{variable_name}': {e}")
            return _ExtractedOptions()

    @classmethod
    def _log_completeness(
        cls,
        variable_name: str,
        result: _ExtractedOptions,
    ) -> None:
        """Echo the completeness self-assessment into app logs at INFO.

        LangSmith already captures the structured output; this surfaces
        the same data in our terminal / log aggregator so authors can
        diagnose under-extraction without leaving the deploy logs.
        """
        logger.info(
            "DropdownAgent[%s] completeness=%s reasoning=%s options=%d",
            variable_name,
            result.completeness,
            result.completeness_reasoning or "<none>",
            len(result.options),
        )
