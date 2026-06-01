from typing import Optional
from langchain_core.tools import tool
from ...chatbot.vectorestore import search_vectorstore

# Called by: GmailMotionServiceAgent (agents/cert_service.py)
def cert_service_gmail_tool(session_id: Optional[str] = None):
    """
    Individual tools for certificate of service base field extraction.
    Covers court district and debtor name (petition PDF) plus case number
    and chapter (Gmail vectorstore).
    Trustee/hearing fields are fetched directly in service/cert_service.py.
    """

    @tool()
    def extract_court_district_cert_service(query: str):
        """Extract court district from bankruptcy petition PDFs"""
        if not session_id:
            return "No session_id available. Please start a session or upload a PDF first."

        pdf_collection = f"bankruptcy_knowledge_{session_id}"
        pdf_docs = search_vectorstore(query, collection_name=pdf_collection, k=15)
        if not pdf_docs:
            return f"No relevant passages found in collection '{pdf_collection}'."

        return "\n\n".join(
            (f"Source: {doc.metadata}\nContent: {doc.page_content}")
            for doc in pdf_docs
        )

    @tool()
    def extract_debtor_name_cert_service(query: str):
        """Extract debtor name from bankruptcy petition PDFs"""
        if not session_id:
            return "No session_id available. Please start a session or upload a PDF first."

        pdf_collection = f"bankruptcy_knowledge_{session_id}"
        pdf_docs = search_vectorstore(query, collection_name=pdf_collection, k=15)
        if not pdf_docs:
            return f"No relevant passages found in collection '{pdf_collection}'."

        return "\n\n".join(
            (f"Source: {doc.metadata}\nContent: {doc.page_content}")
            for doc in pdf_docs
        )

    @tool()
    def extract_case_number_cert_service(query: str):
        """
        Extract case number (with judge initial) from Gmail emails for this case.
        Falls back to bankruptcy petition PDF if Gmail has no results.
        The case number should include the judge initial suffix (e.g., "25-14980-PDR").
        """
        if not session_id:
            return "No session_id available. Please start a session or ingest Gmail emails first."

        gmail_collection = f"gmail_{session_id}"
        gmail_docs = search_vectorstore(query, collection_name=gmail_collection, k=15)
        if gmail_docs:
            return "\n\n".join(
                (f"Source: {doc.metadata}\nContent: {doc.page_content}")
                for doc in gmail_docs
            )

        # Fallback: try petition PDF
        pdf_collection = f"bankruptcy_knowledge_{session_id}"
        pdf_docs = search_vectorstore(query, collection_name=pdf_collection, k=15)
        if not pdf_docs:
            return f"No relevant passages found in '{gmail_collection}' or '{pdf_collection}'."
        return "\n\n".join(
            (f"Source: {doc.metadata}\nContent: {doc.page_content}")
            for doc in pdf_docs
        )

    @tool()
    def extract_chapter_cert_service(query: str):
        """
        Extract chapter from Gmail emails for this case.
        Falls back to bankruptcy petition PDF if Gmail has no results.
        """
        if not session_id:
            return "No session_id available. Please start a session or ingest Gmail emails first."

        gmail_collection = f"gmail_{session_id}"
        gmail_docs = search_vectorstore(query, collection_name=gmail_collection, k=15)
        if gmail_docs:
            return "\n\n".join(
                (f"Source: {doc.metadata}\nContent: {doc.page_content}")
                for doc in gmail_docs
            )

        # Fallback: try petition PDF
        pdf_collection = f"bankruptcy_knowledge_{session_id}"
        pdf_docs = search_vectorstore(query, collection_name=pdf_collection, k=15)
        if not pdf_docs:
            return f"No relevant passages found in '{gmail_collection}' or '{pdf_collection}'."
        return "\n\n".join(
            (f"Source: {doc.metadata}\nContent: {doc.page_content}")
            for doc in pdf_docs
        )

    @tool()
    def extract_case_number_cert_service_pdf(query: str):
        """Extract case number from bankruptcy petition PDFs (PDF fallback for when Gmail returns N/A)"""
        if not session_id:
            return "No session_id available. Please start a session or upload a PDF first."

        pdf_collection = f"bankruptcy_knowledge_{session_id}"
        pdf_docs = search_vectorstore(query, collection_name=pdf_collection, k=15)
        if not pdf_docs:
            return f"No relevant passages found in collection '{pdf_collection}'."

        return "\n\n".join(
            (f"Source: {doc.metadata}\nContent: {doc.page_content}")
            for doc in pdf_docs
        )

    @tool()
    def extract_chapter_cert_service_pdf(query: str):
        """Extract chapter number from bankruptcy petition PDFs (PDF fallback for when Gmail returns N/A)"""
        if not session_id:
            return "No session_id available. Please start a session or upload a PDF first."

        pdf_collection = f"bankruptcy_knowledge_{session_id}"
        pdf_docs = search_vectorstore(query, collection_name=pdf_collection, k=15)
        if not pdf_docs:
            return f"No relevant passages found in collection '{pdf_collection}'."

        return "\n\n".join(
            (f"Source: {doc.metadata}\nContent: {doc.page_content}")
            for doc in pdf_docs
        )

    return [
        extract_court_district_cert_service,
        extract_debtor_name_cert_service,
        extract_case_number_cert_service,
        extract_chapter_cert_service,
        extract_case_number_cert_service_pdf,
        extract_chapter_cert_service_pdf,
    ]
