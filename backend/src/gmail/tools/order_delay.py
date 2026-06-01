from typing import Optional
from langchain_core.tools import tool
from ...chatbot.vectorestore import search_vectorstore

# Called by: GmailOrderDelayAgent (agents/order_delay.py)
def order_delay_gmail_tool(session_id: Optional[str] = None):
    """
    Individual tools for order delay payload extraction using Gmail + petition.

    - Petition (bankruptcy_knowledge_<session_id>) for:
      debtor_name_delay
    - Gmail (gmail_<session_id>) for:
      case_number_delay (with judge initial), chapter_delay
    """

    @tool()
    def extract_court_district_delay(query: str):
        """Extract court district from bankruptcy petition PDFs"""
        if not session_id:
            return "No session_id available. Please start a session or upload a PDF first."

        pdf_collection = f"bankruptcy_knowledge_{session_id}"
        pdf_docs = search_vectorstore(query, collection_name=pdf_collection, k=15)
        if not pdf_docs:
            return f"No relevant passages found in collection '{pdf_collection}'."

        return "\n\n".join(
            f"Source: {doc.metadata}\nContent: {doc.page_content}"
            for doc in pdf_docs
        )

    @tool()
    def extract_debtor_name_delay(query: str):
        """Extract debtor name from bankruptcy petition PDFs"""
        if not session_id:
            return "No session_id available. Please start a session or upload a PDF first."

        pdf_collection = f"bankruptcy_knowledge_{session_id}"
        pdf_docs = search_vectorstore(query, collection_name=pdf_collection, k=15)
        if not pdf_docs:
            return f"No relevant passages found in collection '{pdf_collection}'."

        return "\n\n".join(
            f"Source: {doc.metadata}\nContent: {doc.page_content}"
            for doc in pdf_docs
        )

    @tool()
    def extract_case_number_delay(query: str):
        """
        Extract case number (with judge initial) from Gmail emails for this case.

        Expects a collection named gmail_<session_id> to contain
        case-related emails (subjects and bodies).
        The case number should include the judge initial suffix (e.g., "25-14980-PDR").
        """
        if not session_id:
            return "No session_id available. Please start a session or ingest Gmail emails first."

        gmail_collection = f"gmail_{session_id}"
        gmail_docs = search_vectorstore(query, collection_name=gmail_collection, k=15)
        if not gmail_docs:
            return f"No relevant passages found in collection '{gmail_collection}'."

        return "\n\n".join(
            f"Source: {doc.metadata}\nContent: {doc.page_content}"
            for doc in gmail_docs
        )

    @tool()
    def extract_case_number_delay_pdf(query: str):
        """Extract case number from bankruptcy petition PDFs (PDF fallback for when Gmail returns N/A)"""
        if not session_id:
            return "No session_id available. Please start a session or upload a PDF first."

        pdf_collection = f"bankruptcy_knowledge_{session_id}"
        pdf_docs = search_vectorstore(query, collection_name=pdf_collection, k=15)
        if not pdf_docs:
            return f"No relevant passages found in collection '{pdf_collection}'."

        return "\n\n".join(
            f"Source: {doc.metadata}\nContent: {doc.page_content}"
            for doc in pdf_docs
        )

    @tool()
    def extract_chapter_delay(query: str):
        """Extract chapter number from Gmail emails (e.g. '13', '7')"""
        if not session_id:
            return "No session_id available. Please start a session or ingest Gmail emails first."

        gmail_collection = f"gmail_{session_id}"
        gmail_docs = search_vectorstore(query, collection_name=gmail_collection, k=15)
        if not gmail_docs:
            return f"No relevant passages found in collection '{gmail_collection}'."

        return "\n\n".join(
            f"Source: {doc.metadata}\nContent: {doc.page_content}"
            for doc in gmail_docs
        )

    @tool()
    def extract_chapter_delay_pdf(query: str):
        """Extract chapter number from bankruptcy petition PDFs (PDF fallback for when Gmail returns N/A)"""
        if not session_id:
            return "No session_id available. Please start a session or upload a PDF first."

        pdf_collection = f"bankruptcy_knowledge_{session_id}"
        pdf_docs = search_vectorstore(query, collection_name=pdf_collection, k=15)
        if not pdf_docs:
            return f"No relevant passages found in collection '{pdf_collection}'."

        return "\n\n".join(
            f"Source: {doc.metadata}\nContent: {doc.page_content}"
            for doc in pdf_docs
        )

    return [
        extract_court_district_delay,
        extract_debtor_name_delay,
        extract_case_number_delay,
        extract_case_number_delay_pdf,
        extract_chapter_delay,
        extract_chapter_delay_pdf,
    ]
