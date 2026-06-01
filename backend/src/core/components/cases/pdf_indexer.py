"""
Petition PDF chunking and embedding.

Reads a bankruptcy petition PDF page-by-page with pypdf, builds one Document
per page carrying case-level metadata, and hands off to the core vectorstore
wrapper for chunked indexing into case_file_{case_id}.
"""

import logging
from io import BytesIO

from langchain_core.documents import Document
from pypdf import PdfReader

from src.core.agents.llm.case_ingestion import CaseMetadata
from src.core.common.storage.vectorstore import index_documents

logger = logging.getLogger(__name__)


class PdfIndexer:
    """Petition PDF page-wise indexing into the case_file collection."""

    @staticmethod
    async def index(
        case_id: str,
        resource_key: str,
        pdf_bytes: bytes,
        case_metadata: CaseMetadata,
    ) -> int:
        """Extract per-page text from the petition, chunk, embed, and store.

        `case_id` (UUID, PK) is written into Document metadata so chunks
        link back to their owning case. `resource_key` (sanitized
        case_number for filed cases) names the pgvector collection —
        decoupled from the PK so the "collection = case_file_<sanitized>"
        invariant survives the Phase 1 UUID migration.

        Uses chunk_size=500 / chunk_overlap=50 (spec: overlap at least 50
        for case file content). Returns the number of embedding rows
        written.
        """
        reader = PdfReader(BytesIO(pdf_bytes))

        documents: list[Document] = []
        for idx, page in enumerate(reader.pages):
            text = (page.extract_text() or "").strip()
            if not text:
                continue
            documents.append(
                Document(
                    page_content=text,
                    metadata={
                        "case_id": case_id,
                        "case_number": case_metadata.case_number,
                        "case_name": case_metadata.case_name,
                        "source": "petition.pdf",
                        "doc_type": "petition_page",
                        "page": idx,
                    },
                )
            )

        if not documents:
            logger.warning(f"Petition PDF for case {case_id} produced no extractable text")
            return 0

        return await index_documents(
            collection_name=f"case_file_{resource_key}",
            documents=documents,
            chunk_size=500,
            chunk_overlap=50,
        )
