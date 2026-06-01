# src/gmail/agents/waive.py
from ..agents import GmailMotionWaiveAgent

# Called by: generate_payload_waive_with_service_for_session_gmail (below),
#            tasks/orchestrator.py, tasks/extractors.py
def generate_payload_waive_for_session_gmail(
    session_id: str,
    user_hint: str = (
        "Find case number with judge initial, debtor name, chapter from Gmail, and date filed from petition for motion to waive."
    ),
) -> dict:
    """
    Generate the payload JSON for a session using the GmailMotionWaiveAgent (motion to waive).
    Returns status dict with payload or error information.
    """
    try:
        print(f"INFO: Generating motion waive payload JSON for session {session_id} using Gmail")

        gmail_motion_waive_agent = GmailMotionWaiveAgent(session_id=session_id)

        payload_result = gmail_motion_waive_agent.extract_payload(user_hint=user_hint)

        if payload_result.get("status") == "completed":
            import json

            payload_data = payload_result.get("payload")

            waive_payload = {
                "CaseNumber":            payload_data.get("CaseNumber", "N/A"),
                "Chapter":               payload_data.get("Chapter", "N/A"),
                "DebtorName":            payload_data.get("DebtorName", "N/A"),
                "DateOne":               payload_data.get("DateOne", "N/A"),
                "DateTwo":               payload_data.get("DateTwo", "N/A"),
                "EmploymentExplanation": payload_data.get("EmploymentExplanation", "N/A"),
            } if isinstance(payload_data, dict) else {}

            payload_json = json.dumps(waive_payload) if waive_payload else payload_data

            return {
                "status": "success",
                "payload": payload_json,
                "message": "Motion waive payload generated successfully from Gmail data",
            }
        else:
            return {
                "status": "failed",
                "payload": None,
                "error": payload_result.get("error", "Unknown error"),
                "message": "Error generating motion waive payload",
            }
    except Exception as payload_error:
        print(f"ERROR: Motion waive payload generation failed for {session_id}: {str(payload_error)}")
        return {
            "status": "failed",
            "payload": None,
            "error": str(payload_error),
            "message": "Error generating motion waive payload",
        }
