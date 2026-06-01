"""Public surface of the RecoChipsAgent — re-exports the agent class, param union, and structured-output schema."""

from .agent import RecoChipsAgent, RecoChipsParams, _ExtractedChips

__all__ = ["RecoChipsAgent", "RecoChipsParams", "_ExtractedChips"]
