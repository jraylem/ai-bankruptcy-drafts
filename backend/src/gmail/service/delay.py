# src/gmail/agents/delay.py
from ..agents import GmailMotionDelayAgent


# Called by: tasks/orchestrator.py, tasks/extractors.py
def generate_payload_delay_for_session_gmail(
    session_id: str,
    user_hint: str = (
        "Find case number, debtor name, date filed, vehicle, VIN, house, address, creditors from petition, and chapter, judge initial, concluded meeting date from Gmail for motion to delay."
    ),
) -> dict:
    """
    Generate the payload JSON for a session using the GmailMotionDelayAgent (motion to delay).
    Returns status dict with payload or error information.
    """
    try:
        print(f"INFO: Generating motion delay payload JSON for session {session_id} using Gmail")

        gmail_motion_delay_agent = GmailMotionDelayAgent(session_id=session_id)

        payload_result = gmail_motion_delay_agent.extract_payload(user_hint=user_hint)

        if payload_result.get("status") == "completed":
            import json

            payload_data = payload_result.get("payload")
            payload_json = json.dumps(payload_data) if isinstance(payload_data, dict) else payload_data

            return {
                "status": "success",
                "payload": payload_json,
                "message": "Motion delay payload generated successfully from Gmail data",
            }
        else:
            return {
                "status": "failed",
                "payload": None,
                "error": payload_result.get("error", "Unknown error"),
                "message": "Error generating motion delay payload",
            }
    except Exception as payload_error:
        print(f"ERROR: Motion delay payload generation failed for {session_id}: {str(payload_error)}")
        return {
            "status": "failed",
            "payload": None,
            "error": str(payload_error),
            "message": "Error generating motion delay payload",
        }
