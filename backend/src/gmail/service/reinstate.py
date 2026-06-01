import json

# src/gmail/extractor.py
from ..extractor import search_and_extract_subject_email
# src/gmail/agents/reinstate.py, src/gmail/agents/hearing_extract.py
from ..agents import GmailMotionReinstateAgent, GmailHearingExtractAgent
# src/gmail/prompts/hearing_extract.py
from ..prompts import PETITION_EXTRACT_FIELDS_DATE_FILED, DISMISS_EXTRACT_FIELDS_REINSTATE

# Called by: tasks/orchestrator.py, tasks/extractors.py
def generate_payload_reinstate_for_session_gmail(
    session_id: str,
    user_hint: str = (
        "Find case number and debtor name from petition, and chapter number from Gmail for motion to reinstate."
    ),
) -> dict:
    """
    Generate motion reinstate payload enriched with DateFiled extracted from the oldest
    'Voluntary Petition' Gmail email via Claude Haiku.

    Uses GmailMotionReinstateAgent for base fields (DebtorName, CaseNumber, ChapterNumb),
    then fetches the petition email and extracts DateFiled via a single direct Haiku call.
    DismissedDate, DismissalReason, and WhyDismissedDetailed are set to 'N/A' for now.
    """
    try:
        # Step 1 — base reinstate fields via GmailMotionReinstateAgent
        print(f"INFO: Generating motion reinstate payload JSON for session {session_id} using Gmail")
        gmail_motion_reinstate_agent = GmailMotionReinstateAgent(session_id=session_id)
        payload_result = gmail_motion_reinstate_agent.extract_payload(user_hint=user_hint)

        if payload_result.get("status") != "completed":
            return {
                "status": "failed",
                "payload": None,
                "error": payload_result.get("error", "Unknown error"),
                "message": "Error generating motion reinstate payload",
            }

        payload_data = payload_result.get("payload")
        base_payload = payload_data if isinstance(payload_data, dict) else {}
        if not base_payload and isinstance(payload_data, str):
            try:
                base_payload = json.loads(payload_data)
            except Exception:
                base_payload = {}

        # Step 2 — derive base case number (strip judge initial suffix, e.g. "25-14980-PDR" → "25-14980")
        case_number_full = base_payload.get("CaseNumber", "")
        case_number = "-".join(case_number_full.split("-")[:2]) if case_number_full else ""

        # Step 3 — fetch the oldest original "Voluntary Petition" email for DateFiled
        subject_title = "Voluntary Petition"
        petition_email = search_and_extract_subject_email(
            case_number,
            subject_title,
            docket_text_filter="Voluntary Petition",
            oldest=True,
        )

        if not petition_email:
            print(f"[warn] No '{subject_title}' email found for case {case_number}, DateFiled will be N/A")
            date_filed = "N/A"
        else:
            # Step 4 — extract DateFiled via GmailHearingExtractAgent using Voluntary Petition email
            petition_agent = GmailHearingExtractAgent()
            petition_fields = petition_agent.extract(petition_email["body"], PETITION_EXTRACT_FIELDS_DATE_FILED)

            # Format DateFiled: "3/9/2026" → "March 9, 2026"
            date_filed_raw = petition_fields.get("DateFiled", "N/A")
            if date_filed_raw and date_filed_raw != "N/A":
                try:
                    from dateutil.parser import parse as _parse_date
                    parsed = _parse_date(date_filed_raw)
                    date_filed = parsed.strftime(f"%B {parsed.day}, %Y")
                except Exception:
                    date_filed = date_filed_raw
            else:
                date_filed = "N/A"
        
        # Step 4 — fetch the latest "Order Dismissing" email and extract DismissedDate and DismissalReason
        dismiss_email = search_and_extract_subject_email(
            case_number,
            "Order Dismissing",
            docket_text_filter="Order Dismissing",
            body_text_filter="The following transaction was received from",
        )

        if not dismiss_email:
            print(f"[warn] No 'Order Dismissing' email found for case {case_number}, dismiss fields will be N/A")
            dismissed_date = "N/A"
            dismissal_reason = "N/A"
        else:
            dismiss_agent = GmailHearingExtractAgent()
            dismiss_fields = dismiss_agent.extract(dismiss_email["body"], DISMISS_EXTRACT_FIELDS_REINSTATE)

            # Format DismissedDate: "09/16/2025" → "September 16, 2025"
            dismissed_date_raw = dismiss_fields.get("DismissedDate", "N/A")
            if dismissed_date_raw and dismissed_date_raw != "N/A":
                try:
                    from dateutil.parser import parse as _parse_date
                    parsed = _parse_date(dismissed_date_raw)
                    dismissed_date = parsed.strftime(f"%B {parsed.day}, %Y")
                except Exception:
                    dismissed_date = dismissed_date_raw
            else:
                dismissed_date = "N/A"

            dismissal_reason = dismiss_fields.get("DismissalReason", "N/A")

        # Step 5 — build final payload
        reinstate_payload = {
            "DebtorName":              base_payload.get("DebtorName", "N/A"),
            "CaseNumber":              base_payload.get("CaseNumber", "N/A"),
            "ChapterNumb":             base_payload.get("ChapterNumb", "N/A"),
            "DateFiled":               date_filed,
            "DismissedDate":           dismissed_date,
            "DismissalReason":         dismissal_reason,
            "WhyDismissedDetailed":    "N/A",
        }

        return {
            "status": "success",
            "payload": json.dumps(reinstate_payload),
            "message": "Motion reinstate payload generated successfully from Gmail data",
        }

    except Exception as e:
        print(f"ERROR: Motion reinstate payload generation failed for {session_id}: {str(e)}")
        return {
            "status": "failed",
            "payload": None,
            "error": str(e),
            "message": "Error generating motion reinstate payload",
        }
