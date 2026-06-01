from typing import Optional
from langchain_core.tools import tool
from ..vectorestore import search_vectorstore

# Called by: ChatAgent (agents/chat.py), ReviewAgent (agents/review.py), ExtractorsAgent (agents/extractors.py)
def context_tool(session_id: Optional[str] = None):
    @tool()
    def retrieve_bankruptcy_context(query: str):
        """
        Use this tool to retrieve context from the Florida bankruptcy rules, trustee checklists,
        and petition best practices.
        """

        retrieved_docs = search_vectorstore(query)

        serialized = "\n\n".join(
            (f"Source: {doc.metadata}\nContent: {doc.page_content}")
            for doc in retrieved_docs
        )

        return serialized or "No relevant context found in global knowledge base."

    @tool()
    def query_uploaded_file(query: str):
        """
        Use this tool to query the user's uploaded bankruptcy petition PDF(s) for the current session.
        Searches the collection named "bankruptcy_knowledge_<session_id>".
        """

        if not session_id:
            return "No session_id available for querying uploaded files. Please start a session or upload a PDF first."

        collection_name = f"bankruptcy_knowledge_{session_id}"
        retrieved_docs = search_vectorstore(query, collection_name=collection_name, k=4)

        if not retrieved_docs:
            return f"No relevant passages found in collection '{collection_name}'."

        serialized = "\n\n".join(
            (f"Source: {doc.metadata}\nContent: {doc.page_content}")
            for doc in retrieved_docs
        )

        return serialized

    @tool()
    def query_gmail(query: str):
        """
        Use this tool to query the user's courtmail docket data for the current session.
        Searches the collection named "gmail_<session_id>".
        """

        if not session_id:
            return "No session_id available for querying Gmail. Please start a session first."

        collection_name = f"gmail_{session_id}"
        retrieved_docs = search_vectorstore(query, collection_name=collection_name, k=4)

        if not retrieved_docs:
            return f"No relevant passages found in collection '{collection_name}'."

        serialized = "\n\n".join(
            (f"Source: {doc.metadata}\nContent: {doc.page_content}")
            for doc in retrieved_docs
        )

        return serialized

    @tool()
    def query_generated_motions(query: str):
        """
        Use this tool to query previously generated motions or documents for the current session.
        Searches the collection named "generated_motions_<session_id>".
        """

        if not session_id:
            return "No session_id available for querying generated motions. Please start a session first."

        collection_name = f"generated_motions_{session_id}"
        retrieved_docs = search_vectorstore(query, collection_name=collection_name, k=4)

        if not retrieved_docs:
            return f"No relevant passages found in collection '{collection_name}'."

        serialized = "\n\n".join(
            (f"Source: {doc.metadata}\nContent: {doc.page_content}")
            for doc in retrieved_docs
        )

        return serialized

    return [retrieve_bankruptcy_context, query_uploaded_file, query_gmail, query_generated_motions]


# Called by: ChatAgent (agents/chat.py)
def loe_supporting_tool(session_id: Optional[str] = None):
    """
    Tool for querying LOE supporting documents (bank statements, receipts, etc.)
    that the user uploaded and chose to store permanently.
    """

    @tool()
    def query_loe_supporting_docs(query: str):
        """
        Search LOE supporting documents uploaded by the user.
        These include bank statements, receipts, invoices, and other documents
        the user provided as evidence for their Letter of Explanation.

        Use this tool when the user asks about:
        - Bank statements or transactions they uploaded
        - Receipts or invoices they provided
        - Any supporting documentation for previous LOE letters
        - Details from documents they attached to explain their circumstances
        """
        if not session_id:
            return "No session_id available. Please start a session first."

        collection_name = f"loe_supporting_{session_id}"
        retrieved_docs = search_vectorstore(query, collection_name=collection_name, k=10)

        if not retrieved_docs:
            return "No LOE supporting documents found for this session. The user may not have uploaded any documents with 'Store for AI to refer to again later' enabled."

        serialized = "\n\n".join(
            (f"Document: {doc.metadata.get('filename', 'unknown')} | Type: {doc.metadata.get('file_type', 'unknown')}\nContent: {doc.page_content}")
            for doc in retrieved_docs
        )

        return serialized

    return [query_loe_supporting_docs]
