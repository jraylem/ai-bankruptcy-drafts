from typing import Optional, Dict
from langchain_core.tools import tool
from ...chatbot.vectorestore import search_vectorstore

# Called by: GmailMotionExtendAgent (agents/extend.py)
def motion_extend_gmail_tool(session_id: Optional[str] = None):
    """
    Individual tools for motion extend payload extraction using Gmail + petition.

    - Petition (bankruptcy_knowledge_<session_id>) for:
      court_district_extend, debtor_name_extend, petition_date_extend
    - Gmail (gmail_<session_id>) for:
      case_number_extend (with judge initial), dismissed_case_number_extend,
      docket_entry_number_extend, trustees_reason_extend, dismissal_date_extend,
      chapter_extend
    """

    @tool()
    def extract_court_district_extend(query: str):
        """Extract court district from bankruptcy petition PDFs"""
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
    def extract_debtor_name_extend(query: str):
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
    def extract_petition_date_extend(query: str):
        """Extract petition date from bankruptcy petition PDFs"""
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
    def extract_case_number_extend(query: str):
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
    def extract_court_division_extend(query: str):
        """
        Extract court division from Gmail emails for this case.
        Look for hearing notices or court addresses to find the division.
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
    def extract_dismissed_case_number_extend(query: str):
        """Extract dismissed case number (base, without judge initial) from main Gmail emails"""
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
    def extract_dismissed_case_number_with_judge_extend(query: str):
        """Extract dismissed case number with judge initial from dismissed case Gmail emails"""
        if not session_id:
            return "No session_id available. Please start a session or ingest dismissed case Gmail emails first."

        gmail_dismissed_collection = f"gmail_dismissed_{session_id}"
        gmail_docs = search_vectorstore(query, collection_name=gmail_dismissed_collection, k=15)
        if not gmail_docs:
            return f"No relevant passages found in collection '{gmail_dismissed_collection}'. Make sure dismissed case emails have been ingested."

        serialized = "\n\n".join(
            (f"Source: {doc.metadata}\nContent: {doc.page_content}")
            for doc in gmail_docs
        )
        return serialized

    @tool()
    def extract_docket_entry_number_extend(query: str):
        """Extract docket entry number from dismissed case Gmail emails"""
        if not session_id:
            return "No session_id available. Please start a session or ingest dismissed case Gmail emails first."

        gmail_dismissed_collection = f"gmail_dismissed_{session_id}"
        gmail_docs = search_vectorstore(query, collection_name=gmail_dismissed_collection, k=15)
        if not gmail_docs:
            return f"No relevant passages found in collection '{gmail_dismissed_collection}'. Make sure dismissed case emails have been ingested."

        serialized = "\n\n".join(
            (f"Source: {doc.metadata}\nContent: {doc.page_content}")
            for doc in gmail_docs
        )
        return serialized

    @tool()
    def extract_trustees_reason_extend(query: str):
        """Extract trustee's reason from Gmail emails"""
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
    def extract_dismissal_date_extend(query: str):
        """Extract dismissal date from Gmail emails"""
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
    def extract_chapter_extend(query: str):
        """Extract chapter from Gmail emails"""
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
        extract_court_district_extend,
        extract_debtor_name_extend,
        extract_petition_date_extend,
        extract_case_number_extend,
        extract_court_division_extend,
        extract_dismissed_case_number_extend,
        extract_dismissed_case_number_with_judge_extend,
        extract_docket_entry_number_extend,
        extract_trustees_reason_extend,
        extract_dismissal_date_extend,
        extract_chapter_extend,
    ]


