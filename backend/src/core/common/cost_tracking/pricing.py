"""Per-token USD pricing for the LLMs + embeddings called from src/core/.

Anthropic pricing source (May 2026):
  https://platform.claude.com/docs/en/about-claude/pricing
  - Haiku 4.5:  $1 in  /  $5 out  per 1M tokens
  - Sonnet 4.6: $3 in  / $15 out  per 1M tokens
  - Opus 4.6 / 4.7: $5 in / $25 out per 1M tokens
  Cache: read = 0.1× input (90% discount), write = 1.25× input.

OpenAI embeddings:
  - text-embedding-3-large: $0.13 per 1M tokens.

PR-gated updates when Anthropic / OpenAI adjust rates.
"""

from __future__ import annotations

import logging
import re
from decimal import Decimal
from typing import TypedDict

logger = logging.getLogger(__name__)


class _ModelRate(TypedDict):
    input: float
    output: float
    cache_read: float
    cache_write: float


# All values are USD per single token (e6 scale).
PRICES_PER_TOKEN: dict[str, _ModelRate] = {
    "claude-opus-4-7": {
        "input": 5.0e-6,
        "output": 25.0e-6,
        "cache_read": 0.5e-6,
        "cache_write": 6.25e-6,
    },
    "claude-opus-4-6": {
        "input": 5.0e-6,
        "output": 25.0e-6,
        "cache_read": 0.5e-6,
        "cache_write": 6.25e-6,
    },
    "claude-sonnet-4-6": {
        "input": 3.0e-6,
        "output": 15.0e-6,
        "cache_read": 0.3e-6,
        "cache_write": 3.75e-6,
    },
    "claude-haiku-4-5": {
        "input": 1.0e-6,
        "output": 5.0e-6,
        "cache_read": 0.1e-6,
        "cache_write": 1.25e-6,
    },
    "text-embedding-3-large": {
        "input": 0.13e-6,
        "output": 0.0,
        "cache_read": 0.0,
        "cache_write": 0.0,
    },
}


# Anthropic web_search server-tool flat fee: $10 per 1,000 searches.
WEB_SEARCH_FEE_USD_PER_USE: Decimal = Decimal("0.01")


# Matches a trailing date suffix like "-20251001" or "-20250715".
_DATE_SUFFIX_RE = re.compile(r"-(\d{8})$")
# Matches a trailing bracket variant like "[1m]".
_VARIANT_SUFFIX_RE = re.compile(r"\[[^\]]+\]$")


def normalize_model_name(raw: str) -> str:
    """Strip variant + date suffixes so call-site model strings hit the
    pricing table. Examples:
      - "claude-haiku-4-5-20251001"  → "claude-haiku-4-5"
      - "claude-opus-4-7[1m]"        → "claude-opus-4-7"
      - "Claude-Sonnet-4-6"           → "claude-sonnet-4-6"
    """
    if not raw:
        return ""
    name = raw.strip().lower()
    name = _VARIANT_SUFFIX_RE.sub("", name)
    name = _DATE_SUFFIX_RE.sub("", name)
    return name


def compute_cost_usd(
    *,
    model: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
) -> Decimal:
    """Multiply token counts by the model's per-token rates and return
    the total USD cost as a `Decimal`.

    Unknown model → returns `Decimal('0')` and logs a warning. We never
    raise from this path; cost-tracking must not break the LLM call.
    Negative token counts are clamped to zero defensively (some
    streaming intermediate states have produced -1 sentinels).
    """
    key = normalize_model_name(model)
    rate = PRICES_PER_TOKEN.get(key)
    if rate is None:
        logger.warning(
            "compute_cost_usd: unknown model %r (normalized=%r) — returning 0",
            model, key,
        )
        return Decimal("0")

    def _clamp(n: int) -> int:
        return n if isinstance(n, int) and n > 0 else 0

    total = (
        Decimal(str(rate["input"])) * _clamp(input_tokens)
        + Decimal(str(rate["output"])) * _clamp(output_tokens)
        + Decimal(str(rate["cache_read"])) * _clamp(cache_read_tokens)
        + Decimal(str(rate["cache_write"])) * _clamp(cache_write_tokens)
    )
    return total.quantize(Decimal("0.000001"))


def web_search_fee_usd(uses: int) -> Decimal:
    """Anthropic's hosted web_search bills a flat fee per search on top of
    the message tokens. `uses` is the count of `server_tool_use` content
    blocks in the response."""
    if not uses or uses < 0:
        return Decimal("0")
    return (WEB_SEARCH_FEE_USD_PER_USE * uses).quantize(Decimal("0.000001"))
