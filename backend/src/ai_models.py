# AI Model Configuration
# Change model names here to apply across the entire project.

# ─── Provider ────────────────────────────────────────────────────────────────
MODEL_PROVIDER = "openai"

# ─── Standard — Agents / Field Extraction ────────────────────────────────────
# Used for: init_chat_model agents in chatbot/agent.py, gmail/agent.py, routes/service_stream.py
# Previous Models
# MODEL_STANDARD = "gpt-4o-mini"
# MODEL_STANDARD = "gpt-5-mini"
# Current Model
MODEL_STANDARD = "gpt-4.1-mini"

# ─── Enhance — Direct OpenAI Client Calls ────────────────────────────────────
# Used for: AI text enhancement in motion_filling/* and chatbot streaming reviews
# Previous Models
# MODEL_ENHANCE = "gpt-3.5-turbo"
# Current Model
MODEL_ENHANCE = "gpt-4o-mini"

# ─── Advanced — Complex Reasoning ────────────────────────────────────────────
# Used for: trustees_reason field (gmail/agent.py - GmailMotionExtendAgent only)
# Previous Models
# MODEL_ADVANCED = "gpt-5.4"
# Current Model
MODEL_ADVANCED = "gpt-5.4-mini"

# ─── Temperature (GPT-4 models only) ────────────────────────────────────────────
# TEMPERATURE_EXTRACTION = 0    → fully deterministic (gmail/agent.py field extraction)
# TEMPERATURE_AGENTS     = 0.3  → standard agents, chatbot, service_stream, fill_motion_delay
# TEMPERATURE_ENHANCE    = 0.7  → creative text enhancement (motion_filling AI functions)
TEMPERATURE_EXTRACTION = 0
TEMPERATURE_AGENTS = 0.3
TEMPERATURE_ENHANCE = 0.7

# ─── Reasoning Effort ────────────────────────────────────────────────────────
# Only for GPT-5 models (MODEL_ADVANCED) — GPT-5 does not support temperature.
# "low"  = fast, direct, deterministic (best for field extraction)
# "medium" = balanced
# "high" = deep reasoning (best for complex analysis)
REASONING_EFFORT = "low"

# ─── Claude (Anthropic) ──────────────────────────────────────────────────────
# Used for: direct structured extraction calls (no ReAct agent, no vectorstore)
# e.g. subject-filtered Gmail email → single Haiku call → JSON fields
CLAUDE_PROVIDER = "anthropic"
#CLAUDE_MODEL_FAST = "claude-haiku-4-5-20251001"   # fast + cheap, field extraction
CLAUDE_MODEL_FAST = "claude-sonnet-4-6"            
CLAUDE_MODEL_STANDARD = "claude-sonnet-4-6"        # balanced, moderate reasoning
CLAUDE_MODEL_ADVANCED = "claude-opus-4-6"          # deep reasoning, complex tasks
CLAUDE_TEMPERATURE = 0                             # deterministic for extraction
CLAUDE_MAX_TOKENS_CHAT = 16384                     # longer regular chat replies

# ─── Claude Built-in Tools ───────────────────────────────────────────────────
# Versioned tool names — update here when Anthropic releases a newer version.
# Used for: _get_us_prime_rate (gmail/service.py)
CLAUDE_TOOL_WEB_SEARCH = "web_search_20250305"

# ─── Embeddings ──────────────────────────────────────────────────────────────
# Used for: vector store (RAG / chatbot document search)
MODEL_EMBEDDINGS = "text-embedding-3-small"
