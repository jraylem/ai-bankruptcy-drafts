"""
Email backfill + per-case vector indexing.

Queries Gmail and Court Drive for all emails whose subject contains the
case number, converts each email into a Document, and stores one embedding
row per email in gmail_emails_{case_id} / courtdrive_emails_{case_id}.

No chunking: one email in, one row out.
"""

import logging

from langchain_core.documents import Document

from src.core.common.services.email import Email, EmailSearchResult, EmailType
from src.core.common.storage.vectorstore import index_documents
from src.core.common.toolbox import ToolBox

logger = logging.getLogger(__name__)


class EmailIndexer:
    """Case-email backfill into per-case pgvector collections."""

    _BACKFILL_MAX_RESULTS = 100

    @staticmethod
    def _format_email_body(email: Email) -> str:
        return (
            f"Subject: {email.subject}\n"
            f"From: {email.sender}\n"
            f"Date: {email.date}\n\n"
            f"{email.body}"
        )

    @staticmethod
    def _emails_to_documents(
        search_result: EmailSearchResult,
        case_id: str,
        case_number: str,
        source: str,
        doc_type: str,
    ) -> list[Document]:
        documents: list[Document] = []
        for email in search_result.emails:
            documents.append(
                Document(
                    page_content=EmailIndexer._format_email_body(email),
                    metadata={
                        "case_id": case_id,
                        "case_number": case_number,
                        "source": source,
                        "doc_type": doc_type,
                        "email_id": email.id,
                        "subject": email.subject,
                        "sender": email.sender,
                        "date": email.date,
                    },
                )
            )
        return documents

    @staticmethod
    async def _index_one_source(
        case_id: str,
        case_number: str,
        email_type: EmailType,
        collection_name: str,
        source: str,
        doc_type: str,
    ) -> int:
        try:
            result = await ToolBox.query_email(
                email_type=email_type,
                case_number=case_number,
                max_results=EmailIndexer._BACKFILL_MAX_RESULTS,
            )
        except Exception as e:
            logger.warning(
                f"Email backfill failed for case {case_id} source={source}: {e}"
            )
            return 0

        documents = EmailIndexer._emails_to_documents(
            search_result=result,
            case_id=case_id,
            case_number=case_number,
            source=source,
            doc_type=doc_type,
        )
        if not documents:
            logger.info(
                f"No {source} emails matched case_number={case_number} for case {case_id}"
            )
            return 0

        return await index_documents(
            collection_name=collection_name,
            documents=documents,
            chunk_size=None,
        )

    @staticmethod
    async def index(
        case_id: str, resource_key: str, case_number: str,
    ) -> tuple[int, int]:
        """Backfill Gmail + Court Drive emails for the given case_number.

        `case_id` (UUID PK) is written into Document metadata. `resource_key`
        (sanitized case_number) names the pgvector collections — decoupled
        from the PK so the "collection = <kind>_emails_<sanitized>"
        invariant survives the Phase 1 UUID migration.

        Returns (gmail_rows_written, courtdrive_rows_written). Each email
        becomes exactly one row in its respective collection
        (chunk_size=None).
        """
        gmail_count = await EmailIndexer._index_one_source(
            case_id=case_id,
            case_number=case_number,
            email_type=EmailType.GMAIL,
            collection_name=f"gmail_emails_{resource_key}",
            source="gmail",
            doc_type="email",
        )
        courtdrive_count = await EmailIndexer._index_one_source(
            case_id=case_id,
            case_number=case_number,
            email_type=EmailType.COURT_DRIVE,
            collection_name=f"courtdrive_emails_{resource_key}",
            source="court_drive",
            doc_type="court_email",
        )
        return gmail_count, courtdrive_count
