"""
Auto-derive LLM agent.

Runs as part of AutoDerivedResolver during finalize_run. For each
AUTO_DERIVED_FROM_VARIABLE template field, this agent receives the
parent's already-resolved value plus the derived field's marker + context
(extracted at template-generation time from the source document) and
returns the substring/portion that should fill the derived placeholder.

Example: parent variable `ecf_number_document_description` resolves to
"3, being a Certification of Budget and Credit Counseling Course by Debtor".
The auto-derived title variable wants only "3" — agent extracts and returns
that fragment.

Error policy: returns "" on None/exception. The resolver treats empty as
"no derivation" — the placeholder stays unfilled, surfacing as an
unresolved-warning rather than crashing the pipeline.
"""

import logging

from pydantic import BaseModel, Field

from ..base import Agent
from .prompt_builder import _DERIVE_PROMPT

logger = logging.getLogger(__name__)


class _DerivedValue(BaseModel):
    """Structured-output target for the auto-derive LLM call."""
    value: str = Field(
        default="",
        description="The derived value extracted from the parent's resolved value",
    )


class AutoDeriveAgent(Agent[_DerivedValue]):
    """Extract a derived substring from a parent template variable's resolved value at fill time."""

    output_type = _DerivedValue
    max_tokens = 500
    tags = ["core", "agent", "auto_derived"]
    cost_kind = "auto_derive"

    @classmethod
    async def run(
        cls,
        parent_variable: str,
        parent_value: str,
        derived_marker: str,
        derived_context: str,
    ) -> str:
        """Return the derived fragment, or "" on any failure."""
        prompt = _DERIVE_PROMPT.format(
            parent_variable=parent_variable,
            parent_value=parent_value,
            derived_marker=derived_marker,
            derived_context=derived_context,
        )
        try:
            result = await cls._invoke(
                prompt,
                run_name="AutoDerive",
                metadata={"parent_variable": parent_variable},
            )
        except Exception as e:
            logger.warning(
                f"AutoDeriveAgent failed for parent '{parent_variable}': {e}; "
                "returning empty derived value"
            )
            return ""

        if result is None or not result.value:
            return ""
        return result.value.strip()
