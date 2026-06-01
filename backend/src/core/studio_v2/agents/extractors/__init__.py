"""LLM extractor agents for v2.

The four agents in this package handle every (gmail / case_file) × (raw
/ dropdown / chip / multi_select) combination from the wizard's
source-shape matrix. They all share:

- The SAME toolset (gmail_search, case_vector_query, vision_fallback —
  built per-resolution by the orchestrator from `StudioV2ToolContext`).
- The SAME tool loop (Anthropic tool-use with a final `submit_*`
  structured-output tool the agent calls to finalize).
- The SAME failure policy (degrade to an empty-value
  `ResolvedTemplateValueV2` with `confidence="low" | "none"` and a
  diagnostic `note` — never raise into the pipeline).

The agents DIFFER in their `submit_*` tool's schema (the shape of
their structured output) and their prompt framing. See `base.py` for
the loop, `draft.py` / `dropdown.py` / `reco_chips.py` /
`multi_select.py` for the per-shape specializations.

NOT a separate "fetcher" agent: every extractor decides autonomously
whether / when to escalate from `case_vector_query` to
`vision_fallback`, or to issue multiple `gmail_search` calls with
refined queries. v1's `CaseVectorVisionResolver` post-processor pass
is folded into the autonomous loop.
"""

from .base import ExtractorAgentV2, ExtractorRunResult
from .draft import DraftAgentV2
from .dropdown import DropdownAgentV2
from .multi_select import MultiSelectAgentV2
from .reco_chips import RecoChipsAgentV2

__all__ = [
    "DraftAgentV2",
    "DropdownAgentV2",
    "ExtractorAgentV2",
    "ExtractorRunResult",
    "MultiSelectAgentV2",
    "RecoChipsAgentV2",
]
