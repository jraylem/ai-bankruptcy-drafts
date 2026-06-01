from typing import Optional
from langchain_core.tools import tool
from ..vectorestore import search_vectorstore

# Called by: CaseNumberAgent (agents/extractors.py)
def motion_modify_tool(session_id: Optional[str] = None):
    @tool()
    def extract_case_no_modify(query: str):
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

    return [extract_case_no_modify]
