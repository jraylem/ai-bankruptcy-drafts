from typing import Optional, Dict
from langchain_core.tools import tool
from ...chatbot.vectorestore import search_vectorstore

# Called by: GmailMotionDelayAgent (agents/delay.py)
def motion_delay_gmail_tool(session_id: Optional[str] = None):
    """
    Individual tools for motion delay payload extraction using Gmail + petition.

    - Petition (bankruptcy_knowledge_<session_id>) for:
      debtor_name_delay, case_number_delay, date_filed_delay, vehicle_delay, vin_delay,
      house_delay, address_delay, creditors_delay
    - Gmail (gmail_<session_id>) for:
      chapter_number_delay, judge_initial_delay, concluded_meeting_date_delay
    """

    @tool()
    def extract_debtor_name_delay(query: str):
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
    def extract_case_number_delay(query: str):
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

    @tool()
    def extract_date_filed_delay(query: str):
        """Extract date filed from bankruptcy petition PDFs"""
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
    def extract_vehicle_delay(query: str):
        """Extract vehicle information from bankruptcy petition PDFs"""
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
    def extract_vin_delay(query: str):
        """Extract VIN from bankruptcy petition PDFs"""
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
    def extract_house_delay(query: str):
        """Extract house/real estate information from bankruptcy petition PDFs"""
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
    def extract_address_delay(query: str):
        """Extract address from bankruptcy petition PDFs"""
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
    def extract_creditors_delay(query: str):
        """Extract creditors from bankruptcy petition PDFs"""
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
    def extract_chapter_number_delay(query: str):
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
    def extract_judge_initial_delay(query: str):
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
    def extract_concluded_meeting_date_delay(query: str):
        """Extract concluded meeting date from Gmail emails (case records)"""
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
        extract_debtor_name_delay,
        extract_case_number_delay,
        extract_date_filed_delay,
        extract_vehicle_delay,
        extract_vin_delay,
        extract_house_delay,
        extract_address_delay,
        extract_creditors_delay,
        extract_chapter_number_delay,
        extract_judge_initial_delay,
        extract_concluded_meeting_date_delay,
    ]


