from typing import Optional

# src/gmail/agents/notice_withdraw.py
from ..agents import GmailNoticeWithdrawAgent


# Called by: tasks/extractors.py
def generate_payload_notice_withdraw_for_session_gmail(
    session_id: str,
    user_hint: str = (
        "Find case number, debtor name from petition, and chapter, judge initial, document title from Gmail for notice to withdraw."
    ),
    docket_number: Optional[int] = None,
) -> dict:
    """
    Generate the payload JSON for a session using the GmailNoticeWithdrawAgent.
    Returns status dict with payload or error information.
    """
    try:
        print(
            f"INFO: Generating notice to withdraw payload JSON for session {session_id} using Gmail"
        )

        gmail_notice_agent = GmailNoticeWithdrawAgent(session_id=session_id)
        payload_result = gmail_notice_agent.extract_payload(
            user_hint=user_hint, docket_number=docket_number
        )

        if payload_result.get("status") == "completed":
            import json

            payload_data = payload_result.get("payload") or {}

            # Set ECFNumber from docket_number parameter if provided (aligns with existing service behavior)
            if docket_number is not None:
                payload_data["ECFNumber"] = str(docket_number)
            else:
                payload_data["ECFNumber"] = "N/A"

            payload_json = json.dumps(payload_data) if isinstance(payload_data, dict) else payload_data

            return {
                "status": "success",
                "payload": payload_json,
                "message": "Notice to withdraw payload generated successfully from Gmail data",
            }
        else:
            return {
                "status": "failed",
                "payload": None,
                "error": payload_result.get("error", "Unknown error"),
                "message": "Error generating notice to withdraw payload",
            }
    except Exception as payload_error:
        print(
            f"ERROR: Notice to withdraw payload generation failed for {session_id}: {str(payload_error)}"
        )
        return {
            "status": "failed",
            "payload": None,
            "error": str(payload_error),
            "message": "Error generating notice to withdraw payload",
        }
