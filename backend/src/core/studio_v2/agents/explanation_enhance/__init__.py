"""ExplanationEnhanceAgentV2 — multimodal polish for the
`author_input` × `with_docs` resume path.

Receives the paralegal's free-text explanation plus a set of
pre-parsed supporting documents (`SupportingDoc` variants from
v1's `supporting_doc_reader` helper, imported read-only) and
produces one compact, legally-worded paragraph that:

  - Preserves every fact the user asserted.
  - Corroborates / sharpens specific claims using the attached docs.
  - Never fabricates facts absent from BOTH the user text and the docs.

Mirrors v1's `ExplanationEnhanceAgent` 1:1 behaviorally; brand-new
class in the v2 namespace (no v1 class import — reuses only the
v1 SupportingDoc reader as a pure utility).

Used inside `orchestration.picks.expand_picks_v2` for
`SupportingDocsPickV2`. Error policy: returns the user's raw text
unchanged on None / exception / empty output — enhancement is a
quality improvement, never a hard dependency.
"""

from .agent import ExplanationEnhanceAgentV2

__all__ = ["ExplanationEnhanceAgentV2"]
