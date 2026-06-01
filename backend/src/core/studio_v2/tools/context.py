"""Per-resolution scope passed into every tool constructor.

Invariant: **agents never see plumbing.** No tool input schema
includes `case_id`, `petition_pdf_url`, `case_file_collection`,
`attachment_id`, OAuth credentials, or any other routing/identity
field. Tools accept ONLY the natural-language inputs the LLM actually
needs to reason about (`query`, `question`, `top_k`, etc.). Everything
else is bound at tool construction time via `StudioV2ToolContext`.

Mirrors v1's chat-tool pattern from
`src/core/agents/llm/chat/tools/base.py` (ToolContext) — same
binding philosophy, separate namespace + separate dataclass so v2
can evolve its tool list without touching v1.

Lifecycle (orchestration calls this once per dry-run / draft):

    case = await case_repo.get(case_id)
    ctx = StudioV2ToolContext(
        case=case,
        firm_oauth=load_firm_oauth_credentials(),
    )
    toolset = [
        build_gmail_search_tool(ctx),         # binds ctx.firm_oauth
        build_case_vector_query_tool(ctx),    # binds ctx.case.case_file_collection
        build_vision_fallback_tool(ctx),      # binds ctx.case.petition_pdf_url
        SubmitOptions, SubmitValue, SubmitChips,
    ]

Every extractor agent for this resolution gets the SAME toolset.
Per-(source, shape) dispatch only picks WHICH agent class runs, not
which tools it sees.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class StudioV2ToolContext:
    """Immutable per-resolution scope.

    Constructed once at the top of `run_initial_stages_v2` /
    `run_resume_stages_v2` for a given (template_id, case_id, firm)
    triple, passed into every tool constructor, and treated as
    immutable for the lifetime of that resolution.

    `case` is the SQLAlchemy `Case` ORM row (or a Pydantic
    representation of it) — carries `case_number`, `case_name`,
    `petition_pdf_url`, `case_file_collection`, etc. Typed as `Any`
    to avoid the v2 namespace importing the v1 ORM directly; the
    consuming tools access fields on the object they receive.

    `firm_oauth` is the `google.oauth2.credentials.Credentials` object
    the firm uses to talk to Gmail. Reuses v1's `token.json` loader
    via `tools/gmail_search.py:load_firm_gmail_credentials`.

    Extend this dataclass when adding new tools that need bound scopes
    (e.g. court_drive_creds, e_signature_session) — never plumb
    routing data through tool input schemas.
    """

    case: Any
    firm_oauth: Any | None = None
