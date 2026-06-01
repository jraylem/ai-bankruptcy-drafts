"""Canonical tool-surface for context fetching inside core.

Every external source the draft pipeline consumes (Gmail, Court Drive,
case-specific vector collections, the mocked law-practice KB) is reached
through a classmethod on ToolBox. Subclasses of Agent / resolvers call
these directly so there's exactly one place to adjust source wiring,
fallback behaviour, or observability.
"""

from src.core.common.services.email import (
    EmailQueryService,
    EmailSearchResult,
    EmailType,
)
from src.core.common.services.vector import (
    VectorQueryService,
    VectorSearchResult,
)


class ToolBox:
    """Canonical tool surface for every external-source fetch the draft pipeline makes (email, vector, etc.)."""

    @staticmethod
    async def query_email(
        email_type: EmailType,
        subject_query: str | None = None,
        body_query: str | None = None,
        max_results: int = 10,
        case_number: str | None = None,
        case_number_in_subject: bool = False,
    ) -> EmailSearchResult:
        """Query emails from Gmail or Court Drive.

        When case_number is provided, the query includes a phrase-quoted
        OR-clause of all known case-number variants (short + bk forms) so
        the result matches regardless of which format the email uses in
        its subject or body. Pass `case_number_in_subject=True` to require
        the case number to appear in the subject line specifically — used
        by the `case_emails_search` chat tool to avoid forwarded-body
        false positives.
        """
        service = EmailQueryService(email_type)
        return await service.search(
            subject_query=subject_query,
            body_query=body_query,
            max_results=max_results,
            case_number=case_number,
            case_number_in_subject=case_number_in_subject,
        )

    @staticmethod
    async def query_law_practice(query: str) -> VectorSearchResult:
        """[MOCK] Law-practice knowledge-base lookup.

        Routes through `VectorQueryService.query_law_practice`, which
        still returns a placeholder result until the real KB collection
        is wired. The mock prefix is visible in traces.
        """
        return await VectorQueryService.query_law_practice(query)

    @staticmethod
    async def query_case_specific(
        collection_name: str,
        query: str,
        k: int = 5,
    ) -> VectorSearchResult:
        """Similarity search against a case-specific pgvector collection.

        Canonical entry point for real vector retrieval. Used by
        CASE_VECTOR fields and by the Gmail / CourtDrive vector-fallback
        when a live email query returns empty.
        """
        return await VectorQueryService.query_case_specific(
            collection_name=collection_name,
            query=query,
            k=k,
        )
