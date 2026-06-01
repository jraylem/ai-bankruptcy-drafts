from typing import Optional, Dict
from langchain_core.tools import tool
from ...chatbot.vectorestore import search_vectorstore

# Called by: GmailMotionObjectionSustainNoUploadAgent (agents/order_sustaining_objection.py)
def motion_objection_sustain_no_upload_gmail_tool(session_id: Optional[str] = None):
    """
    Individual tools for order sustaining objection payload extraction using Gmail + petition (no upload).

    - Petition (bankruptcy_knowledge_<session_id>) for:
      debtor_name_objection_sustain, case_number_objection_sustain
    - Gmail (gmail_<session_id>) for:
      chapter_number_objection_sustain, judge_initial_objection_sustain,
      case_number_objection_sustain_gmail (fallback)
    """

    @tool()
    def extract_debtor_name_objection_sustain(query: str):
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
    def extract_case_number_objection_sustain(query: str):
        """Extract base case number (no judge initial) from bankruptcy petition PDFs"""
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
    def extract_chapter_number_objection_sustain(query: str):
        """Extract chapter number from Gmail emails (case details)"""
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
    def extract_judge_initial_objection_sustain(query: str):
        """
        Extract judge initial from Gmail emails for this case.

        Expects a collection named gmail_{session_id} to contain
        case-related emails (subjects and bodies).
        The judge initial should be extracted from case numbers in the format xx-xxxxx-XXX
        (e.g., "25-22288-PDR" where "PDR" is the judge initial).
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
    def extract_case_number_objection_sustain_gmail(query: str):
        """Extract full case number with judge initial from Gmail emails (fallback when judge initial is missing)"""
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

    return [
        extract_debtor_name_objection_sustain,
        extract_case_number_objection_sustain,
        extract_chapter_number_objection_sustain,
        extract_judge_initial_objection_sustain,
        extract_case_number_objection_sustain_gmail,
    ]


# Called by: GmailMotionObjectionSustainAgent (agents/order_sustaining_objection.py)
# Only slot number and creditor — base fields (debtor/case/chapter) come from the no-upload path
def motion_objection_sustain_gmail_tool(session_id: Optional[str] = None):
    """
    Tools for extracting SlotNumb and Creditor from the uploaded objection PDF.
    All other fields are sourced from petition PDF + Gmail via the no-upload path.
    """

    @tool()
    def extract_slot_numb_objection_sustain(query: str):
        """Extract slot number from objection PDF"""
        if not session_id:
            return "No session_id available. Please start a session or upload objection PDF first."

        objection_collection = f"objection_pdf_{session_id}"
        objection_docs = search_vectorstore(query, collection_name=objection_collection, k=15)
        if not objection_docs:
            return f"No relevant passages found in collection '{objection_collection}'."

        serialized = "\n\n".join(
            (f"Source: {doc.metadata}\nContent: {doc.page_content}")
            for doc in objection_docs
        )
        return serialized

    @tool()
    def extract_creditor_objection_sustain(query: str):
        """Extract creditor from objection PDF"""
        if not session_id:
            return "No session_id available. Please start a session or upload objection PDF first."

        objection_collection = f"objection_pdf_{session_id}"
        objection_docs = search_vectorstore(query, collection_name=objection_collection, k=15)
        if not objection_docs:
            return f"No relevant passages found in collection '{objection_collection}'."

        serialized = "\n\n".join(
            (f"Source: {doc.metadata}\nContent: {doc.page_content}")
            for doc in objection_docs
        )
        return serialized

    return [
        extract_slot_numb_objection_sustain,
        extract_creditor_objection_sustain,
    ]
