"""Public surface of the TemplateAgent — re-exports the agent class, its merge-instruction input type, and its structured-output schema."""

from .agent import MergeInstruction, TemplateAgent, TemplateAgentOutput

__all__ = ["MergeInstruction", "TemplateAgent", "TemplateAgentOutput"]
