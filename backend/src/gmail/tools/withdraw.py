from typing import Optional, Dict
from langchain_core.tools import tool
from ...chatbot.vectorestore import search_vectorstore

# Called by: GmailMotionWithdrawAgent (agents/withdraw.py)
def motion_withdraw_gmail_tool(session_id: Optional[str] = None):
    """
    Individual tools for motion withdraw payload extraction using Gmail + petition.

    - Petition (bankruptcy_knowledge_<session_id>) for:
      debtor_name_withdraw, debtor_current_addy_withdraw
    - Gmail (gmail_<session_id>) for:
      case_number_withdraw (with judge initial), chapter_withdraw, judge_initial_withdraw
    """

    @tool()
    def extract_debtor_name_withdraw(query: str):
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
    def extract_case_number_withdraw(query: str):
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
        
        serialized = "\n\n".join(
            (f"Source: {doc.metadata}\nContent: {doc.page_content}")
            for doc in gmail_docs
        )
        return serialized

    @tool()
    def extract_chapter_withdraw(query: str):
        """Extract chapter from Gmail emails (case details)"""
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
    def extract_judge_initial_withdraw(query: str):
        """
        Extract judge initial from Gmail emails for this case.
        
        Expects a collection named gmail_{session_id} to contain
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
    def extract_debtor_current_addy_withdraw(query: str):
        """Extract debtor current address from bankruptcy petition PDFs"""
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
    def extract_case_number_withdraw_pdf(query: str):
        """Extract case number from bankruptcy petition PDFs (PDF fallback for when Gmail returns N/A)"""
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
    def extract_chapter_withdraw_pdf(query: str):
        """Extract chapter number from bankruptcy petition PDFs (PDF fallback for when Gmail returns N/A)"""
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
        extract_debtor_name_withdraw,
        extract_case_number_withdraw,
        extract_chapter_withdraw,
        extract_judge_initial_withdraw,
        extract_debtor_current_addy_withdraw,
        extract_case_number_withdraw_pdf,
        extract_chapter_withdraw_pdf,
    ]


