# src/gmail/extractor.py
from ..extractor import search_and_extract_subject_email
# src/gmail/agents/value.py, src/gmail/agents/order_value.py, src/gmail/agents/hearing_extract.py
from ..agents import GmailMotionValueAgent, GmailHearingExtractAgent
# src/gmail/prompts/hearing_extract.py
from ..prompts import (
    HEARING_EXTRACT_FIELDS_VALUE,
    PETITION_EXTRACT_FIELDS_DATE_FILED,
    PROOF_OF_CLAIM_EXTRACT_FIELDS_AMOUNT,
)

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

        client = anthropic.Anthropic(api_key=api_key)

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


def _compute_price(value: str, percent: str) -> str:
    """
    Ask Claude to compute the total amount paid over a 60-month loan for the
    given Value at the given Prime Rate percentage.
    Returns a formatted dollar string (e.g. '$14,250.00') or 'N/A' on error.
    """
    import re
    import anthropic
    from ...ai_models import CLAUDE_MODEL_STANDARD
    from ...config import settings

    try:
        if not value or value == "N/A" or not percent or percent == "N/A":
            return "N/A"

        api_key = settings.ANTHROPIC_API_KEY
        if not api_key:
            raise ValueError("Anthropic API key not configured.")

        client = anthropic.Anthropic(api_key=api_key, max_retries=5)

        prompt = (
            f"Over a 60-month duration, how much total will be paid for a {value} loan "
            f"at a {percent}% Prime Rate. "
            "IMPORTANT: Your ENTIRE response must be the total dollar amount and nothing else. "
            "No markdown, no bold, no explanation, no extra text. "
            "If you cannot compute the value, return 'N/A' immediately. "
            "Example: $14,250.00"
        )

        response = client.messages.create(
            model=CLAUDE_MODEL_STANDARD,
            max_tokens=100,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = ""
        for block in response.content:
            if block.type == "text":
                raw = block.text.strip()

        # Extract first dollar amount from the response
        match = re.search(r"\$[\d,]+\.?\d*", raw)
        if match:
            return match.group(0)

        print(f"[warn] _compute_price: could not parse dollar amount from response: {raw}")
        return "N/A"

    except Exception as e:
        print(f"[error] _compute_price: {e}")
        return "N/A"


# Called by: generate_payload_value_with_service_for_session_gmail (below),
#            tasks/orchestrator.py, tasks/extractors.py
def generate_payload_value_for_session_gmail(
    session_id: str,
    user_hint: str = "Find case number, debtor name, vehicle information, creditor details.",
) -> dict:
    """
    Generate motion value payload from Gmail data.
    Uses GmailMotionValueAgent for base field extraction, then enriches with
    hearing email, petition date, prime rate, and proof of claim data.
    """
    try:
        import json

        # Step 1 — base motion value fields via GmailMotionValueAgent
        print(f"INFO: Generating motion value payload for session {session_id} using Claude")
        value_agent = GmailMotionValueAgent(session_id=session_id)
        payload_result = value_agent.extract_payload(user_hint=user_hint)

        if payload_result.get("status") != "completed":
            return {
                "status": "failed",
                "payload": None,
                "error": payload_result.get("error", "Unknown error"),
                "message": "Error generating motion value payload",
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

        # Step 5 — fetch the oldest original "Voluntary Petition" email for the Date Filed
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

        # Step 7 — look up U.S. prime loan rate for DateFiled
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
            with_claim = "No"
        else:
            claim_agent = GmailHearingExtractAgent()
            claim_fields = claim_agent.extract(hearing_email_2["body"], PROOF_OF_CLAIM_EXTRACT_FIELDS_AMOUNT)
            with_claim = "Yes"

        # Step 10 — compute Price via Claude: total paid over 60-month loan
        value_for_price = base_payload.get("Value", "N/A")
        price_str = _compute_price(value_for_price, percent)
        print(f"[info] Computed Price (60-month total) for Value={value_for_price}, Percent={percent}: {price_str}")

        # Step 11 — build final mapped motion value payload
        final_payload = {
            "CaseNumber":      base_payload.get("CaseNumber", "N/A"),
            "ChapterNumber":   base_payload.get("ChapterNumber", base_payload.get("Chapter", "N/A")),
            "DebtorName":      base_payload.get("DebtorName", "N/A"),
            "Creditor":        creditor,
            "DocketNumber":    hearing_fields.get("DocketNumber", "N/A"),
            "TrusteeCalendar": hearing_fields.get("TrusteeCalendar", "N/A"),
            "CarModel":        base_payload.get("CarModel", "N/A"),
            "VinModel":        base_payload.get("VinModel", "N/A"),
            "Odometer":        base_payload.get("Odometer", "N/A"),
            "Value":           base_payload.get("Value", "N/A"),
            "ValueMethod":     base_payload.get("ValueMethod", "N/A"),
            "ClaimSlot":       claim_fields.get("ClaimSlot", "N/A"),
            "DateFiled":       date_filed,
            "Percent":         percent.replace("%", "").strip() if percent != "N/A" else percent,
            "Price":           price_str,
            "WithClaim":       with_claim,
        }

        print(f"Motion value payload: {final_payload}")
        return {
            "status": "success",
            "payload": json.dumps(final_payload),
            "message": "Successfully generated motion value payload from Gmail data",
        }

    except Exception as e:
        print(f"ERROR: Motion value payload generation failed for {session_id}: {str(e)}")
        return {
            "status": "failed",
            "payload": None,
            "error": str(e),
            "message": "Error generating motion value payload",
        }