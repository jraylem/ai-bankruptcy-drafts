"""Async orchestration shell around `studio_v2.services.dry_run`.

Mirrors `src/core/studio_v2/composer/async_run/` 1:1 — Redis-backed
state + per-user SSE event stream + Taskiq workers on the shared
`core_broker`. The actual dry-run work (`execute_dry_run_v2`,
`resume_dry_run_v2`) is NOT reimplemented; this layer just wraps the
existing service-layer functions so the HTTP request returns
immediately with a `task_id` and the FE subscribes to the SSE stream
for status events.

Solves the same class of problem composer-async solves:
LLM-heavy work (Wave-A/B extractors typically 15s-2min) used to run
synchronously in the request/response cycle, hitting Cloudflare /
Railway edge timeouts. Async-via-Taskiq sidesteps every layer's
HTTP timeout because the POST returns a task_id immediately.

Dry-run-specific deltas from composer-async:
- **Pause/resume.** Initial may hit AWAITING_INPUT and stop; a second
  POST (/{task_id}/submit-input) resumes with the paralegal's picks.
- **Heavier persisted state.** Records carry `template_spec`,
  `resolved_values`, `pending_inputs`, `user_picks` across the pause
  boundary so the worker can resume without the FE re-sending.
- **Lower concurrency caps** (5 / 20 vs composer's 10 / 50) — dry-runs
  are diagnostic; beyond ~5 in flight a paralegal can't track them.
- **No persisted artifacts.** Composer produces a `templates_v2` row;
  dry-run produces an R2 docx only. The task record IS the result
  store (Redis TTL'd).
"""
