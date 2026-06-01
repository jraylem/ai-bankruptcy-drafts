# src/gmail/extractor.py
from ..extractor import search_and_extract_subject_email
# src/gmail/agents/order_value.py, src/gmail/agents/hearing_extract.py
from ..agents import GmailOrderValueAgent, GmailHearingExtractAgent
# src/gmail/prompts/hearing_extract.py
from ..prompts import (
    HEARING_EXTRACT_FIELDS_VALUE,
    PETITION_EXTRACT_FIELDS_DATE_FILED,
    PROOF_OF_CLAIM_EXTRACT_FIELDS_AMOUNT,
)
# src/gmail/service/value.py
from .value import generate_payload_value_for_session_gmail


_CREDITOR_ALIASES: dict[str, str] = {
    "usaa fsb": "USAA Federal Savings Bank",
}


def _normalize_creditor(creditor: str) -> str:
    """
    Expand known creditor abbreviations to their full legal names for Gmail search matching.
    Returns the original string unchanged if no alias is found.
    """
    return _CREDITOR_ALIASES.get(creditor.strip().lower(), creditor)


def _get_us_prime_rate(date_str: str) -> str:
    """
    Return the U.S. Bank Prime Loan Rate in effect on the given date as a string (e.g. '6.75%').
    Uses Claude with web search tool so the model fetches live/accurate rate data.
    Falls back to 'N/A' on any error.
    """
    import re
    import anthropic
    from ...ai_models import CLAUDE_MODEL_STANDARD, CLAUDE_TOOL_WEB_SEARCH
    from ...config import settings

    try:
        api_key = settings.ANTHROPIC_API_KEY
        if not api_key:
            raise ValueError("Anthropic API key not configured.")

        client = anthropic.Anthropic(api_key=api_key, max_retries=5)

        prompt = (
            f"What was the U.S. Bank Prime Loan Rate on {date_str}? "
            "IMPORTANT: Your ENTIRE response must be the requested value and nothing else. "
            "No markdown, no bold, no bullet points, no headers, no extra context, no additional case info. "
            "If you cannot find the value, return 'N/A' immediately. "
            "Do NOT ask for clarification or provide additional information under any circumstances. "
            "One value. That is all. "
            "Example: 6.75%"
        )

        response = client.messages.create(
            model=CLAUDE_MODEL_STANDARD,
            max_tokens=100,
            tools=[{"type": CLAUDE_TOOL_WEB_SEARCH, "name": "web_search"}],
            messages=[{"role": "user", "content": prompt}],
        )

        # Extract the final text block from the response (after web search completes)
        raw = ""
        for block in response.content:
            if block.type == "text":
                raw = block.text.strip()

        # Extract the first percentage value from the response
        match = re.search(r"\d+\.?\d*%", raw)
        if match:
            return match.group(0)

        print(f"[warn] _get_us_prime_rate: could not parse percentage from response: {raw}")
        return "N/A"

    except Exception as e:
        print(f"[error] _get_us_prime_rate: {e}")
        return "N/A"


# Called by: tasks/extractors.py
def generate_order_value_payload_for_session_gmail(
    session_id: str,
    motion_user_hint: str = "Find case number, debtor name, vehicle information, creditor details.",
) -> dict:
    """
    Generate order value payload from Gmail data.
    Uses GmailOrderValueAgent (Claude Haiku) for all field extraction.
    """
    try:
        import json

        # Step 1 — base order value fields via GmailOrderValueAgent (Claude Haiku)
        print(f"INFO: Generating order value payload for session {session_id} using Claude")
        value_agent = GmailOrderValueAgent(session_id=session_id)
        payload_result = value_agent.extract_payload(user_hint=motion_user_hint)

        if payload_result.get("status") != "completed":
            return {
                "status": "failed",
                "order_value_payload": None,
                "error": payload_result.get("error", "Unknown error"),
                "message": "Error generating order value payload",
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
        docket_text_filter = "Motion to Value"
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
            hearing_fields = hearing_agent.extract(hearing_email["body"], HEARING_EXTRACT_FIELDS_VALUE)


        # Step 5 — fetch the oldest original "Voluntary Petition" email for the Date File
        subject_title_1 = "Voluntary Petition"
        petition_email_1 = search_and_extract_subject_email(
            case_number,
            subject_title_1,
            docket_text_filter="Voluntary Petition",
            oldest=True,
        )

        if not petition_email_1:
            print(f"[warn] No '{subject_title_1}' email found for case {case_number}, DateFiled will be N/A")
            date_filed = "N/A"
        else:
            # Step 6 — extract DateFiled via GmailHearingExtractAgent using Voluntary Petition email
            petition_agent = GmailHearingExtractAgent()
            petition_fields = petition_agent.extract(petition_email_1["body"], PETITION_EXTRACT_FIELDS_DATE_FILED)

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

        # Step 7 — look up U.S. prime loan rate for DateFiled from hardcoded table
        if date_filed and date_filed != "N/A":
            percent = _get_us_prime_rate(date_filed)
            print(f"[info] Prime loan rate for {date_filed}: {percent}")
        else:
            percent = "N/A"

        # Step 8 — fetch the "Proof of Claim" email for this creditor
        subject_title_2 = "Proof of ClaimCh-13"

        creditor = _normalize_creditor(base_payload.get("Creditor", "N/A"))

        hearing_email_2 = search_and_extract_subject_email(
            case_number,
            subject_title_2,
            creditor_text_filter=creditor or None,
        )

        # Step 9 — extract AmountClaimed / AmountSecured from Proof of Claim email
        claim_fields = {}
        if not hearing_email_2:
            print(f"[warn] No '{subject_title_2}' email found for case {case_number}, AmountClaimed/AmountSecured will be N/A")
        else:
            claim_agent = GmailHearingExtractAgent()
            claim_fields = claim_agent.extract(hearing_email_2["body"], PROOF_OF_CLAIM_EXTRACT_FIELDS_AMOUNT)

        # Step 10 — compute Value1 (AmountSecured) and Value2 (AmountClaimed - AmountSecured, floor 0)
        amount_claimed_raw = claim_fields.get("AmountClaimed", "N/A") or "N/A"
        amount_secured_raw = claim_fields.get("AmountSecured", "N/A") or "N/A"
        if amount_claimed_raw == "N/A" or amount_secured_raw == "N/A":
            value1_str = "N/A"
            value2_str = "N/A"
            value1 = None
            value2 = None
        else:
            try:
                amount_claimed = float(amount_claimed_raw.replace(",", ""))
                amount_secured = float(amount_secured_raw.replace(",", ""))
                value1 = amount_secured
                value2 = max(0.0, amount_claimed - amount_secured)
                value1_str = f"${value1:,.2f}"
                value2_str = f"${value2:,.2f}"
            except Exception:
                value1_str = "N/A"
                value2_str = "N/A"
                value1 = None
                value2 = None

        # Step 11 — compute Price_Yes Claim (total for "claim filed" path: (Value1 + Value2) × (1 + rate))
        try:
            rate = float(percent.replace("%", "").strip()) / 100
            price_yes = (value1 + value2) * (1 + rate)
            price_yes_str = f"${price_yes:,.2f}"
        except Exception:
            price_yes_str = "N/A"

        # Step 12 — compute Price_No Claim(no-claim path: Value × (1 + rate))
        try:
            value_raw = base_payload.get("Value", "0") or "0"
            value_amount = float(value_raw.replace("$", "").replace(",", "").strip())
            price_no = value_amount * (1 + rate)
            price_no_str = f"${price_no:,.2f}"
        except Exception:
            price_no_str = "N/A"

        # Step 13 — build final mapped order value payload
        order_value_payload = {
            "CaseNumber":      base_payload.get("CaseNumber", "N/A"),
            "ChapterNumber":   base_payload.get("ChapterNumber", base_payload.get("Chapter", "N/A")),
            "DebtorName":      base_payload.get("DebtorName", "N/A"),
            "Creditor":        creditor, #Creditor Full Name
            "DocketNumber":    hearing_fields.get("DocketNumber", "N/A"),
            "TrusteeCalendar": hearing_fields.get("TrusteeCalendar", "N/A"),
            "CarModel":        base_payload.get("CarModel", "N/A"),
            "VinModel":        base_payload.get("VinModel", "N/A"),
            "Odometer":        base_payload.get("Odometer", "N/A"),
            "Value":           base_payload.get("Value", "N/A"),
            "ClaimSlot":       claim_fields.get("ClaimSlot", "N/A"), #or base_payload.get("ClaimSlot", "N/A"),
            "DateFiled":       date_filed,
            "Value1":          value1_str,
            "Value2":          value2_str,
            "Percent":         percent.replace("%", "").strip() if percent != "N/A" else percent,
            "PriceYes":        price_yes_str,
            "PriceNo":         price_no_str,
            "WithClaim":       "N/A",
            "AmountClaimed":   amount_claimed_raw,
            "AmountSecured":   amount_secured_raw,
            "FinalPrice":      "N/A",
        }

        print(f"Order value payload: {order_value_payload}")
        return {
            "status": "success",
            "order_value_payload": json.dumps(order_value_payload),
            "message": "Successfully generated Order value payload from Gmail data",
        }

    except Exception as e:
        print(f"ERROR: Order value payload generation failed for {session_id}: {str(e)}")
        return {
            "status": "failed",
            "order_value_payload": None,
            "error": str(e),
            "message": "Error generating order value payload",
        }
