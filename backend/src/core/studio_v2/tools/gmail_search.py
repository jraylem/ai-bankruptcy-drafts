"""Gmail-search tool — wraps LangChain's `GmailSearch` so extractor
agents can issue Gmail-query-syntax searches inside their tool loop.

The Phase 0 dumb-down design intentionally removed the v1 requirement
that authors hand-write `subject_query` + `body_query` filters.
Paralegals now write ONE natural-language `extraction_prompt`
("the debtor's monthly income from the most recent paystub"), and
this tool lets the extractor LLM translate that into one or more
Gmail-query calls itself.

OAuth reuse: this module imports v1's `case_inbox/gmail.py` ONLY to
borrow the existing `token.json` location + SCOPES — never modifies
v1 code or shares state. The firm OAuth token loaded here is the
same one the ECF cron uses (bound to the firm-wide mailbox per
`reference_case_inbox_oauth_mailbox` memory).
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

logger = logging.getLogger(__name__)


def case_number_variants(case_number: str | None) -> list[str]:
    """Generate Gmail-search variants of a bankruptcy case number.

    Bankruptcy case numbers come in several flavors in PACER /
    creditor / court emails:
      - `26-15038-PDR`              year-NUM-judge_initials (canonical)
      - `26-15038`                  without the judge-initials suffix
      - `8:26-bk-15038-PDR`         district + bk court prefix (Florida)
      - `8:26-bk-15038`             district + court prefix, no judge

    Each variant is returned WITHOUT quotes; the caller wraps each in
    quotes when building a Gmail OR-group. Returned in
    longest-first order so the most-specific match has highest
    priority in any human-facing display.

    Empty / None case_number → empty list (caller falls back to
    unscoped search).
    """
    if not case_number:
        return []
    raw = case_number.strip()
    if not raw:
        return []
    variants: set[str] = {raw}

    # Strip trailing judge-initials block (e.g. "-PDR", "-SMG", "-KKS")
    def _strip_judge(s: str) -> str:
        return re.sub(r"-[A-Z]{2,4}$", "", s)

    no_judge = _strip_judge(raw)
    if no_judge != raw:
        variants.add(no_judge)

    # Strip leading district + court-type prefix
    #   "8:26-bk-15038-PDR" → "26-15038-PDR"
    #   "1:24-cv-04200-RDB" → "24-04200-RDB"
    no_district = re.sub(
        r"^\d+:(\d+)-(?:bk|cv|cr)-",
        r"\1-",
        raw,
        flags=re.IGNORECASE,
    )
    if no_district != raw:
        variants.add(no_district)
        variants.add(_strip_judge(no_district))

    return sorted(variants, key=lambda v: (-len(v), v))


def build_case_scope_clause(case_number: str | None) -> str:
    """Build a Gmail-query clause that scopes a search to the active case.

    Returns a parenthesized OR-group of quoted variants suitable for
    AND-ing to any user query, e.g.:
        `("26-15038-PDR" OR "26-15038")`

    Returns `""` when no case_number is available — the caller then
    sends the user's query unmodified.
    """
    variants = case_number_variants(case_number)
    if not variants:
        return ""
    if len(variants) == 1:
        return f'"{variants[0]}"'
    return "(" + " OR ".join(f'"{v}"' for v in variants) + ")"


def apply_case_scope_to_query(user_query: str, case_number: str | None) -> str:
    """AND-append the case-scope clause to `user_query`.

    The clause is ALWAYS appended (not substituted in) so any
    `subject:` / `from:` / `after:` operators the LLM already used
    remain intact. Idempotent: if the variant already appears in the
    user_query, we skip to avoid double-scoping.
    """
    clause = build_case_scope_clause(case_number)
    if not clause:
        return user_query
    # Cheap dedup: if ANY variant already appears in the query, the
    # LLM already scoped it — don't duplicate.
    for variant in case_number_variants(case_number):
        if variant in user_query:
            return user_query
    base = user_query.strip()
    if not base:
        return clause
    return f"{base} {clause}"


def load_firm_gmail_credentials() -> Any | None:
    """Load the firm's Gmail OAuth `Credentials` object from disk.

    Reuses v1's `token.json` location + SCOPES via read-only import.
    Returns `None` (not raises) when the token file is missing or
    can't be refreshed — the extractor agent then receives a tool
    error and decides whether to retry with a different source or
    stop. Never raises into the pipeline.
    """
    try:
        # Read-only import — v1 path / OAuth bootstrapping is the same
        # the ECF cron has been using for months, so we know it works.
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials

        from src.core.components.case_inbox.gmail import _TOKEN_PATH, SCOPES
    except ImportError as err:
        logger.warning("gmail_search: import failed (%s); tool will return errors", err)
        return None

    if not os.path.exists(_TOKEN_PATH):
        logger.warning("gmail_search: %s missing — tool will return errors", _TOKEN_PATH)
        return None

    try:
        creds = Credentials.from_authorized_user_file(_TOKEN_PATH, SCOPES)
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        return creds
    except Exception as err:  # noqa: BLE001 — bubble up via None, never raise
        logger.warning("gmail_search: token load/refresh failed (%s)", err)
        return None


def build_gmail_search_tool(ctx) -> Any | None:
    """Construct a Gmail-search tool bound to the firm's Gmail OAuth.

    LOAD-BEARING — case-scope enforcement: every query the LLM agent
    sends is rewritten via `apply_case_scope_to_query()` to AND-append
    a parenthesized OR-group of the active case's number variants
    (e.g. `("26-15038-PDR" OR "26-15038")`). This guarantees the
    Gmail search returns only emails matching THIS case, even if the
    LLM forgets to include the case number in its query. Without
    this, the firm's shared mailbox returns claims / notices from
    every case in the inbox (real bug observed during dry-run).

    The wrapped tool exposes the SAME interface as LangChain's
    `GmailSearch._run(query)` so the agent sees a single
    `gmail_search(query: str) -> list[dict]` call shape.

    Returns `None` when:
    - `ctx.firm_oauth` is missing (constructor didn't get a token)
    - LangChain's `langchain-google-community` package isn't importable
    - building the Gmail resource service raises

    Callers (the orchestration layer's toolset builder) filter `None`
    out of the toolset before handing it to the agent — the agent
    then never sees a tool that would fail at call time.
    """
    creds = ctx.firm_oauth
    if creds is None:
        logger.debug("build_gmail_search_tool: no firm_oauth on context; tool unavailable")
        return None
    try:
        from langchain.tools import tool as langchain_tool
        from langchain_google_community.gmail.search import GmailSearch
        from langchain_google_community.gmail.utils import build_resource_service
    except ImportError as err:
        logger.warning(
            "build_gmail_search_tool: langchain-google-community not importable (%s); "
            "tool unavailable",
            err,
        )
        return None
    try:
        api_resource = build_resource_service(credentials=creds)
        underlying = GmailSearch(api_resource=api_resource)
    except Exception as err:  # noqa: BLE001 — broad on purpose
        logger.warning("build_gmail_search_tool: build_resource_service failed (%s)", err)
        return None

    case_number = getattr(getattr(ctx, "case", None), "case_number", None)
    variants = case_number_variants(case_number)
    variants_blurb = (
        " · ".join(variants) if variants else "(no case_number on file)"
    )

    @langchain_tool(  # type: ignore[misc]
        "gmail_search",
        description=(
            "Search the firm's shared Gmail inbox using Gmail query "
            "syntax. Each result includes `subject`, `sender`, "
            "`snippet`, and the full plain-text `body` of the email.\n\n"
            "QUERY TIPS — match by content, not just headers:\n"
            "  - Default to UNQUOTED search terms with NO operator: "
            "Gmail matches across subject, body, sender, and "
            "attachments. Example: `\"proof of claim\"` matches the "
            "phrase anywhere in the email.\n"
            "  - Use operators ONLY when narrowing helps: `from:` for "
            "specific senders, `after:YYYY/MM/DD` for date windows. "
            "Avoid `subject:` unless you specifically want to ignore "
            "the body — most useful answers live in the body.\n"
            "  - The active case's number is AUTOMATICALLY "
            "AND-appended to every query (auto-scope: "
            f"{variants_blurb}). You do NOT need to include it.\n\n"
            "Returns up to 25 most-recent matching emails."
        ),
    )
    def gmail_search(query: str) -> Any:
        scoped = apply_case_scope_to_query(query, case_number)
        if scoped != query:
            logger.info(
                "gmail_search: scoped query · llm=%r · sent=%r",
                query,
                scoped,
            )
        # Bump max_results above LangChain's default (10) — the
        # case-scope clause already narrows, so we can safely pull a
        # wider window and let the agent pick the right one from the
        # body contents.
        return underlying._run(scoped, max_results=25)

    return gmail_search
