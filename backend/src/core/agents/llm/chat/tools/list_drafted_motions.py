"""`list_drafted_motions` chat tool — cross-user drafting history.

Surfaces every draft attempt for the current case across ALL firm users
so a paralegal in any session can answer "has anyone drafted X" without
duplicating work. Backed by
`CaseGenerationLogRepository.list_for_case_all_users(case_id, limit)`.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, ClassVar, Optional

from pydantic import BaseModel, Field

from src.core.common.storage.database import CaseGenerationLogRepository

from .base import BaseChatTool, ToolContext
from .registry import register_tool

logger = logging.getLogger(__name__)

# Truncate the error field so a multi-kilobyte stack trace doesn't
# blow the LLM context budget on a failed-log row.
_ERROR_MAX_CHARS = 200


class ListDraftedMotionsInput(BaseModel):
    """Args the model passes to `list_drafted_motions`."""
    status_filter: Optional[str] = Field(
        default=None,
        description=(
            "Optional status to narrow results — e.g. \"COMPLETED\" when "
            "counsel only cares about finished drafts. Case-insensitive. "
            "Omit to see every state (PENDING, DRAFTING, COMPLETED, "
            "FAILED, CANCELLED, etc.) which is useful for \"has anyone "
            "STARTED X\" questions."
        ),
    )
    limit: int = Field(
        default=50,
        ge=1,
        le=200,
        description="Maximum number of log rows to return (most-recent-first).",
    )


@register_tool
class ListDraftedMotionsTool(BaseChatTool):
    """Cross-user drafting history for the current case."""

    name: ClassVar[str] = "list_drafted_motions"
    description: ClassVar[str] = (
        "List motions and pleadings already drafted on this case, across "
        "ALL firm users (drafting is collaborative across the firm — a "
        "draft started by one paralegal is visible to every paralegal). "
        "Use this whenever counsel asks about drafting history: \"has "
        "anyone drafted X\", \"what motions have been done\", \"what's "
        "the drafting history here\", or to avoid double-drafting before "
        "starting new work. Returns the N most-recent log rows sorted "
        "most-recent-first. When summarizing results to counsel, refer "
        "to other drafters generically (\"a colleague\", \"another "
        "paralegal\") rather than by user_id — do NOT surface raw "
        "user_ids in your reply."
    )
    input_schema: ClassVar[type[BaseModel]] = ListDraftedMotionsInput

    @classmethod
    async def invoke(cls, ctx: ToolContext, **kwargs: Any) -> dict:
        args = ListDraftedMotionsInput(**kwargs)
        try:
            rows = await CaseGenerationLogRepository.list_for_case_all_users(
                case_id=ctx.case.id, limit=args.limit,
            )
        except Exception as e:
            logger.exception(
                "list_drafted_motions failed for case=%s: %s", ctx.case.id, e,
            )
            return {"logs": [], "total": 0, "error": str(e)}

        if args.status_filter:
            needle = args.status_filter.strip().upper()
            rows = [r for r in rows if (r.status or "").upper() == needle]

        logs = [cls._summarize(r) for r in rows]
        return {
            "logs": logs,
            "total": len(logs),
            "status_filter": args.status_filter,
        }

    @staticmethod
    def _summarize(row: Any) -> dict:
        error = row.error or None
        if error and len(error) > _ERROR_MAX_CHARS:
            error = error[:_ERROR_MAX_CHARS] + "…"
        return {
            "log_id": row.id,
            "template_id": row.draft_template_id,
            "template_name": row.template_name or "",
            "status": row.status,
            "created_at": _iso(row.created_at),
            "updated_at": _iso(row.updated_at),
            "task_id": row.task_id,
            "error": error,
            "has_document": bool(getattr(row, "r2_object_key", None)),
            "user_id": row.user_id,
        }


def _iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)
