"""Per-call attribution context for cost tracking.

`CostContext` is constructed at each agent's call site (where firm /
case / user are already known) and threaded through to the callback
handler. We use a `@dataclass(frozen=True)` so it's hashable + safe to
pass through RunnableConfig.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Literal, Optional

# Typed discriminator for the polymorphic `semantic_id` column on
# llm_cost_logs. Each value names the parent entity an LLM call belongs to.
SemanticIdKind = Literal["case_session", "pleading_run", "case", "template"]


@dataclass(frozen=True)
class CostContext:
    """Identifies a single LLM (or embedding) call for cost attribution.

    `kind` is the only required field — it determines the rollup bucket
    in the dashboard. The rest are optional; null values map to NULL in
    `llm_cost_logs` and to absent keys in `log_metadata` JSONB.

    `semantic_id` + `semantic_id_kind` give a typed (polymorphic) linkage
    from the cost row to the parent entity the call belongs to:
      - case_session  : CaseSession.id (chat surface)
      - pleading_run  : taskiq draft task_id (one Generate-button click)
      - case          : Case.id (manual upload / direct case-scoped calls)
      - template      : DraftTemplate.id (template authoring / regenerate)

    Kind taxonomy (the LLM-call type, separate from semantic_id_kind):
      - "chat"               — CaseChatAgent main turn (incl. chat tool call)
      - "chat_guardrail"     — Haiku pre-screen on every chat turn
      - "draft"              — DraftAgent
      - "template"           — TemplateAgent (compose + regenerate)
      - "case_ingest"        — CaseIngestionAgent (PDF vision parse)
      - "embeddings"         — OpenAIEmbeddings (per index batch)
      - "auto_derive"        — AutoDeriveAgent
      - "dropdown"           — DropdownAgent / GroupDropdownAgent
      - "reco_chips"         — RecoChipsAgent
      - "user_input_heal"    — UserInputHealAgent
      - "explanation_enhance" — ExplanationEnhanceAgent
      - "extract_from_draft" — ExtractFromDraftAgent
      - "case_vector_vision" — CaseVectorVisionAgent
      - "multi_select_vision" — MultiSelectVisionAgent
      - "web_search_enhance" — WebSearchEnhanceAgent
    """
    kind: str
    firm_id: Optional[str] = None
    case_id: Optional[str] = None
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    semantic_id: Optional[str] = None
    semantic_id_kind: Optional[SemanticIdKind] = None
    agent_name: Optional[str] = None
    extra_metadata: dict = field(default_factory=dict)

    def to_metadata(self) -> dict:
        """Render the non-firm-id-non-kind fields as JSONB-friendly metadata."""
        out: dict = {}
        if self.case_id:
            out["case_id"] = self.case_id
        if self.user_id:
            out["user_id"] = self.user_id
        if self.session_id:
            out["session_id"] = self.session_id
        if self.agent_name:
            out["agent_name"] = self.agent_name
        if self.extra_metadata:
            out.update(self.extra_metadata)
        return out


# ─── Attribution contextvar ─────────────────────────────────────────
# Entry points (chat service, draft worker, case ingest, template
# composer) set firm/case/user attribution ONCE for their request scope;
# every nested LLM call picks it up automatically without thread-through
# plumbing at each agent's run() signature.

@dataclass(frozen=True)
class _Attribution:
    firm_id: Optional[str] = None
    case_id: Optional[str] = None
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    semantic_id: Optional[str] = None
    semantic_id_kind: Optional[SemanticIdKind] = None


_attribution_var: ContextVar[Optional[_Attribution]] = ContextVar(
    "cost_attribution", default=None,
)


class cost_attribution:
    """Context manager: scope firm/case/user attribution + semantic linkage to a block.

    Usage:
        with cost_attribution(
            firm_id="firm-1", case_id="26_10700",
            semantic_id_kind="pleading_run", semantic_id=task_id,
        ):
            await DraftAgent.run(...)  # logs cost with that attribution

    Nested usage merges — inner values override outer ones for the
    keys they set. None-valued kwargs inherit from the outer scope.

    `semantic_id` + `semantic_id_kind` should be set together: passing
    one without the other emits a WARNING log (the wiring is almost
    certainly a bug; callers should fix it).
    """

    def __init__(
        self,
        *,
        firm_id: Optional[str] = None,
        case_id: Optional[str] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        semantic_id: Optional[str] = None,
        semantic_id_kind: Optional[SemanticIdKind] = None,
    ) -> None:
        outer = _attribution_var.get()
        # Warn on inconsistent semantic_id pairing — this catches wiring bugs at
        # the scope-open site, before any cost rows are written with a half-set linkage.
        if (semantic_id is None) != (semantic_id_kind is None):
            import logging
            logging.getLogger(__name__).warning(
                "cost_attribution: semantic_id and semantic_id_kind must be set together "
                "(got semantic_id=%r, semantic_id_kind=%r)", semantic_id, semantic_id_kind,
            )
        self._attribution = _Attribution(
            firm_id=firm_id if firm_id is not None else (outer.firm_id if outer else None),
            case_id=case_id if case_id is not None else (outer.case_id if outer else None),
            user_id=user_id if user_id is not None else (outer.user_id if outer else None),
            session_id=session_id if session_id is not None else (outer.session_id if outer else None),
            semantic_id=semantic_id if semantic_id is not None else (outer.semantic_id if outer else None),
            semantic_id_kind=semantic_id_kind if semantic_id_kind is not None else (outer.semantic_id_kind if outer else None),
        )
        self._token = None

    def __enter__(self) -> "cost_attribution":
        self._token = _attribution_var.set(self._attribution)
        return self

    def __exit__(self, *args) -> None:
        if self._token is not None:
            _attribution_var.reset(self._token)


def get_current_attribution() -> _Attribution:
    """Read the current attribution context. Returns an empty
    `_Attribution()` (all-None) when no scope is active so callers can
    always read fields without `if None` guards."""
    return _attribution_var.get() or _Attribution()


def build_cost_context_for_agent(
    *,
    kind: str,
    agent_name: Optional[str] = None,
    extra_metadata: Optional[dict] = None,
) -> CostContext:
    """Combine the current attribution scope with an agent's kind into
    a CostContext ready to hand to a CostTrackingCallback. Always
    returns a context (never None) — agents that don't want logging
    just skip calling this."""
    attr = get_current_attribution()
    return CostContext(
        kind=kind,
        firm_id=attr.firm_id,
        case_id=attr.case_id,
        user_id=attr.user_id,
        session_id=attr.session_id,
        semantic_id=attr.semantic_id,
        semantic_id_kind=attr.semantic_id_kind,
        agent_name=agent_name,
        extra_metadata=extra_metadata or {},
    )
