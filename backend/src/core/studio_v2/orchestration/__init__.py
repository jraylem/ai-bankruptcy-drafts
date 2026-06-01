"""v2 pipeline orchestrator + finalizer.

Three public entry points the v3 dry-run + draft routers call:

    run_initial_stages_v2(spec, case, ...) -> InitialStagesResultV2
        Two-pass field resolution: deterministic + LLM extractors fire
        for wave-A fields; wave-B fields (those whose query_dependencies
        transitively reach a USER_INPUT-rooted field) defer to resume.
        Returns either `all_resolved` (no pending) or `pending_inputs`.

    run_resume_stages_v2(spec, case, resolved_values, user_picks, ...)
        -> list[ResolvedTemplateValueV2]
        Post-pause sequence: expand picks → late auto-derive → wave-B
        pass → derivative pass. Caller passes the return to finalize.

    finalize_run_v2(template_id, case, all_resolved, output_prefix, ...)
        -> FinalizedRunV2
        Heal → fill docx → upload R2 → presigned URL. Same tail for
        dry-run and draft (output_prefix discriminates).

Wave classification helper lives in `wave.py`; pick-to-resolved
expansion in `picks.py`.

NOT exported from this slice: bundling engine (slice D), persistent
drafts (Phase 3 — drafts_v2 table + Taskiq broker).
"""

from .bundling import plan_bundle_v2, run_bundle_v2
from .finalizer import finalize_run_v2
from .picks import expand_picks_v2
from .pipeline import run_initial_stages_v2, run_resume_stages_v2
from .validators import assert_part_of_packet_has_no_user_input_v2
from .wave import classify_wave_v2, root_parent_stage_v2

__all__ = [
    "assert_part_of_packet_has_no_user_input_v2",
    "classify_wave_v2",
    "expand_picks_v2",
    "finalize_run_v2",
    "plan_bundle_v2",
    "root_parent_stage_v2",
    "run_bundle_v2",
    "run_initial_stages_v2",
    "run_resume_stages_v2",
]
