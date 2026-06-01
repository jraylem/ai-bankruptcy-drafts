from typing import Dict, Any, Optional

# src/gmail/extractor.py
from ..extractor import search_and_extract_emails
# src/chatbot/vectorestore.py
from ...chatbot.vectorestore import process_and_store_documents, clear_collection
# src/chatbot/agent.py
from ...chatbot.agent import CaseNumberAgent

# Called by: tasks/pleading_tasks.py, courtdrive/routes.py, all route do_work() functions
gmail_ingestion_status: Dict[str, Dict[str, Any]] = {}


# Called by: tasks/pleading_tasks.py, courtdrive/routes.py, all route do_work() functions
def ingest_gmail_emails_for_session(
    session_id: str,
    case_number: Optional[str] = None,
    debtor_name: Optional[str] = None,
    force_reingest: bool = False
) -> Dict[str, Any]:
    """
    Search Gmail for emails related to the case and store them in vectorstore.

    Args:
        session_id: Session ID for tracking
        case_number: Case number to search for (if None, will extract from petition)
        debtor_name: Debtor name to search for (if None, will extract from petition)
        force_reingest: If True, clear existing collection and re-ingest

    Returns:
        Dictionary with status and result information
    """
    try:
        collection_name = f"gmail_{session_id}"

        # Check if already ingested
        ingestion_key = f"{session_id}:gmail"
        if not force_reingest and ingestion_key in gmail_ingestion_status:
            status = gmail_ingestion_status[ingestion_key]
            if status.get("status") == "completed":
                print(f"[info] Gmail emails already ingested for session {session_id}")
                return {
                    "status": "completed",
                    "result": status.get("result", {}),
                    "message": "Gmail emails already ingested"
                }

        # Extract case number if not provided
        if not case_number:
            print(f"[info] Extracting case number from petition for session {session_id}")
            case_agent = CaseNumberAgent(session_id=session_id)
            case_result = case_agent.extract_case_number()
            if case_result.get("status") == "completed" and case_result.get("case_number"):
                case_number = case_result.get("case_number", "").strip()
                print(f"[info] Extracted case number: {case_number}")
            else:
                return {
                    "status": "failed",
                    "error": "Failed to extract case number from petition",
                    "message": case_result.get("error", "Unknown error")
                }

        # Clear collection if force_reingest
        if force_reingest:
            print(f"[info] Clearing existing Gmail collection: {collection_name}")
            clear_result = clear_collection(collection_name)
            if not clear_result.get("success"):
                print(f"[warn] Failed to clear collection: {clear_result.get('error')}")

        # Update status to running
        gmail_ingestion_status[ingestion_key] = {
            "status": "running",
            "session_id": session_id,
            "case_number": case_number,
            "debtor_name": debtor_name
        }

        # Search and extract emails using core extractor logic
        try:
            documents = search_and_extract_emails(case_number)
        except Exception as e:
            gmail_ingestion_status[ingestion_key] = {
                "status": "failed",
                "error": str(e)
            }
            return {
                "status": "failed",
                "error": str(e),
                "message": f"Failed to search/extract Gmail emails: {str(e)}"
            }

        # Add debtor_name to metadata if available
        if debtor_name:
            for doc in documents:
                doc.metadata["debtor_name"] = debtor_name

        emails_processed = len(documents)

        # Store documents in vectorstore
        print(f"[info] Storing {len(documents)} email documents in vectorstore: {collection_name}")
        store_result = process_and_store_documents(documents, collection_name)

        if not store_result.get("success"):
            gmail_ingestion_status[ingestion_key] = {
                "status": "failed",
                "error": store_result.get("error", "Failed to store documents"),
            }
            return {
                "status": "failed",
                "error": store_result.get("error", "Failed to store documents"),
                "message": "Failed to store emails in vectorstore",
            }

        # Update status to completed
        result = {
            "total_emails_found": emails_processed,
            "total_emails_processed": emails_processed,
            "total_documents_stored": store_result.get("stored_count", 0),
            "case_number": case_number,
            "debtor_name": debtor_name,
            "collection_name": collection_name
        }

        gmail_ingestion_status[ingestion_key] = {
            "status": "completed",
            "result": result
        }

        print(f"[info] Gmail ingestion completed for session {session_id}: {emails_processed} emails stored")

        return {
            "status": "completed",
            "result": result,
            "message": f"Successfully ingested {emails_processed} emails"
        }

    except Exception as e:
        ingestion_key = f"{session_id}:gmail"
        gmail_ingestion_status[ingestion_key] = {
            "status": "failed",
            "error": str(e)
        }
        print(f"[error] Gmail ingestion failed for session {session_id}: {e}")
        return {
            "status": "failed",
            "error": str(e),
            "message": f"Gmail ingestion error: {str(e)}"
        }

# Called by: GmailMotionExtendAgent (agents/extend.py) — invoked during extend payload extraction
def ingest_dismissed_case_emails_for_session(
    session_id: str,
    dismissed_case_number: str,
    force_reingest: bool = False
) -> Dict[str, Any]:
    """
    Search Gmail for emails related to the dismissed case and store them in vectorstore.

    Args:
        session_id: Session ID for tracking
        dismissed_case_number: Dismissed case number to search for (e.g., "25-14980")
        force_reingest: If True, clear existing collection and re-ingest

    Returns:
        Dictionary with status and result information
    """
    try:
        collection_name = f"gmail_dismissed_{session_id}"

        # Check if already ingested
        ingestion_key = f"{session_id}:gmail_dismissed"
        if not force_reingest and ingestion_key in gmail_ingestion_status:
            status = gmail_ingestion_status[ingestion_key]
            if status.get("status") == "completed":
                print(f"[info] Dismissed case emails already ingested for session {session_id}")
                return {
                    "status": "completed",
                    "result": status.get("result", {}),
                    "message": "Dismissed case emails already ingested"
                }

        # Clear collection if force_reingest
        if force_reingest:
            print(f"[info] Clearing existing dismissed case Gmail collection: {collection_name}")
            clear_result = clear_collection(collection_name)
            if not clear_result.get("success"):
                print(f"[warn] Failed to clear collection: {clear_result.get('error')}")

        # Update status to running
        gmail_ingestion_status[ingestion_key] = {
            "status": "running",
            "session_id": session_id,
            "dismissed_case_number": dismissed_case_number
        }

        # Search and extract emails using core extractor logic
        try:
            documents = search_and_extract_emails(dismissed_case_number)
        except Exception as e:
            gmail_ingestion_status[ingestion_key] = {
                "status": "failed",
                "error": str(e)
            }
            return {
                "status": "failed",
                "error": str(e),
                "message": f"Failed to search/extract dismissed case Gmail emails: {str(e)}"
            }

        # Add dismissed_case_number to metadata
        for doc in documents:
            doc.metadata["dismissed_case_number"] = dismissed_case_number

        emails_processed = len(documents)

        # Store documents in vectorstore
        print(f"[info] Storing {len(documents)} dismissed case email documents in vectorstore: {collection_name}")
        store_result = process_and_store_documents(documents, collection_name)

        if not store_result.get("success"):
            gmail_ingestion_status[ingestion_key] = {
                "status": "failed",
                "error": store_result.get("error", "Failed to store documents"),
            }
            return {
                "status": "failed",
                "error": store_result.get("error", "Failed to store documents"),
                "message": "Failed to store dismissed case emails in vectorstore",
            }

        # Update status to completed
        result = {
            "total_emails_found": emails_processed,
            "total_emails_processed": emails_processed,
            "total_documents_stored": store_result.get("stored_count", 0),
            "dismissed_case_number": dismissed_case_number,
            "collection_name": collection_name
        }

        gmail_ingestion_status[ingestion_key] = {
            "status": "completed",
            "result": result
        }

        print(f"[info] Dismissed case Gmail ingestion completed for session {session_id}: {emails_processed} emails stored")

        return {
            "status": "completed",
            "result": result,
            "message": f"Successfully ingested {emails_processed} dismissed case emails"
        }

    except Exception as e:
        ingestion_key = f"{session_id}:gmail_dismissed"
        gmail_ingestion_status[ingestion_key] = {
            "status": "failed",
            "error": str(e)
        }
        print(f"[error] Dismissed case Gmail ingestion failed for session {session_id}: {e}")
        return {
            "status": "failed",
            "error": str(e),
            "message": f"Dismissed case Gmail ingestion error: {str(e)}"
        }

# Called by: courtdrive/routes.py, all route polling loops
def check_gmail_ingestion_status(session_id: str) -> Dict[str, Any]:
    """
    Check the status of Gmail ingestion for a session.

    Args:
        session_id: Session ID to check

    Returns:
        Dictionary with status information
    """
    ingestion_key = f"{session_id}:gmail"

    if ingestion_key not in gmail_ingestion_status:
        return {
            "status": "not_started",
            "message": "Gmail ingestion not started"
        }

    status_info = gmail_ingestion_status[ingestion_key]
    status_value = status_info.get("status")

    if status_value == "completed":
        return {
            "status": "ready",
            "message": "Gmail ingestion completed",
            "result": status_info.get("result", {})
        }
    elif status_value == "running":
        return {
            "status": "running",
            "message": "Gmail ingestion in progress"
        }
    elif status_value == "failed":
        return {
            "status": "failed",
            "message": status_info.get("error", "Gmail ingestion failed"),
            "error": status_info.get("error")
        }
    else:
        return {
            "status": "unknown",
            "message": f"Unknown status: {status_value}"
        }
