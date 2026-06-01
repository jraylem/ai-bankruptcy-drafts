import json

# src/gmail/extractor.py
from ..extractor import search_and_extract_subject_email
# src/gmail/agents/order_reinstate.py, src/gmail/agents/hearing_extract.py
from ..agents import GmailOrderReinstateAgent, GmailHearingExtractAgent
# src/gmail/prompts/hearing_extract.py
from ..prompts import HEARING_EXTRACT_FIELDS_REINSTATE


# Called by: tasks/extractors.py → OrderReinstateExtractor
def generate_payload_reinstate_from_hearing_for_session_gmail(
    session_id: str,
    user_hint: str = (
        "Find case number, debtor name, date filed from petition, and chapter, judge initial, dismissed date, dismissal reason from Gmail for order to reinstate."
    ),
) -> dict:
    """
    Generate order reinstate payload enriched with DocketNumber and TrusteeCalendar
    extracted from the latest original 'Notice of Hearing' Gmail email via Claude Haiku.

    Uses GmailOrderReinstateAgent for base fields, then fetches the hearing email
    and extracts two additional fields via a single direct Haiku call.
    """
    try:
        # Step 1 — base reinstate fields via GmailOrderReinstateAgent
        print(f"INFO: Generating order reinstate payload JSON for session {session_id} using Gmail")
        gmail_order_reinstate_agent = GmailOrderReinstateAgent(session_id=session_id)
        payload_result = gmail_order_reinstate_agent.extract_payload(user_hint=user_hint)

        if payload_result.get("status") != "completed":
            return {
                "status": "failed",
                "order_reinstate_payload": None,
                "error": payload_result.get("error", "Unknown error"),
                "message": "Error generating order reinstate payload",
            }

        payload_data = payload_result.get("payload")
        base_payload = payload_data if isinstance(payload_data, dict) else {}
        if not base_payload and isinstance(payload_data, str):
            try:
                base_payload = json.loads(payload_data)
            except Exception:
                base_payload = {}

        # Step 2 — derive base case number from payload (strip judge initial suffix, e.g. "25-14980-PDR" → "25-14980")
        case_number_full = base_payload.get("CaseNumber", "")
        case_number = "-".join(case_number_full.split("-")[:2]) if case_number_full else ""

        # Step 3 — fetch the latest original "Notice of Hearing" email for this motion type
        subject_title = "Notice of Hearing"
        docket_text_filter = "Motion to Reinstate"
        hearing_email = search_and_extract_subject_email(
            case_number,
            subject_title,
            docket_text_filter=docket_text_filter,
        )

        if not hearing_email:
            print(f"[warn] No 'Notice of Hearing' email found for case {case_number}, new fields will be N/A")
            hearing_fields = {"DocketNumber": "N/A", "TrusteeCalendar": "N/A"}
        else:
            # Step 4 — extract DocketNumber and TrusteeCalendar via GmailHearingExtractAgent
            hearing_agent = GmailHearingExtractAgent()
            hearing_fields = hearing_agent.extract(hearing_email["body"], HEARING_EXTRACT_FIELDS_REINSTATE)

        # Step 5 — build final mapped payload with correct field names for the order document
        order_reinstate_payload = {
            "DebtorName":      base_payload.get("DebtorName", "N/A"),
            "CaseNumber":      base_payload.get("CaseNumber", "N/A"),
            "ChapterNumber":   base_payload.get("ChapterNumb", base_payload.get("ChapterNumber", "N/A")),
            "DocketNumber":    hearing_fields.get("DocketNumber", "N/A"),
            "TrusteeCalendar": hearing_fields.get("TrusteeCalendar", "N/A"),
            "X1": "N/A",
            "X2": "N/A",
            "X3": "N/A",
        }

        return {
            "status": "success",
            "order_reinstate_payload": json.dumps(order_reinstate_payload),
            "message": "Order reinstate payload with hearing fields generated successfully",
        }

    except Exception as e:
        print(f"ERROR: Order reinstate payload generation failed for {session_id}: {str(e)}")
        return {
            "status": "failed",
            "order_reinstate_payload": None,
            "error": str(e),
            "message": "Error generating order reinstate payload",
        }
