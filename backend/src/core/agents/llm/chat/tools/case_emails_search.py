"""`case_emails_search` chat tool — Gmail search scoped to the current case.

Wraps `ToolBox.query_email` against the firm's Gmail inbox and applies
the case-number-in-subject filter so only emails carrying THIS case's
number in their subject line come back. Court ECF notifications arrive
through Gmail too — their subjects always include the case number
(`1:26-bk-10700-PGH …`), so they are reachable through this tool
without a separate code path.
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


class CaseEmailsSearchInput(BaseModel):
    """Args the model passes to `case_emails_search`."""
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
class CaseEmailsSearchTool(BaseChatTool):
    """Search the firm Gmail inbox, scoped to THIS case via subject-line case-number match."""

    name: ClassVar[str] = "case_emails_search"
    description: ClassVar[str] = (
        "Search the firm's Gmail inbox, scoped to THIS case via a "
        "subject-line case-number match. The case number (and its short "
        "/ bk-prefixed variants) is applied automatically — don't repeat "
        "it in your query. Court ECF notifications also arrive through "
        "Gmail (their subjects always include the case number), so this "
        "tool catches them too. Use it when the user asks about "
        "correspondence on THIS case: what the trustee said, what's been "
        "filed recently, court notices, scheduling, etc."
        "\n\nUSAGE: put your search terms in `body_query` — that field "
        "searches subject + body + headers together. Only use "
        "`subject_query` when you need to restrict to subject-line matches "
        "specifically (rare). If `case_emails_search` returns nothing, "
        "consider retrying with `gmail_search` (un-scoped) — useful when "
        "the relevant email doesn't carry the case number in its subject."
    )
    input_schema: ClassVar[type[BaseModel]] = CaseEmailsSearchInput

    @classmethod
    async def invoke(cls, ctx: ToolContext, **kwargs: Any) -> dict:
        args = CaseEmailsSearchInput(**kwargs)
        try:
            result = await ToolBox.query_email(
                email_type=EmailType.GMAIL,
                subject_query=args.subject_query,
                body_query=args.body_query,
                max_results=args.max_results,
                case_number=ctx.case.case_number,
                # Subject-only case-number filtering — case correspondence
                # reliably puts the case number in the subject, and a
                # body-anywhere match brings in forwarded threads that
                # mention an unrelated case number.
                case_number_in_subject=True,
            )
            return {
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
                "case_emails_search failed for case %s: %s",
                ctx.case.id, e,
            )
            return {
                "total": 0,
                "emails": [],
                "error": str(e),
            }
