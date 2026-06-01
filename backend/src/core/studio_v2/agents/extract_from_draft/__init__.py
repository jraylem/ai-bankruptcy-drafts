"""ExtractFromDraftAgentV2 — pulls one fragment from a parent's
filled docx text per the author's `extract_instruction`.

Used by `inherit_from_parent_v2.resolve` when a companion's slot
configuration is `extract_from_draft` (kind = "From the document" in
the FE Companions modal). Replaces slice A's placeholder path with a
live LLM extraction.

Mirrors v1's `ExtractFromDraftAgent` 1:1 — brand-new class in the v2
namespace (no v1 import). Error policy: returns "" on None /
exception, the resolver then surfaces it as the slot's
`parent_bundle_fallback` (or empty + warning).
"""

from .agent import ExtractFromDraftAgentV2

__all__ = ["ExtractFromDraftAgentV2"]
