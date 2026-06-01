"""Public surface of the ExplanationEnhanceAgent — re-exports the agent class and its structured-output schema."""

from .agent import ExplanationEnhanceAgent, _EnhancedExplanation

__all__ = ["ExplanationEnhanceAgent", "_EnhancedExplanation"]
