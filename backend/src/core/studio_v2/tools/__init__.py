"""Shared tools every v2 extractor agent can call.

Every extractor agent (DraftAgentV2, DropdownAgentV2, RecoChipsAgentV2,
MultiSelectAgentV2) is constructed with the SAME toolset and decides
autonomously which tools to invoke based on the field's `source` kind
and on what it sees in tool results (text payload missing → escalate
to vision, etc.). No separate fetcher agents, no per-source wrappers.

Tool construction is per-resolution: the pipeline builds a
`StudioV2ToolContext` once at the top of each resolution, then
constructs every tool against it. Tools BIND their context at
construction time and accept only natural-language inputs the LLM
needs to reason about — no `case_id`, no OAuth credentials, no R2
keys ever appear in a tool input schema.

See `tools/context.py` for the invariant + the binding contract.
"""

from .context import StudioV2ToolContext

__all__ = ["StudioV2ToolContext"]
