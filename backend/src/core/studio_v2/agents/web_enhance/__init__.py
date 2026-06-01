"""WebEnhanceAgentV2 — post-resolution web-search enhancement.

Universal optional finalizer step: any resolved value (regardless of
source) whose field has a non-empty `web_enhance_instruction` is run
through Claude with the native server-side `web_search_20250305` tool
enabled. The agent uses the resolved value as an anchor, searches the
open web per the author's instruction, and returns a reshaped value
that drops into the template placeholder.

Mirrors v1's `WebSearchEnhanceAgent` behaviorally; brand-new class in
the v2 namespace (no v1 import). v1's resolver was case_vector / Gmail
only — v2 makes web enhancement orthogonal to source (works on
derived_from_variable + author_input + constants too, as long as the
author opted in with an instruction).

Soft-failure contract: on LLM error / no `<answer>` tag / empty
response, returns the original resolved value unchanged. Enhancement
is a quality improvement, never a hard dependency.
"""

from .agent import WebEnhanceAgentV2

__all__ = ["WebEnhanceAgentV2"]
