"""Pre-finalize resolver pipeline + post-finalize fill/upload tail.

Both the dry-run and draft flows share the same agent-orchestration shape:

    `pipeline.run_initial_stages(...)` runs the pre-pause resolver
    sequence (DraftContextService fetch + DraftAgent + DateHealing +
    SystemValue + UserInputResolver, optionally followed by Derivative).

    `pipeline.run_resume_stages(...)` runs the post-pause sequence after
    the user supplies inputs (expand_picks + Derivative).

    `finalizer.finalize_run(...)` runs the auto_derive + heal + fill +
    upload tail. The invariant "auto_derive must run before heal" is
    owned here.

This package is HTTP-agnostic — no FastAPI / Starlette imports anywhere.
The HTTP-bound consumers
(`components.engines.template.dry_run`, `components.engines.draft.service`)
are what wrap these into `/dry-run` and `/draft` endpoints.
"""

from .bundling import BundleChildRun, plan_bundle, run_bundle
from .finalizer import FinalizedRun, finalize_run
from .pipeline import (
    InitialStagesResult,
    _dedupe_last_wins,
    run_initial_stages,
    run_resume_stages,
)

__all__ = [
    "BundleChildRun",
    "FinalizedRun",
    "InitialStagesResult",
    "_dedupe_last_wins",
    "finalize_run",
    "plan_bundle",
    "run_bundle",
    "run_initial_stages",
    "run_resume_stages",
]
