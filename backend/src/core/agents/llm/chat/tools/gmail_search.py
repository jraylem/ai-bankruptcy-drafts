"""`gmail_search` chat tool — un-scoped Gmail inbox search.

The agent's case-aware tool is `case_emails_search`, which auto-applies
the loaded case's case-number variants to every query. `gmail_search` is
the complement: same Gmail backend, but no case scoping — for questions
that span cases (e.g. "find any email from this opposing counsel" or
"any trustee correspondence about delayed plans") or anything in the
firm inbox that isn't tied to the case currently being chatted about.
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from pydantic import BaseModel, Field

from src.core.common.services.email import EmailType
from src.core.common.toolbox import ToolBox

from .base import BaseChatTool, ToolContext
from .registry import register_tool

logger = logging.getLogger(__name__)


class GmailSearchInput(BaseModel):
    """Args the model passes to `gmail_search`."""
    body_query: str | None = Field(
        default=None,
        description=(
            "PRIMARY search field. Free-text or quoted phrase to match "
            "anywhere in the email — subject, body, AND headers. Gmail's "
            "full-text index covers all of these despite the field name. "
            "Use a single keyword (e.g. 'trustee') or a quoted phrase "
            "(e.g. 'motion to extend'). Most searches should use this "
            "field alone — it already catches subject matches."
        ),
    )
    subject_query: str | None = Field(
        default=None,
        description=(
            "Optional: restrict matching to the subject line ONLY. Use "
            "only when you specifically want to exclude body matches "
            "(rare). For typical lookups, leave this empty and put the "
            "search terms in `body_query`. Combining subject_query AND "
            "body_query means BOTH must match (AND semantics) — usually "
            "too restrictive."
        ),
    )
    max_results: int = Field(default=5, ge=1, le=20)


@register_tool
class GmailSearchTool(BaseChatTool):
    """Search the firm's Gmail inbox WITHOUT scoping to the current case."""

    name: ClassVar[str] = "gmail_search"
    description: ClassVar[str] = (
        "Search the firm's Gmail inbox without applying the current case's "
        "case-number filter. Use this for cross-case lookups: finding "
        "emails from a specific opposing counsel across all cases, looking "
        "up general firm correspondence, or any Gmail search that isn't "
        "anchored to the case currently being chatted about. For questions "
        "about THIS case's correspondence, use `case_emails_search` "
        "instead (it auto-applies the case number to catch every variant). "
        "\n\nUSAGE: put your search terms in `body_query` — that field "
        "searches subject + body + headers together. Only use "
        "`subject_query` when you need to restrict to subject-line matches "
        "specifically (rare). If the first search returns nothing, try a "
        "broader or more specific `body_query` rather than reaching for "
        "`subject_query`."
    )
    input_schema: ClassVar[type[BaseModel]] = GmailSearchInput

    @classmethod
    async def invoke(cls, ctx: ToolContext, **kwargs: Any) -> dict:
        args = GmailSearchInput(**kwargs)
        if not args.subject_query and not args.body_query:
            return {
                "total": 0,
                "emails": [],
                "error": "Provide at least one of subject_query or body_query.",
            }
        try:
            result = await ToolBox.query_email(
                email_type=EmailType.GMAIL,
                subject_query=args.subject_query,
                body_query=args.body_query,
                max_results=args.max_results,
                case_number=None,  # un-scoped on purpose
            )
            return {
                "subject_query": args.subject_query,
                "body_query": args.body_query,
                "total": result.total,
                "emails": [
                    {
                        "id": e.id,
                        "subject": e.subject,
                        "sender": e.sender,
                        "date": e.date,
                        "body": (e.body or "")[:2000],
                    }
                    for e in result.emails
                ],
            }
        except Exception as e:
            logger.exception(
                "gmail_search failed user=%s subject=%r body=%r: %s",
                ctx.user_id, args.subject_query, args.body_query, e,
            )
            return {
                "total": 0,
                "emails": [],
                "error": str(e),
            }
