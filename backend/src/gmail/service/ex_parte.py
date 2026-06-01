# src/gmail/agents/ex_parte_extension.py
from ..agents import GmailMotionExParteExtensionAgent


# Called by: tasks/orchestrator.py, tasks/extractors.py
def generate_payload_ex_parte_extension_for_session_gmail(
    session_id: str,
    user_hint: str = (
        "Find case number, debtor name, date filed from petition, and chapter, judge initial, meeting date from Gmail for ex parte motion for extension."
    ),
) -> dict:
    """
    Generate the payload JSON for a session using the GmailMotionExParteExtensionAgent.
    Returns status dict with payload or error information.
    """
    try:
        print(
            f"INFO: Generating ex parte motion for extension payload JSON for session {session_id} using Gmail"
        )

        gmail_ex_parte_agent = GmailMotionExParteExtensionAgent(session_id=session_id)

        payload_result = gmail_ex_parte_agent.extract_payload(user_hint=user_hint)

        if payload_result.get("status") == "completed":
            import json

            payload_data = payload_result.get("payload")
            payload_json = json.dumps(payload_data) if isinstance(payload_data, dict) else payload_data

            return {
                "status": "success",
                "payload": payload_json,
                "message": "Ex parte motion for extension payload generated successfully from Gmail data",
            }
        else:
            return {
                "status": "failed",
                "payload": None,
                "error": payload_result.get("error", "Unknown error"),
                "message": "Error generating ex parte motion for extension payload",
            }
    except Exception as payload_error:
        print(
            f"ERROR: Ex parte motion for extension payload generation failed for {session_id}: {str(payload_error)}"
        )
        return {
            "status": "failed",
            "payload": None,
            "error": str(payload_error),
            "message": "Error generating ex parte motion for extension payload",
        }
