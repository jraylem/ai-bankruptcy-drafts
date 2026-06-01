import json

# src/gmail/extractor.py
from ..extractor import search_and_extract_subject_email
# src/gmail/agents/withdraw.py, src/gmail/agents/hearing_extract.py
from ..agents import GmailMotionWithdrawAgent, GmailHearingExtractAgent
# src/gmail/prompts/hearing_extract.py
from ..prompts import HEARING_EXTRACT_FIELDS_WITHDRAW
# src/gmail/service/withdraw.py
from .withdraw import generate_payload_withdraw_for_session_gmail


# Called by: tasks/extractors.py
def generate_payload_withdraw_from_hearing_for_session_gmail(
    session_id: str,
    user_hint: str = (
        "Find case number with judge initial, debtor name, chapter, judge, and current address for motion to withdraw."
    ),
) -> dict:
    """
    Generate motion withdraw payload enriched with DocketNumber and TrusteeCalendar
    extracted from the latest original 'Notice of Hearing' Gmail email via Claude Haiku.

    Uses GmailMotionWithdrawAgent directly for base fields (same as
    generate_payload_withdraw_for_session_gmail), then fetches the hearing email
    and extracts two additional fields via a single direct Haiku call.
    """
    try:
        # Step 1 — base withdraw fields via GmailMotionWithdrawAgent (mirrors generate_payload_withdraw_for_session_gmail)
        print(f"INFO: Generating motion withdraw payload JSON for session {session_id} using Gmail")
        gmail_motion_withdraw_agent = GmailMotionWithdrawAgent(session_id=session_id)
        payload_result = gmail_motion_withdraw_agent.extract_payload(user_hint=user_hint)

        if payload_result.get("status") != "completed":
            return {
                "status": "failed",
                "order_withdraw_payload": None,
                "error": payload_result.get("error", "Unknown error"),
                "message": "Error generating motion withdraw payload",
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
        docket_text_filter = "Motion to Withdraw"
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
            hearing_fields = hearing_agent.extract(hearing_email["body"], HEARING_EXTRACT_FIELDS_WITHDRAW)

        # Step 5 — build final mapped payload with correct field names for the order document
        order_withdraw_payload = {
            "DebtorName":      base_payload.get("DebtorName", "N/A"),
            "CaseNumber":      base_payload.get("CaseNumber", "N/A"),
            "ChapterNumber":   base_payload.get("Chapter", base_payload.get("ChapterNumber", "N/A")),
            "MotionAddress":   base_payload.get("DebtorCurrentAddy", "N/A"),
            "DocketNumber":    hearing_fields.get("DocketNumber", "N/A"),
            # "IfExParte":     "N/A", - remove based on the updated document - order_motion_withdraw.docx
            "TrusteeCalendar": hearing_fields.get("TrusteeCalendar", "N/A"),
        }

        return {
            "status": "success",
            "order_withdraw_payload": json.dumps(order_withdraw_payload),
            "message": "Motion withdraw payload with hearing fields generated successfully",
        }

    except Exception as e:
        print(f"ERROR: Motion withdraw payload generation failed for {session_id}: {str(e)}")
        return {
            "status": "failed",
            "order_withdraw_payload": None,
            "error": str(e),
            "message": "Error generating motion withdraw payload",
        }
