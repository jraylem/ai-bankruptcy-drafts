# src/gmail/extractor.py
from ..extractor import search_and_extract_subject_email
# src/gmail/agents/suggestion.py, src/gmail/agents/hearing_extract.py
from ..agents import GmailMotionSuggestionAgent, GmailHearingExtractAgent
# src/gmail/prompts/hearing_extract.py
from ..prompts import PETITION_EXTRACT_FIELDS_DATE_FILED

from dataclasses import dataclass
import re
import anthropic
from ...ai_models import CLAUDE_MODEL_STANDARD, CLAUDE_TOOL_WEB_SEARCH
from ...config import settings


_STRICT = (
    "IMPORTANT: Your ENTIRE response must be the requested value and nothing else. "
    "No markdown, no bold, no bullet points, no headers, no extra context, no additional case info. "
    "If you cannot find the value, return 'N/A' immediately. "
    "Do NOT ask for clarification or provide additional information under any circumstances. "
    "One value. That is all."
)


@dataclass
class CourtAgencyInfo:
    county: str        # e.g. "Broward"
    circuit_number: str  # e.g. "17th"


def _query_claude(client: anthropic.Anthropic, system_prompt: str, user_content: str) -> str:
    """Send a single prompt to Claude with web search and return the first text block."""
    response = client.messages.create(
        model=CLAUDE_MODEL_STANDARD,
        max_tokens=100,
        system=system_prompt,
        tools=[{"type": CLAUDE_TOOL_WEB_SEARCH, "name": "web_search"}],
        messages=[{"role": "user", "content": user_content}],
    )
    for block in response.content:
        if block.type == "text":
            return block.text.strip()
    return "N/A"


def get_court_agency_info(court_agency: str) -> CourtAgencyInfo:
    """
    Given a court or agency name/address string, return its county and circuit number.

    Example input:
        "Broward County Circuit Court 201 SE 6th St Ste 136 Fort Lauderdale, FL 33301-3389"

    Returns:
        CourtAgencyInfo(county="Broward", circuit_number="17th")

    Falls back to "N/A" for any field that cannot be determined or on error.
    """
    prompts = {
        "county": (
            "You are a precise legal assistant. "
            "You will be given a court or agency name. "
            "Use web search to determine what county that court belongs to. "
            "Return ONLY the county name WITHOUT the word 'County' (e.g. 'Broward', 'Marion', 'Palm Beach'). "
            "Do NOT include 'County', the state, city, or any other text — just the name. "
            "If the county cannot be determined, return 'N/A'. "
            + _STRICT
        ),
        "circuit_number": (
            "You are a precise legal assistant. "
            "You will be given a court or agency name. "
            "Use web search to determine the circuit number that court belongs to. "
            "Return ONLY the circuit number with its ordinal suffix (e.g. '17th', '11th', '4th', '1st', '2nd', '3rd'). "
            "Do NOT include 'Circuit', the court name, or any other text — just the ordinal number. "
            "If the circuit number cannot be determined, return 'N/A'. "
            + _STRICT
        ),
    }

    try:
        api_key = settings.ANTHROPIC_API_KEY
        if not api_key:
            raise ValueError("Anthropic API key not configured.")

        client = anthropic.Anthropic(api_key=api_key)

        county = _query_claude(client, prompts["county"], court_agency)
        circuit_number = _query_claude(client, prompts["circuit_number"], court_agency)

        # Sanitise county — strip any accidental "County" suffix
        county = re.sub(r"\s*county\s*$", "", county, flags=re.IGNORECASE).strip() or "N/A"

        # Sanitise circuit_number — ensure it looks like an ordinal (e.g. "17th")
        if not re.fullmatch(r"\d+(st|nd|rd|th)", circuit_number, flags=re.IGNORECASE):
            print(f"[warn] get_court_agency_info: unexpected circuit_number format: {circuit_number!r}")
            # circuit_number = "N/A"

        return CourtAgencyInfo(county=county, circuit_number=circuit_number)

    except Exception as e:
        print(f"[error] get_court_agency_info: {e}")
        return CourtAgencyInfo(county="N/A", circuit_number="N/A")

# Called by: generate_payload_suggestion_with_service_for_session_gmail (below),
#            tasks/orchestrator.py, tasks/extractors.py
def generate_payload_suggestion_for_session_gmail(
    session_id: str,
    user_hint: str = "Find case number, debtor name, creditor, date filed, judge initial from Gmail."
) -> dict:
    """
    Generate the payload JSON for a session using the GmailMotionSuggestionAgent (suggestion motion).
    Returns status dict with payload or error information.
    """
    try:
        print(f"INFO: Generating suggestion payload JSON for session {session_id} using Gmail")

        gmail_motion_suggestion_agent = GmailMotionSuggestionAgent(session_id=session_id)

        payload_result = gmail_motion_suggestion_agent.extract_payload(user_hint=user_hint)

        if payload_result.get("status") == "completed":
            import json
            payload_data = payload_result.get("payload")
            base_payload = payload_data if isinstance(payload_data, dict) else {}
            if not base_payload and isinstance(payload_data, str):
                try:
                    base_payload = json.loads(payload_data)
                except Exception:
                    base_payload = {}

            # Derive BKCaseNumber from CaseNumber (strip judge initial suffix, e.g. "25-14980-PDR" → "25-14980")
            case_number_full = base_payload.get("CaseNumber", "")
            bk_case_number = "-".join(case_number_full.split("-")[:2]) if case_number_full else "N/A"

            # Resolve DateFiled: format if present, otherwise fallback to "Voluntary Petition" email
            date_filed_raw = base_payload.get("DateFiled", "N/A")
            if date_filed_raw and date_filed_raw != "N/A":
                try:
                    from dateutil.parser import parse as _parse_date
                    parsed = _parse_date(date_filed_raw)
                    date_filed = parsed.strftime(f"%B {parsed.day}, %Y")
                except Exception:
                    date_filed = date_filed_raw
            else:
                petition_email = search_and_extract_subject_email(
                    bk_case_number,
                    "Voluntary Petition",
                    oldest=True,
                )
                if not petition_email:
                    print(f"[warn] No 'Voluntary Petition' email found for case {bk_case_number}, DateFiled will be N/A")
                    date_filed = "N/A"
                else:
                    petition_agent = GmailHearingExtractAgent()
                    petition_fields = petition_agent.extract(petition_email["body"], PETITION_EXTRACT_FIELDS_DATE_FILED)
                    raw = petition_fields.get("DateFiled", "N/A")
                    if raw and raw != "N/A":
                        try:
                            from dateutil.parser import parse as _parse_date
                            parsed = _parse_date(raw)
                            date_filed = parsed.strftime(f"%B {parsed.day}, %Y")
                        except Exception:
                            date_filed = raw
                    else:
                        date_filed = "N/A"

            # Derive County and CircuitNumber from CourtAgency if not already present
            court_agency = base_payload.get("CourtAgency", "N/A")
            county = base_payload.get("County", "N/A")
            circuit_number = base_payload.get("CircuitNumber", "N/A")

            if court_agency and court_agency != "N/A":
                if county == "N/A" or circuit_number == "N/A":
                    court_info = get_court_agency_info(court_agency)
                    if county == "N/A":
                        county = court_info.county
                    if circuit_number == "N/A":
                        circuit_number = court_info.circuit_number

            suggestion_payload = {
                "CaseNumber":     base_payload.get("CaseNumberVS", "N/A"), #not 25-21322 should be CACE22014610 under versus
                "DebtorName":     base_payload.get("DebtorName", "N/A"),
                "Creditor":       base_payload.get("Creditor", "N/A"),
                "CourtAgency":    court_agency,
                "County":         county,
                "CircuitNumber":  circuit_number,
                "District":       base_payload.get("District", "N/A"),
                "BKCaseNumber":   bk_case_number,
                "DateFiled":      date_filed,
            }

            print(f"Suggestion payload: {suggestion_payload}")
            return {
                "status": "success",
                "payload": json.dumps(suggestion_payload),
                "message": "Suggestion payload generated successfully from Gmail data"
            }
        else:
            return {
                "status": "failed",
                "payload": None,
                "error": payload_result.get("error", "Unknown error"),
                "message": "Error generating suggestion payload"
            }
    except Exception as payload_error:
        print(f"ERROR: Suggestion payload generation failed for {session_id}: {str(payload_error)}")
        return {
            "status": "failed",
            "payload": None,
            "error": str(payload_error),
            "message": "Error generating suggestion payload"
        }