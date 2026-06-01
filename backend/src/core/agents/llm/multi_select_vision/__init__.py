"""Public surface of the MultiSelectVisionAgent — re-exports the agent and structured-output schema."""

from .agent import (
    MultiSelectVisionAgent,
    VisionExtractionResult,
    _ExtractedMultiSelectOptions,
)

__all__ = [
    "MultiSelectVisionAgent",
    "VisionExtractionResult",
    "_ExtractedMultiSelectOptions",
]
