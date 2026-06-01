"""DeriveAgent — produces the resolved value of a
`derived_from_variable` field by applying the author's
`extraction_prompt` to the parent variable's value.

NO tools (no Gmail / case_vector / vision lookups). The parent's
value is the SOLE input — that's the whole point of derivation: the
author already declared what to extract from, the LLM just shapes
the output per the instruction.

`run()` accepts the parent's `raw_context` and `value` separately and
picks `raw_context` first when non-empty. That's the load-bearing
path for derived children of dropdown / chip / multi-select picks:
the child sees the full source slice (email body chunk, case-file
pgvector chunk, vehicle paragraph) instead of just the truncated
display label.

Reuses v1's `Agent` base class for structured-output + cost
attribution wiring. v1 base class is import-only — never modified.
"""

from __future__ import annotations

import logging
from typing import ClassVar

from pydantic import BaseModel

from src.core.studio_v2.agents._v1_base import StudioV2Agent
from src.core.common.constants import CLAUDE_MODEL_ADVANCED

from ...types.resolution import ResolvedTemplateValueV2
from .prompt_builder import build_derive_prompt

logger = logging.getLogger(__name__)


class _DerivedValue(BaseModel):
    """Structured-output target. Single `value` field — the derived
    string, ready to substitute into the rendered docx."""

    value: str


class DeriveAgent(StudioV2Agent[_DerivedValue]):
    """Prompt-based derivation for v2 `derived_from_variable` fields.

    Replaces the v1 `AutoDeriveAgent` + `rule_effect` enum. There is
    no longer a "fast path" for substring extraction or
    pluralization — every derivation is one LLM call. The author's
    natural-language `extraction_prompt` is the binding contract.
    """

    output_type: ClassVar[type[BaseModel]] = _DerivedValue
    model: ClassVar[str] = CLAUDE_MODEL_ADVANCED
    max_tokens: ClassVar[int] = 1000
    tags: ClassVar[list[str]] = ["core", "agent", "studio_v2", "derive"]
    cost_kind: ClassVar[str] = "derive_v2"

    @classmethod
    async def run(
        cls,
        *,
        child_variable: str,
        parent_variable: str,
        parent_raw_context: str = "",
        parent_value: str = "",
        extraction_prompt: str,
        output_expectation: str | None = None,
    ) -> ResolvedTemplateValueV2:
        """Derive `child_variable`'s value from `parent_variable`'s
        value per the author's `extraction_prompt`.

        Returns a `ResolvedTemplateValueV2` ready to add to
        `resolved_by_name`. On failure (empty inputs, LLM error,
        empty output), returns a row with `value=""`, `confidence="low"`,
        and a `note` describing the cause. Never raises into the
        pipeline.

        Args:
            child_variable: Name of the variable being derived.
            parent_variable: Name of the parent variable (for prompt
                framing and the resolved row's debug trace).
            parent_raw_context: Source slice the parent was extracted
                from (preferred over `parent_value` when non-empty).
            parent_value: Parent's resolved display string (fallback
                when no raw_context is available).
            extraction_prompt: Author's binding derivation instruction.
            output_expectation: Optional shape hint for the final
                string.
        """
        # Prefer raw_context (full source slice) over the display value
        # — that's the whole reason raw_context exists.
        effective_parent_value = (parent_raw_context or "").strip() or (
            parent_value or ""
        ).strip()

        if not effective_parent_value:
            return ResolvedTemplateValueV2(
                template_variable=child_variable,
                value="",
                confidence="none",
                note=(
                    f"DeriveAgent: parent '{parent_variable}' has no value "
                    f"(neither raw_context nor display) — cannot derive."
                ),
            )

        if not (extraction_prompt and extraction_prompt.strip()):
            return ResolvedTemplateValueV2(
                template_variable=child_variable,
                value="",
                confidence="none",
                note=(
                    f"DeriveAgent: no extraction_prompt supplied for "
                    f"'{child_variable}' — cannot derive."
                ),
            )

        prompt = build_derive_prompt(
            child_variable=child_variable,
            parent_variable=parent_variable,
            parent_value=effective_parent_value,
            extraction_prompt=extraction_prompt,
            output_expectation=output_expectation,
        )

        try:
            result = await cls._invoke(
                prompt,
                run_name=f"DeriveAgent:{child_variable}",
                metadata={
                    "child_variable": child_variable,
                    "parent_variable": parent_variable,
                    "has_raw_context": str(bool(parent_raw_context)),
                },
            )
        except Exception as err:  # noqa: BLE001
            logger.warning(
                "DeriveAgent: LLM call failed for %s ← %s (%s)",
                child_variable, parent_variable, err,
            )
            return ResolvedTemplateValueV2(
                template_variable=child_variable,
                value="",
                confidence="none",
                note=f"DeriveAgent: LLM call failed ({err})",
            )

        if result is None:
            return ResolvedTemplateValueV2(
                template_variable=child_variable,
                value="",
                confidence="low",
                note="DeriveAgent: LLM returned no structured output.",
            )

        return ResolvedTemplateValueV2(
            template_variable=child_variable,
            value=(result.value or "").strip(),
            # DeriveAgent is a single-shot LLM call with no source slice
            # to forward — empty raw_context is fine, downstream
            # derivations (chains of derives) fall back to `value`.
            raw_context="",
            confidence="high" if (result.value or "").strip() else "low",
            note="" if (result.value or "").strip()
            else "DeriveAgent: LLM returned empty string.",
        )
