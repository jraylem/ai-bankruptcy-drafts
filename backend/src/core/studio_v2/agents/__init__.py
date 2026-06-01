"""Studio V2 LLM agents (LLM-call sites only).

Subpackages:
- `template/` — `TemplateAgentV2` (composer-time variable extraction).
- `extractors/` — `DraftAgentV2`, `DropdownAgentV2`, `RecoChipsAgentV2`,
  `MultiSelectAgentV2` + shared tool-loop base.
- `derive/` — `DeriveAgent` (prompt-based derivation, no tools).
- `extract_from_draft/` — `ExtractFromDraftAgentV2` (slot fill from
  parent's filled docx).
- `heal/` — `UserInputHealAgentV2` (post-pick prose shaper).

Deterministic resolvers (no LLM call) live under
`studio_v2/resolvers/` — `DateHealingResolverV2` is there too because
it's a regex normalizer, not an LLM agent.
"""

from .template import (
    MergeInstructionV2,
    TemplateAgentV2,
    TemplateAgentV2Output,
    TemplateFieldV2Extract,
)

__all__ = [
    "MergeInstructionV2",
    "TemplateAgentV2",
    "TemplateAgentV2Output",
    "TemplateFieldV2Extract",
]
