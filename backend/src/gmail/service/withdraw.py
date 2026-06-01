# src/gmail/agents/withdraw.py
from ..agents import GmailMotionWithdrawAgent


# Called by: tasks/orchestrator.py, tasks/extractors.py
def generate_payload_withdraw_for_session_gmail(
    session_id: str,
    user_hint: str = (
        "Find case number with judge initial, debtor name, chapter, judge, and current address for motion to withdraw."
    ),
) -> dict:
    """
    Generate the payload JSON for a session using the GmailMotionWithdrawAgent (motion to withdraw).
    Returns status dict with payload or error information.
    """
    try:
        print(f"INFO: Generating motion withdraw payload JSON for session {session_id} using Gmail")

        gmail_motion_withdraw_agent = GmailMotionWithdrawAgent(session_id=session_id)

        payload_result = gmail_motion_withdraw_agent.extract_payload(user_hint=user_hint)

        if payload_result.get("status") == "completed":
            import json

            payload_data = payload_result.get("payload")
            payload_json = json.dumps(payload_data) if isinstance(payload_data, dict) else payload_data

            return {
                "status": "success",
                "payload": payload_json,
                "message": "Motion withdraw payload generated successfully from Gmail data",
            }
        else:
            return {
                "status": "failed",
                "payload": None,
                "error": payload_result.get("error", "Unknown error"),
                "message": "Error generating motion withdraw payload",
            }
    except Exception as payload_error:
        print(f"ERROR: Motion withdraw payload generation failed for {session_id}: {str(payload_error)}")
        return {
            "status": "failed",
            "payload": None,
            "error": str(payload_error),
            "message": "Error generating motion withdraw payload",
        }
