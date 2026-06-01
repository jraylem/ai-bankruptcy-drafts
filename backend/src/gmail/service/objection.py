# src/gmail/agents/loe.py, objection_claim.py
from ..agents import (
    GmailMotionLOEAgent,
    GmailMotionObjectionClaimAgent,
)


# Called by: tasks/orchestrator.py, tasks/extractors.py
def generate_payload_LOE_for_session_gmail(
    session_id: str,
    user_hint: str = "Find case number, debtor name, trustee name, chapter number from Gmail."
) -> dict:
    """
    Generate the payload JSON for a session using the GmailMotionLOEAgent (LOE motion).
    Returns status dict with payload or error information.
    """
    try:
        print(f"INFO: Generating LOE payload JSON for session {session_id} using Gmail")

        gmail_motion_loe_agent = GmailMotionLOEAgent(session_id=session_id)

        payload_result = gmail_motion_loe_agent.extract_payload(user_hint=user_hint)

        if payload_result.get("status") == "completed":
            import json
            payload_data = payload_result.get("payload")
            payload_json = json.dumps(payload_data) if isinstance(payload_data, dict) else payload_data

            return {
                "status": "success",
                "payload": payload_json,
                "message": "LOE payload generated successfully from Gmail data"
            }
        else:
            return {
                "status": "failed",
                "payload": None,
                "error": payload_result.get("error", "Unknown error"),
                "message": "Error generating LOE payload"
            }
    except Exception as payload_error:
        print(f"ERROR: LOE payload generation failed for {session_id}: {str(payload_error)}")
        return {
            "status": "failed",
            "payload": None,
            "error": str(payload_error),
            "message": "Error generating LOE payload"
        }


# Called by: tasks/orchestrator.py
def generate_payload_objection_claim_for_session_gmail(
    session_id: str,
    user_hint: str = "Find case number, debtor name, and claim details from Proof of Claim emails.",
) -> dict:
    """
    Generate the payload JSON for a session using the GmailMotionObjectionClaimAgent (motion objection claim).
    Returns status dict with payload or error information.
    """
    try:
        print(f"INFO: Generating motion objection claim payload JSON for session {session_id} using Gmail")

        gmail_motion_objection_claim_agent = GmailMotionObjectionClaimAgent(session_id=session_id)

        payload_result = gmail_motion_objection_claim_agent.extract_payload(user_hint=user_hint)

        if payload_result.get("status") == "completed":
            import json

            payload_data = payload_result.get("payload")
            payload_json = json.dumps(payload_data) if isinstance(payload_data, dict) else payload_data

            return {
                "status": "success",
                "payload": payload_json,
                "message": "Motion objection claim payload generated successfully from Gmail data",
            }
        else:
            return {
                "status": "failed",
                "payload": None,
                "error": payload_result.get("error", "Unknown error"),
                "message": "Error generating motion objection claim payload",
            }
    except Exception as payload_error:
        print(f"ERROR: Motion objection claim payload generation failed for {session_id}: {str(payload_error)}")
        return {
            "status": "failed",
            "payload": None,
            "error": str(payload_error),
            "message": "Error generating motion objection claim payload",
        }
