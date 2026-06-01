from typing import Optional, Dict
from langchain_core.tools import tool
from ...chatbot.vectorestore import search_vectorstore

# Called by: GmailOrderImposeRegularAgent (agents/order_impose.py)
def order_impose_regular_gmail_tool(session_id: Optional[str] = None):
    """
    Individual tools for ORDER IMPOSE REGULAR extraction backed by Gmail + petition.

    - Petition (bankruptcy_knowledge_<session_id>) for:
      debtor_name_order_impose_regular
    - Gmail (gmail_<session_id>) for:
      case_number_order_impose_regular (with judge initial), chapter_order_impose_regular
    """

    @tool()
    def extract_debtor_name_order_impose_regular(query: str):
        """Extract debtor name from bankruptcy petition PDFs for Order Impose Regular"""
        if not session_id:
            return "No session_id available. Please start a session or upload a PDF first."

        pdf_collection = f"bankruptcy_knowledge_{session_id}"
        pdf_docs = search_vectorstore(query, collection_name=pdf_collection, k=15)
        if not pdf_docs:
            return f"No relevant passages found in collection '{pdf_collection}'."

        serialized = "\n\n".join(
            (f"Source: {doc.metadata}\nContent: {doc.page_content}") for doc in pdf_docs
        )
        return serialized

    @tool()
    def extract_case_number_order_impose_regular(query: str):
        """
        Extract case number (with judge initial) from Gmail emails for Order Impose Regular.

        Expects a collection named gmail_<session_id> to contain case-related emails.
        The case number should include the judge initial suffix (e.g., "25-12345-PDR").
        """
        if not session_id:
            return "No session_id available. Please start a session or ingest Gmail emails first."

        gmail_collection = f"gmail_{session_id}"
        gmail_docs = search_vectorstore(query, collection_name=gmail_collection, k=15)
        if not gmail_docs:
            return f"No relevant passages found in collection '{gmail_collection}'."

        serialized = "\n\n".join(
            (f"Source: {doc.metadata}\nContent: {doc.page_content}") for doc in gmail_docs
        )
        return serialized

    @tool()
    def extract_chapter_order_impose_regular(query: str):
        """Extract chapter from Gmail emails for Order Impose Regular"""
        if not session_id:
            return "No session_id available. Please start a session or ingest Gmail emails first."

        gmail_collection = f"gmail_{session_id}"
        gmail_docs = search_vectorstore(query, collection_name=gmail_collection, k=15)
        if not gmail_docs:
            return f"No relevant passages found in collection '{gmail_collection}'."

        serialized = "\n\n".join(
            (f"Source: {doc.metadata}\nContent: {doc.page_content}") for doc in gmail_docs
        )
        return serialized

    return [
        extract_debtor_name_order_impose_regular,
        extract_case_number_order_impose_regular,
        extract_chapter_order_impose_regular,
    ]


