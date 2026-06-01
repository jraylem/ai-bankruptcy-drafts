"""Public surface of the CaseIngestionAgent — re-exports the agent class and its structured-output schema."""

from .agent import CaseIngestionAgent, CaseMetadata

__all__ = ["CaseIngestionAgent", "CaseMetadata"]
