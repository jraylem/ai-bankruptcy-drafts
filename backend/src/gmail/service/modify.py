# src/gmail/agents/modify.py
from ..agents import GmailMotionModifyAgent


# Called by: tasks/orchestrator.py, tasks/extractors.py
def generate_payload_modify_for_session_gmail(
    session_id: str,
    user_hint: str = (
        "Find court district, debtor name, case number with judge initials, chapter, "
        "confirmation date, docket entries, and delinquency information for motion to modify."
    ),
    modification_type: str = "delinquent",
) -> dict:
    """
    Generate the payload JSON for a session using the GmailMotionModifyAgent (motion to modify).

    Args:
        session_id: Session identifier
        user_hint: Hint for the AI extraction
        modification_type: Type of modification - 'delinquent', 'creditor_alteration', or 'both'

    Returns status dict with payload or error information.
    """
    try:
        print(f"INFO: Generating motion modify payload JSON for session {session_id} using Gmail (type: {modification_type})")

        gmail_motion_modify_agent = GmailMotionModifyAgent(
            session_id=session_id,
            modification_type=modification_type
        )

        payload_result = gmail_motion_modify_agent.extract_payload(user_hint=user_hint)

        if payload_result.get("status") == "completed":
            import json

            payload_data = payload_result.get("payload")
            payload_json = json.dumps(payload_data) if isinstance(payload_data, dict) else payload_data

            return {
                "status": "success",
                "payload": payload_json,
                "message": "Motion modify payload generated successfully from Gmail data",
            }
        else:
            return {
                "status": "failed",
                "payload": None,
                "error": payload_result.get("error", "Unknown error"),
                "message": "Error generating motion modify payload",
            }
    except Exception as payload_error:
        print(f"ERROR: Motion modify payload generation failed for {session_id}: {str(payload_error)}")
        return {
            "status": "failed",
            "payload": None,
            "error": str(payload_error),
            "message": "Error generating motion modify payload",
        }
