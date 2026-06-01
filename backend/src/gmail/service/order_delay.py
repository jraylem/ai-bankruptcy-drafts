import json

# src/gmail/extractor.py
from ..extractor import search_and_extract_subject_email
# src/gmail/agents/order_delay.py, src/gmail/agents/hearing_extract.py
from ..agents import GmailOrderDelayAgent, GmailHearingExtractAgent
# src/gmail/prompts/hearing_extract.py
from ..prompts import MOTION_EXTENSION_EXTRACT_FIELDS, MEETING_OF_CREDITORS_EXTRACT_FIELDS


# Called by: tasks/extractors.py
def generate_order_delay_payload_for_session_gmail(
    session_id: str,
    motion_user_hint: str = "Find case number, debtor name, and chapter.",
) -> dict:
    """
    Generate order delay payload from Gmail data.
    Extracts: DebtorName, CaseNumber, ChapterNumber, DocketNumber,
              OldDischargeability, OldDischargeabilityDatePlus30.
    Placeholders (N/A): WhyExtensionNeeded, WithMotion.
    """
    try:
        # Step 1 — base fields via GmailOrderDelayAgent
        print(f"INFO: Generating order delay payload for session {session_id}")
        delay_agent = GmailOrderDelayAgent(session_id=session_id)
        payload_result = delay_agent.extract_payload(user_hint=motion_user_hint)

        if payload_result.get("status") != "completed":
            return {
                "status": "failed",
                "order_delay_payload": None,
                "error": payload_result.get("error", "Unknown error"),
                "message": "Error generating order delay payload",
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

        # Step 3 — fetch the latest "Motion to Delay" email for DocketNumber
        delay_email = search_and_extract_subject_email(
            case_number,
            "Motion to Delay",
            #docket_text_filter="Motion to Delay",
        )

        if not delay_email:
            print(f"[warn] No 'Motion to Delay' email found for case {case_number}, DocketNumber will be N/A")
            docket_number = "N/A"
        else:
            # Step 4 — extract DocketNumber from "Document Number:" field
            hearing_agent = GmailHearingExtractAgent()
            hearing_fields = hearing_agent.extract(delay_email["body"], MOTION_EXTENSION_EXTRACT_FIELDS)
            docket_number = hearing_fields.get("DocketNumber", "N/A")
        
        # Step 5 — fetch "Meeting of Creditors" email to extract OldDischargeability
        creditors_email = search_and_extract_subject_email(
            case_number,
            "Meeting of Creditors",
            docket_text_filter="Dischargeability",
        )

        old_dischargeability = "N/A"
        old_dischargeability_plus_30 = "N/A"

        if not creditors_email:
            print(f"[warn] No 'Meeting of Creditors' email found for case {case_number}, OldDischargeability will be N/A")
        else:
            # Step 6 — extract OldDischargeability from "Last Day to Oppose Discharge or Dischargeability is" line
            creditors_agent = GmailHearingExtractAgent()
            creditors_fields = creditors_agent.extract(creditors_email["body"], MEETING_OF_CREDITORS_EXTRACT_FIELDS)
            raw_date = creditors_fields.get("OldDischargeability", "N/A")

            if raw_date and raw_date != "N/A":
                try:
                    from datetime import timedelta
                    from dateutil.parser import parse as _parse_date
                    parsed = _parse_date(raw_date)
                    old_dischargeability = parsed.strftime(f"%B {parsed.day}, %Y")
                    plus_30 = parsed + timedelta(days=30)
                    old_dischargeability_plus_30 = plus_30.strftime(f"%B {plus_30.day}, %Y")
                except Exception:
                    old_dischargeability = raw_date
                    old_dischargeability_plus_30 = "N/A"

        # Step 7 — build final payload
        order_delay_payload = {
            "DebtorName":                    base_payload.get("DebtorName", "N/A"),
            "CaseNumber":                    base_payload.get("CaseNumber", "N/A"),
            "ChapterNumber":                 base_payload.get("ChapterNumber", "N/A"),
            "District":                      base_payload.get("CourtDistrict", "N/A"),
            "DocketNumber":                  docket_number,
            "OldDischargeability":           old_dischargeability,
            "OldDischargeabilityDatePlus30": old_dischargeability_plus_30,
            "WhyExtensionNeeded":            "N/A",
            "WithMotion":                    True,
        }

        print(f"Order delay payload: {order_delay_payload}")
        return {
            "status": "success",
            "order_delay_payload": json.dumps(order_delay_payload),
            "message": "Successfully generated order delay payload from Gmail data",
        }

    except Exception as e:
        print(f"ERROR: Order delay payload generation failed for {session_id}: {str(e)}")
        return {
            "status": "failed",
            "order_delay_payload": None,
            "error": str(e),
            "message": "Error generating order delay payload",
        }
