from typing import Optional, Dict
from langchain_core.tools import tool
from ...chatbot.vectorestore import search_vectorstore

# Called by: GmailMotionLOEAgent (agents/loe.py)
def loe_gmail_tool(session_id: Optional[str] = None):
    """
    Individual tools for motion LOE payload extraction,
    using Gmail-backed vectorstore for trustee name, chapter number, and judge initial,
    and petition vectorstore for debtor name and case number.
    """

    @tool()
    def extract_trustee_name_loe(query: str):
        """
        Extract trustee name from Gmail emails for this case.
        
        Expects a collection named gmail_<session_id> to contain
        case-related emails (subjects and bodies).
        """
        if not session_id:
            return "No session_id available. Please start a session or ingest Gmail emails first."

        gmail_collection = f"gmail_{session_id}"
        gmail_docs = search_vectorstore(query, collection_name=gmail_collection, k=15)
        if not gmail_docs:
            return f"No relevant passages found in collection '{gmail_collection}'."

        serialized = "\n\n".join(
            (f"Source: {doc.metadata}\nContent: {doc.page_content}")
            for doc in gmail_docs
        )
        return serialized

    @tool()
    def extract_chapter_number_loe(query: str):
        """
        Extract chapter number from Gmail emails for this case.
        
        Expects a collection named gmail_<session_id> to contain
        case-related emails (subjects and bodies).
        """
        if not session_id:
            return "No session_id available. Please start a session or ingest Gmail emails first."

        gmail_collection = f"gmail_{session_id}"
        gmail_docs = search_vectorstore(query, collection_name=gmail_collection, k=15)
        if not gmail_docs:
            return f"No relevant passages found in collection '{gmail_collection}'."

        serialized = "\n\n".join(
            (f"Source: {doc.metadata}\nContent: {doc.page_content}")
            for doc in gmail_docs
        )
        return serialized

    @tool()
    def extract_judge_initial_loe(query: str):
        """
        Extract judge initial from Gmail emails for this case.
        
        Expects a collection named gmail_<session_id> to contain
        case-related emails (subjects and bodies).
        The judge initial should be extracted from case numbers in the format xx-xxxxx-XXX
        (e.g., "25-22321-CLC" where "CLC" is the judge initial).
        DO NOT extract from trustee names or other names in the email.
        """
        if not session_id:
            return "No session_id available. Please start a session or ingest Gmail emails first."

        gmail_collection = f"gmail_{session_id}"
        gmail_docs = search_vectorstore(query, collection_name=gmail_collection, k=15)
        if not gmail_docs:
            return f"No relevant passages found in collection '{gmail_collection}'."

        serialized = "\n\n".join(
            (f"Source: {doc.metadata}\nContent: {doc.page_content}")
            for doc in gmail_docs
        )
        return serialized

    @tool()
    def extract_debtor_name_loe(query: str):
        """Extract debtor name from bankruptcy petition PDFs"""
        if not session_id:
            return "No session_id available. Please start a session or upload a PDF first."

        pdf_collection = f"bankruptcy_knowledge_{session_id}"
        pdf_docs = search_vectorstore(query, collection_name=pdf_collection, k=15)
        if not pdf_docs:
            return f"No relevant passages found in collection '{pdf_collection}'."

        serialized = "\n\n".join(
            (f"Source: {doc.metadata}\nContent: {doc.page_content}")
            for doc in pdf_docs
        )
        return serialized

    @tool()
    def extract_case_number_loe(query: str):
        """Extract case number from bankruptcy petition PDFs"""
        if not session_id:
            return "No session_id available. Please start a session or upload a PDF first."

        pdf_collection = f"bankruptcy_knowledge_{session_id}"
        pdf_docs = search_vectorstore(query, collection_name=pdf_collection, k=15)
        if not pdf_docs:
            return f"No relevant passages found in collection '{pdf_collection}'."

        serialized = "\n\n".join(
            (f"Source: {doc.metadata}\nContent: {doc.page_content}")
            for doc in pdf_docs
        )
        return serialized

    return [
        extract_trustee_name_loe,
        extract_chapter_number_loe,
        extract_judge_initial_loe,
        extract_debtor_name_loe,
        extract_case_number_loe,
    ]


