"""Core-owned constants (Claude model names, etc.).

Core-owned so agents inside src/core/agents/ never reach outside the boundary
to pick the model for an LLM call. Values mirror the defaults from
src/ai_models.py; the canonical copy lives here.
"""

CLAUDE_MODEL_STANDARD = "claude-sonnet-4-6"
CLAUDE_MODEL_ADVANCED = "claude-opus-4-6"
# Document/vision-capable model used by the case_vector vision-fallback agent
# to re-extract low-confidence values directly from the petition PDF.
CLAUDE_MODEL_VISION = "claude-opus-4-6"
# Lightweight model for fast classification / pre-screen calls (e.g. the
# chat guardrail's jailbreak / off-topic check). Anthropic recommends a
# Haiku-tier model for safety pre-screens: cheap, low-latency, and good
# enough at structured-output classification.
CLAUDE_MODEL_LIGHT = "claude-haiku-4-5-20251001"
