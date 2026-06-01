import json

# src/gmail/extractor.py
from ..extractor import search_and_extract_subject_email
# src/gmail/agents/order_extension.py, src/gmail/agents/hearing_extract.py
from ..agents import GmailOrderExtensionAgent, GmailHearingExtractAgent
# src/gmail/prompts/hearing_extract.py
from ..prompts import PETITION_EXTRACT_FIELDS_DATE_FILED, MOTION_EXTENSION_EXTRACT_FIELDS


# Called by: tasks/extractors.py
def generate_order_extension_payload_for_session_gmail(
    session_id: str,
    motion_user_hint: str = "Find case number, debtor name, and chapter.",
) -> dict:
    """
    Generate order extension payload from Gmail data.
    Extracts: DebtorName, CaseNumber, ChapterNumber, DocketNumber, DateFiledPlusFourteen.
    """
    try:
        # Step 1 — base fields via GmailOrderExtensionAgent
        print(f"INFO: Generating order extension payload for session {session_id}")
        extension_agent = GmailOrderExtensionAgent(session_id=session_id)
        payload_result = extension_agent.extract_payload(user_hint=motion_user_hint)

        if payload_result.get("status") != "completed":
            return {
                "status": "failed",
                "order_extension_payload": None,
                "error": payload_result.get("error", "Unknown error"),
                "message": "Error generating order extension payload",
            }

        payload_data = payload_result.get("payload")
        base_payload = payload_data if isinstance(payload_data, dict) else {}
        if not base_payload and isinstance(payload_data, str):
            try:
                base_payload = json.loads(payload_data)
            except Exception:
                base_payload = {}

        # Step 2 — strip judge initial suffix (e.g. "25-14980-PDR" → "25-14980")
        case_number_full = base_payload.get("CaseNumber", "")
        case_number = "-".join(case_number_full.split("-")[:2]) if case_number_full else ""

        # Step 3 — fetch the latest "Motion to Extend Time" email
        hearing_email = search_and_extract_subject_email(
            case_number,
            "Motion to Extend Time",
        )

        if not hearing_email:
            print(f"[warn] No 'Motion to Extend Time' email found for case {case_number}, DocketNumber will be N/A")
            docket_number = "N/A"
        else:
            # Step 4 — extract DocketNumber from "Document Number:" field
            hearing_agent = GmailHearingExtractAgent()
            hearing_fields = hearing_agent.extract(hearing_email["body"], MOTION_EXTENSION_EXTRACT_FIELDS)
            docket_number = hearing_fields.get("DocketNumber", "N/A")

        # Step 5 — fetch the oldest "Voluntary Petition" email for DateFiled
        petition_email = search_and_extract_subject_email(
            case_number,
            "Voluntary Petition",
            docket_text_filter="Voluntary Petition",
            oldest=True,
        )

        date_filed_raw = "N/A"
        if not petition_email:
            print(f"[warn] No 'Voluntary Petition' email found for case {case_number}, DateFiledPlusFourteen will be N/A")
            date_filed_plus_fourteen = "N/A"
        else:
            # Step 6 — extract DateFiled, then compute DateFiledPlusFourteen (+14 business days)
            petition_agent = GmailHearingExtractAgent()
            petition_fields = petition_agent.extract(petition_email["body"], PETITION_EXTRACT_FIELDS_DATE_FILED)

            date_filed_raw = petition_fields.get("DateFiled", "N/A")
            if date_filed_raw and date_filed_raw != "N/A":
                try:
                    from datetime import timedelta
                    from dateutil.parser import parse as _parse_date
                    parsed = _parse_date(date_filed_raw)
                    date_filed_raw = parsed.strftime(f"%B {parsed.day}, %Y")
                    # Add 14 business days (skip Saturday=5 and Sunday=6)
                    business_days_added = 0
                    current = parsed
                    while business_days_added < 14:
                        current += timedelta(days=1)
                        if current.weekday() < 5:
                            business_days_added += 1
                    date_filed_plus_fourteen = current.strftime(f"%B {current.day}, %Y")
                except Exception:
                    date_filed_plus_fourteen = "N/A"
            else:
                date_filed_plus_fourteen = "N/A"

        # Step 7 — build final payload
        order_extension_payload = {
            "DebtorName":           base_payload.get("DebtorName", "N/A"),
            "CaseNumber":           base_payload.get("CaseNumber", "N/A"),
            "ChapterNumber":        base_payload.get("ChapterNumber", "N/A"),
            "DocketNumber":         docket_number,
            "DateFiled":            date_filed_raw,
            "DateFiledPlusFourteen": date_filed_plus_fourteen,
        }

        print(f"Order extension payload: {order_extension_payload}")
        return {
            "status": "success",
            "order_extension_payload": json.dumps(order_extension_payload),
            "message": "Successfully generated order extension payload from Gmail data",
        }

    except Exception as e:
        print(f"ERROR: Order extension payload generation failed for {session_id}: {str(e)}")
        return {
            "status": "failed",
            "order_extension_payload": None,
            "error": str(e),
            "message": "Error generating order extension payload",
        }
