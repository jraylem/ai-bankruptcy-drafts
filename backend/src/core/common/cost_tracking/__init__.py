"""Cost tracking for LLM and embedding calls under src/core/.

Every Claude / OpenAI call writes one row to `llm_cost_logs` via the
`CostTrackingCallback` (LangChain `AsyncCallbackHandler`) attached at
each agent's edge. Pricing constants live in `pricing.py`; the
`CostContext` dataclass carries firm/case/user attribution through
the call.
"""

from .context import (
    CostContext,
    SemanticIdKind,
    build_cost_context_for_agent,
    cost_attribution,
    get_current_attribution,
)
from .handler import CostTrackingCallback
from .pricing import (
    PRICES_PER_TOKEN,
    compute_cost_usd,
    normalize_model_name,
)

__all__ = [
    "CostContext",
    "CostTrackingCallback",
    "PRICES_PER_TOKEN",
    "SemanticIdKind",
    "build_cost_context_for_agent",
    "compute_cost_usd",
    "cost_attribution",
    "get_current_attribution",
    "normalize_model_name",
]
