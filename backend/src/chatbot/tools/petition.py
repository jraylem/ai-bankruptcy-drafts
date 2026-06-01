from typing import Optional
from langchain_core.tools import tool
from sqlalchemy import create_engine, text
from ...config import settings

# Called by: ChatAgent (agents/chat.py)

_TOOL_SYNC_ENGINE = create_engine(
    settings.CHAT_DATABASE_URL.replace("+asyncpg", "+psycopg"),
    pool_pre_ping=True,
    pool_recycle=300,
    echo=False,
)


def _resolve_session_petition_path_sync(session_id: str) -> Optional[str]:
    """Fetch the latest PDF file path for a session and verify it on disk."""
    from ..pending_petitions import _resolve_managed_path

    with _TOOL_SYNC_ENGINE.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT file_path FROM pdf_documents
                WHERE session_id = :session_id
                ORDER BY uploaded_at DESC NULLS LAST, id DESC
                LIMIT 1
                """
            ),
            {"session_id": session_id},
        ).fetchone()

    if not row or not row[0]:
        return None
    resolved = _resolve_managed_path(row[0])
    if not resolved or not resolved.exists() or not resolved.is_file():
        return None
    return str(resolved)


def petition_pdf_tool(session_id: Optional[str] = None):
    @tool()
    def read_petition_pdf(query: str):
        """
        Use this tool to answer questions about the petition PDF that text-extracted
        chunks can't answer reliably — checkbox states (☑ / ☐), filled-in form values,
        signature presence, or anything that depends on the visual form layout.

        Examples of when to use this:
        - "In the SOFA, did the debtor mark Yes or No on Question 9 about lawsuits?"
        - "Was line 11 of Schedule J left blank?"
        - "Is the attorney signature present on page 84?"
        - "Which box is checked for Q5 of the Voluntary Petition?"

        Do NOT use this for general fact lookups already covered by query_uploaded_file
        (debtor name, case number, dollar totals from text). Reach for this only when
        a checkbox / form-field answer matters.

        The PDF is sent to a vision-capable model on each call. The first call in a
        session pays full cost; subsequent calls within ~5 minutes hit the prompt
        cache and are roughly an order of magnitude cheaper.

        Args:
            query: A specific question about the petition. Be concrete — name the
                   form (SOFA / Schedule J / Voluntary Petition / Means Test) and
                   the question or line number when known.
        """
        if not session_id:
            return "No session_id available — cannot read petition PDF."

        from ..petition_vision_extractor import query_petition_pdf

        file_path = _resolve_session_petition_path_sync(session_id)
        if not file_path:
            return (
                "No petition PDF on disk for this session. The file may have been "
                "archived or the session has no uploaded petition yet."
            )

        answer = query_petition_pdf(file_path, query)
        if not answer:
            return (
                "Vision read failed (see backend logs). Try again, or fall back to "
                "query_uploaded_file for a text-based search."
            )
        return answer

    return [read_petition_pdf]
