import json
import re  # used by _extract_mailing_section
from typing import Optional

# src/gmail/extractor.py
from ..extractor import search_latest_court_mail
# src/gmail/agents/cert_service.py, src/gmail/agents/hearing_extract.py
from ..agents import GmailMotionServiceAgent, GmailHearingExtractAgent
# src/gmail/prompts/cert_service.py
from ..prompts import (
    HEARING_EXTRACT_FIELDS_CERT_SERVICE_TRUSTEE,
    HEARING_EXTRACT_FIELDS_CERT_SERVICE_HEARING,
)


def _extract_mailing_section(body: str) -> str:
    """
    Extract the raw 'Notice will be electronically mailed to:' block from a
    court NEF email body.  Returns everything between that header and the
    matching 'Notice will not be electronically mailed to:' line, trimmed.
    Returns an empty string if the section is not found.
    """
    match = re.search(
        r'Notice will be electronically mailed to:(.*?)(?=\S+\s+Notice will not be electronically mailed to:|Notice will not be electronically mailed to:)',
        body,
        re.DOTALL | re.IGNORECASE,
    )
    if match:
        return match.group(1).strip()
    return ""


# Called by: tasks/extractors.py (direct) + all _with_service_ composites (L3A, L3B, L3C)
def generate_payload_service_for_session_gmail(
    session_id: str,
    user_hint: str = "Find case number, debtor name, and chapter information for certificate of service.",
    motion_context: str = None,
) -> dict:
    """
    Generate certificate of service payload from Gmail data.

    Step 1 — GmailMotionServiceAgent: base fields
              (CaseNumber, DebtorName, CourtDistrict, Chapter, CurrentDate)
    Step 2 — derive base case_number (strip judge initial)
    Step 3 — fetch latest "Notice of Electronic Filing" email for the case;
              extract the raw "Notice will be electronically mailed to:" block
              into trustee_fields (plain text, parsed by downstream logic)
    Step 4 — build and return final payload
    """
    try:
        # Step 1 — base fields via GmailMotionServiceAgent
        print(f"INFO: Generating motion service payload for session {session_id} using Gmail")
        agent = GmailMotionServiceAgent(session_id=session_id)
        payload_result = agent.extract_payload(user_hint=user_hint)

        if payload_result.get("status") != "completed":
            return {
                "status": "failed",
                "payload": None,
                "error": payload_result.get("error", "Unknown error"),
                "message": "Error generating motion service payload",
            }

        base_payload = payload_result.get("payload", {})
        if not isinstance(base_payload, dict):
            try:
                base_payload = json.loads(base_payload)
            except Exception:
                base_payload = {}

        # Step 2 — derive base case_number (strip judge initial, e.g. "25-14980-PDR" → "25-14980")
        case_number_full = base_payload.get("CaseNumber", "")
        case_number = "-".join(case_number_full.split("-")[:2]) if case_number_full else ""

        # Also derive base case_number from PDF extraction (used as fallback below)
        case_number_pdf = base_payload.get("CaseNumberPDF", "")
        #case_number_pdf = "-".join(case_number_pdf_full.split("-")[:2]) if case_number_pdf_full else ""

        # Step 3 — fetch latest court mail and extract the mailing-list section
        court_mail = search_latest_court_mail(case_number)
        if not court_mail and case_number_pdf and case_number_pdf != case_number:
            print(f"[warn] No court mail found for case {case_number}, retrying with CaseNumberPDF: {case_number_pdf}")
            court_mail = search_latest_court_mail(case_number_pdf)
        if not court_mail:
            print(f"[warn] No court mail found for case {case_number}, mailing section will be N/A")
            trustee_fields = ""
        else:
            trustee_fields = _extract_mailing_section(court_mail["body"])
            if not trustee_fields:
                print(f"[warn] Could not extract mailing section from court mail for case {case_number}")

        # Step 4 — extract TrusteeName / TrustEmail / USTemail from the mailing section
        if trustee_fields:
            trustee_agent = GmailHearingExtractAgent()
            trustee_extracted = trustee_agent.extract(trustee_fields, HEARING_EXTRACT_FIELDS_CERT_SERVICE_TRUSTEE)
            trustee_name      = trustee_extracted.get("TrusteeName",     "N/A")
            trust_email       = trustee_extracted.get("TrustEmail",      "N/A")
            us_trustee_email  = trustee_extracted.get("USTemail",        "N/A")
            misc_mail_listings = trustee_extracted.get("MiscMailListings", "N/A")
        else:
            trustee_name       = "N/A"
            trust_email        = "N/A"
            us_trustee_email   = "N/A"
            misc_mail_listings = "N/A"

        # Step 5 — extract DocketMotion from the full court mail body via Claude
        if court_mail:
            hearing_agent = GmailHearingExtractAgent()
            hearing_extracted = hearing_agent.extract(court_mail["body"], HEARING_EXTRACT_FIELDS_CERT_SERVICE_HEARING)
            docket_motion = hearing_extracted.get("DocketMotion", "N/A")
        else:
            docket_motion = "N/A"

        # Step 6 — build final payload
        # MiscMailListings: Claude may return a list — deduplicate by name (case-insensitive), serialize
        if isinstance(misc_mail_listings, list):
            seen_names = set()
            deduped = []
            for item in misc_mail_listings:
                name_key = item.split("|")[0].strip().lower() if "|" in item else item.strip().lower()
                if name_key not in seen_names:
                    seen_names.add(name_key)
                    deduped.append(item)
            misc_str = json.dumps(deduped)
        else:
            misc_str = misc_mail_listings or "N/A"

        final_payload = {
            "CaseNumber":        base_payload.get("CaseNumber", "N/A"),
            "DebtorName":        base_payload.get("DebtorName", "N/A"),
            "CourtDistrict":     base_payload.get("CourtDistrict", "N/A"),
            "Chapter":           base_payload.get("Chapter", "N/A"),
            "CurrentDate":       base_payload.get("CurrentDate", "N/A"),
            "MotionType":        motion_context or "N/A",
            "TrusteeName":       trustee_name,
            "TrustEmail":        trust_email,
            "USTemail":          us_trustee_email,
            "MiscMailListings":  misc_str,
            "DocketMotion":      docket_motion,
            "IfNoticeofHearing": "N/A",
            "WasOrWere":         "N/A",
        }

        print(f"Motion service payload: {final_payload}")
        return {
            "status": "success",
            "payload": json.dumps(final_payload),
            "message": "Motion service payload generated successfully from Gmail data",
        }

    except Exception as e:
        print(f"ERROR: Motion service payload generation failed for {session_id}: {str(e)}")
        return {
            "status": "failed",
            "payload": None,
            "error": str(e),
            "message": "Error generating motion service payload",
        }
