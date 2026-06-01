import json
# src/gmail/extractor.py
from ..extractor import search_and_extract_subject_email
# src/gmail/agents/order_extend.py
from ..agents import GmailOrderExtendAgent, GmailHearingExtractAgent
# src/gmail/prompts/hearing_extract.py
from ..prompts import HEARING_EXTRACT_FIELDS_EXTEND


# Called by: tasks/extractors.py → OrderExtendExtractor
def generate_order_extend_payload_for_session_gmail(
    session_id: str,
    user_hint: str = "Find case number, dismissed case number, docket entry number, trustee's reason, dismissal date, and chapter information.",
) -> dict:
    """
    Generate ONLY the order_extend_payload from Gmail data.
    Derives DebtorName, CaseNumber, Chapter from GmailOrderExtendAgent;
    DocketMotion extracted from Notice of Hearing email.

    Returns:
        Dict with keys:
        - status: "success" or "failed"
        - order_extend_payload: JSON string
        - message / error
    """
    try:
        print(f"INFO: Generating order extend payload only for session {session_id} using Gmail")
        agent = GmailOrderExtendAgent(session_id=session_id)
        result = agent.extract_payload(user_hint=user_hint)

        if result.get("status") != "completed":
            return {
                "status": "failed",
                "order_extend_payload": None,
                "error": result.get("error", "GmailOrderExtendAgent did not complete"),
                "message": "Failed to generate order extend payload",
            }

        agent_payload = result.get("payload", {})

        # Derive base case number (strip judge initial suffix, e.g. "25-14980-PDR" → "25-14980")
        case_number_full = agent_payload.get("CaseNumber", "")
        case_number = "-".join(case_number_full.split("-")[:2]) if case_number_full else ""

        # Fetch the latest "Notice of Hearing" email for Motion to Extend
        subject_title = "Notice of Hearing"
        docket_text_filter = "Motion to Extend"
        hearing_email = search_and_extract_subject_email(
            case_number,
            subject_title,
            docket_text_filter=docket_text_filter,
        )

        if not hearing_email:
            print(f"[warn] No 'Notice of Hearing' email found for case {case_number}, new fields will be N/A")
            hearing_fields = {"DocketNumber": "N/A", "TrusteeCalendar": "N/A"}
        else:
            hearing_agent = GmailHearingExtractAgent()
            hearing_fields = hearing_agent.extract(hearing_email["body"], HEARING_EXTRACT_FIELDS_EXTEND)

        order_payload = {
            "DebtorName":        (agent_payload.get("DebtorName") or "N/A").strip() or "N/A",
            "CaseNumber":        (agent_payload.get("CaseNumber") or "N/A").strip() or "N/A",
            "Chapter":           (agent_payload.get("Chapter") or "N/A").strip() or "N/A",
            "CalendarDate":      (agent_payload.get("CalendarDate") or "N/A").strip() or "N/A",
            "granted":           True,
            "OptionalConditions": "N/A",
            "DocketMotion":      (hearing_fields.get("DocketNumber", "N/A") or "N/A").strip() or "N/A",
            "expedited":         (agent_payload.get("expedited") or "N/A").strip() or "N/A",
        }
        order_payload_json = json.dumps(order_payload)
        print(f"Order extend payload (dedicated): {order_payload}")

        return {
            "status": "success",
            "order_extend_payload": order_payload_json,
            "message": "Successfully generated Order extend payload generated from Gmail data",
        }
    except Exception as e:
        print(f"ERROR: Order extend payload generation failed for {session_id}: {str(e)}")
        return {
            "status": "failed",
            "order_extend_payload": None,
            "error": str(e),
            "message": "Error generating order extend payload",
        }
