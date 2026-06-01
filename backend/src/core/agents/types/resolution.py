"""Resolver-pipeline output shapes.

Every stage of the resolver pipeline — the draft agent (LLM extraction),
the system-generated resolver, the derivative resolver, the date-healing
post-processor, and the user-input resolver — emits the same
ResolvedTemplateValue shape. ResolverStage is the enum the pipeline uses
to dispatch each TemplateField to its matching resolver.
"""

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class ResolverStage(str, Enum):
    """Pipeline stage that resolves a TemplateField, derived from its FieldSource via _STAGE_BY_SOURCE."""

    LLM_DRAFT = "llm_draft"
    SYSTEM_GENERATED = "system_generated"
    DERIVATIVE = "derivative"
    USER_INPUT = "user_input"
    AUTO_DERIVED = "auto_derived"
    INHERIT_FROM_PARENT = "inherit_from_parent"


class ResolvedTemplateValue(BaseModel):
    """A single template field resolved by any resolver stage."""
    property_name: str = Field(description="Matches TemplateField.property_name")
    value: str = Field(description="Extracted value to substitute into the template")
    reasoning: str = Field(description="Why the LLM picked this value from the raw context")
    confidence: Literal["high", "medium", "low"] = Field(
        description="How confident the LLM is in the extraction given the raw context"
    )

    @classmethod
    def low_confidence(cls, property_name: str, reasoning: str) -> "ResolvedTemplateValue":
        """Build a low-confidence resolved value with an empty string and the given reasoning."""
        return cls(property_name=property_name, value="", reasoning=reasoning, confidence="low")

    @classmethod
    def high_confidence(cls, property_name: str, value: str, reasoning: str) -> "ResolvedTemplateValue":
        """Build a high-confidence resolved value with the given value and reasoning."""
        return cls(property_name=property_name, value=value, reasoning=reasoning, confidence="high")
