from typing import Optional, Dict
from langchain_core.tools import tool
from ...chatbot.vectorestore import search_vectorstore

# Called by: GmailMotionExParteExtensionAgent (agents/ex_parte_extension.py)
def motion_ex_parte_extension_gmail_tool(session_id: Optional[str] = None):
    """
    Individual tools for ex parte motion for extension payload extraction using Gmail + petition.

    - Petition (bankruptcy_knowledge_<session_id>) for:
      debtor_name_ex_parte_extension, case_number_ex_parte_extension, date_filed_ex_parte_extension
    - Gmail (gmail_<session_id>) for:
      chapter_number_ex_parte_extension, judge_ex_parte_extension, meeting_date_ex_parte_extension
    """

    @tool()
    def extract_debtor_name_ex_parte_extension(query: str):
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
    def extract_case_number_ex_parte_extension(query: str):
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
    def extract_date_filed_ex_parte_extension(query: str):
        """Extract date filed from bankruptcy petition PDFs"""
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
    def extract_chapter_number_ex_parte_extension(query: str):
        """Extract chapter number from Gmail emails (case details)"""
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
    def extract_judge_ex_parte_extension(query: str):
        """
        Extract judge initial from Gmail emails related to the case.

        Expects a collection named gmail_{session_id} to contain case-related emails.
        The judge initial should be extracted from case numbers in the format xx-xxxxx-XXX
        (e.g., "25-22321-CLC" where "CLC" is the judge initial).
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
    def extract_meeting_date_ex_parte_extension(query: str):
        """Extract meeting of creditors date from Gmail emails (case notices)"""
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
        extract_debtor_name_ex_parte_extension,
        extract_case_number_ex_parte_extension,
        extract_chapter_number_ex_parte_extension,
        extract_judge_ex_parte_extension,
        extract_date_filed_ex_parte_extension,
        extract_meeting_date_ex_parte_extension,
    ]


