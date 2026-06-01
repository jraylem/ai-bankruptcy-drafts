from typing import Optional
from langchain_core.tools import tool
from ...chatbot.vectorestore import search_vectorstore


# Called by: GmailOrderExtendAgent (agents/order_extend.py)
def order_extend_gmail_tool(session_id: Optional[str] = None):
    """
    Individual tools for ORDER EXTEND extraction backed by Gmail + petition.

    - Petition (bankruptcy_knowledge_<session_id>) for:
      debtor_name_order_extend
    - Gmail (gmail_<session_id>) for:
      case_number_order_extend (with judge initial), chapter_order_extend
    """

    @tool()
    def extract_debtor_name_order_extend(query: str):
        """Extract debtor name from bankruptcy petition PDFs for Order Extend"""
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
    def extract_case_number_order_extend(query: str):
        """
        Extract case number (with judge initial) from Gmail emails for Order Extend.

        Expects a collection named gmail_<session_id> to contain case-related emails.
        The case number should include the judge initial suffix (e.g., "25-12345-PDR").
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
    def extract_case_number_order_extend_pdf(query: str):
        """Extract case number from bankruptcy petition PDFs for Order Extend (PDF fallback)"""
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
    def extract_chapter_order_extend(query: str):
        """Extract chapter number from Gmail emails for Order Extend (e.g. '13', '7')"""
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
    def extract_chapter_order_extend_pdf(query: str):
        """Extract chapter number from bankruptcy petition PDFs for Order Extend (PDF fallback)"""
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
        extract_debtor_name_order_extend,
        extract_case_number_order_extend,
        extract_case_number_order_extend_pdf,
        extract_chapter_order_extend,
        extract_chapter_order_extend_pdf,
    ]

