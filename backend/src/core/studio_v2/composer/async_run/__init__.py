"""Async orchestration shell around `studio_v2.services.composer`.

Mirrors v1's `src/core/components/pleading/` pattern 1:1 — Redis-backed
state + per-user SSE event stream + Taskiq workers on the shared
`core_broker`. The actual composer work (`generate_template_v2`,
`regenerate_template_v2`) is NOT reimplemented; this layer just wraps
the existing service-layer functions in a fire-and-forget pipeline so
the HTTP request returns immediately with a `task_id` and the FE
subscribes to the SSE stream for status events.

Solves the production 504 problem — LLM-heavy composer work
(TemplateAgentV2 typically 30s-2min) used to run synchronously in the
request/response cycle, hitting Cloudflare/Railway edge timeouts.
Async-via-Taskiq sidesteps every layer's HTTP timeout because the
POST returns a task_id immediately.
"""
