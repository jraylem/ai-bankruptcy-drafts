"""Dry-run service for Studio V2.

Resolves a candidate `TemplateSpecV2` end-to-end against a real case
WITHOUT persisting anything — paralegals iterate on the wizard's
working-draft before committing via Publish (Phase 3).

Two public entry points:

    execute_dry_run_v2(...) -> DryRunResponseV2 | AwaitingInputResponseV2
    resume_dry_run_v2(...)  -> DryRunResponseV2

Server is stateless: the FE re-sends `template_spec` + `resolved_values`
+ `pending_inputs` + `user_picks` on every resume call. No session
table, no Redis row, no run_id-keyed lookup.

Cost attribution: wraps every call in
`cost_attribution(semantic_id_kind="pleading_run_v2")` so v2 dry-run
spend lands in its own bucket in the Costs dashboard (distinct from
v1's `pleading_run`).
"""

from .service import execute_dry_run_v2, resume_dry_run_v2

__all__ = ["execute_dry_run_v2", "resume_dry_run_v2"]
