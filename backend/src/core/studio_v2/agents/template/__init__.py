"""TemplateAgentV2 — composer-time variable extraction agent.

Public surface: re-exports the agent class + its merge-instruction
input type + its structured-output schema. Mirrors v1's
`src/core/agents/llm/template/__init__.py` pattern.
"""

from .agent import MergeInstructionV2, TemplateAgentV2, TemplateAgentV2Output
from .schemas import TemplateFieldV2Extract

__all__ = [
    "MergeInstructionV2",
    "TemplateAgentV2",
    "TemplateAgentV2Output",
    "TemplateFieldV2Extract",
]
