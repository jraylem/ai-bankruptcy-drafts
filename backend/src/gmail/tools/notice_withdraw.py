from typing import Optional, Dict
from langchain_core.tools import tool
from ...chatbot.vectorestore import search_vectorstore

# Called by: GmailNoticeWithdrawAgent (agents/notice_withdraw.py)
def notice_withdraw_gmail_tool(session_id: Optional[str] = None):
    """
    Individual tools for notice to withdraw payload extraction using Gmail + petition.

    - Petition (bankruptcy_knowledge_<session_id>) for:
      debtor_name_notice_withdraw, case_number_notice_withdraw
    - Gmail (gmail_<session_id>) for:
      chapter_notice_withdraw, judge_notice_withdraw, document_title_notice_withdraw
    """

    @tool()
    def extract_debtor_name_notice_withdraw(query: str):
        """Extract debtor name from bankruptcy petition PDFs"""
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
    def extract_case_number_notice_withdraw(query: str):
        """Extract case number from bankruptcy petition PDFs"""
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
    def extract_chapter_notice_withdraw(query: str):
        """Extract chapter from Gmail emails (case details)"""
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
    def extract_judge_notice_withdraw(query: str):
        """
        Extract judge initial from Gmail emails related to the case.

        Expects a collection named gmail_{session_id} to contain case-related emails.
        The judge initial should be extracted from case numbers in the format xx-xxxxx-XXX
        (e.g., "25-22321-CLC" -> "CLC").
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
    def extract_document_title_notice_withdraw(query: str):
        """Extract document title from Gmail emails (docket notice / filed by debtor)"""
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
        extract_debtor_name_notice_withdraw,
        extract_case_number_notice_withdraw,
        extract_chapter_notice_withdraw,
        extract_judge_notice_withdraw,
        extract_document_title_notice_withdraw,
    ]


