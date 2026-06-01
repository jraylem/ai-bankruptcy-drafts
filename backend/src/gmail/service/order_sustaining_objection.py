import json

# src/gmail/extractor.py
from ..extractor import search_and_extract_subject_email, search_and_extract_all_subject_emails
# src/gmail/agents/order_sustaining_objection.py, src/gmail/agents/hearing_extract.py
from ..agents import GmailMotionObjectionSustainNoUploadAgent, GmailMotionObjectionSustainAgent, GmailHearingExtractAgent
# src/gmail/prompts/hearing_extract.py
from ..prompts import HEARING_EXTRACT_FIELDS_OBJECTION_SUSTAIN, OBJECTION_CLAIM_EMAIL_EXTRACT_FIELDS
# src/chatbot/vectorestore.py
from ...chatbot.vectorestore import search_vectorstore, clear_collection


def _deduplicate_objection_entries(
    slot_numbs: list, creditors: list, docket_numbers: list, trustee_calendars: list
) -> tuple[list, list, list, list]:
    """
    Deduplicate extracted email entries using all 4 fields as the composite key.
    If all 4 values for a row match an already-seen row, that row is dropped.
    If any field differs, the row is kept as a unique entry.
    """
    seen = set()
    out_slots, out_creditors, out_dockets, out_calendars = [], [], [], []
    for row in zip(slot_numbs, creditors, docket_numbers, trustee_calendars):
        if row not in seen:
            seen.add(row)
            out_slots.append(row[0])
            out_creditors.append(row[1])
            out_dockets.append(row[2])
            out_calendars.append(row[3])
    return out_slots, out_creditors, out_dockets, out_calendars


def _objection_pdf_uploaded(session_id: str) -> bool:
    """Return True if the user uploaded an objection PDF for this session."""
    docs = search_vectorstore("objection claim", collection_name=f"objection_pdf_{session_id}", k=1)
    return bool(docs)


# Called by: routes/stream.py, tasks/extractors.py → OrderSustainingObjectionExtractor
def generate_payload_objection_sustain_for_session_gmail(
    session_id: str,
    user_hint: str = "Find debtor name, case number, chapter, slot number, and creditor information.",
) -> dict:
    """
    Generate order sustaining objection payload.

    Base fields (DebtorName, CaseNo, Chapter) always come from the petition PDF
    and Gmail emails via GmailMotionObjectionSustainNoUploadAgent — same pattern
    as order_reinstate.

    If the user uploaded an objection PDF, SlotNumb and Creditor are extracted
    from it via GmailMotionObjectionSustainAgent. Otherwise both remain 'N/A'
    for the user to fill in manually.

    DocketNumber and TrusteeCalendar are always fetched from the latest
    'Notice of Hearing' email via GmailHearingExtractAgent.
    """
    try:
        # Step 1 — base fields from petition PDF + Gmail (always runs)
        print(f"INFO: Generating order sustaining objection payload for session {session_id}")
        base_agent = GmailMotionObjectionSustainNoUploadAgent(session_id=session_id)
        base_result = base_agent.extract_payload(user_hint=user_hint)

        if base_result.get("status") != "completed":
            return {
                "status": "failed",
                "order_sustaining_objection_payload": None,
                "error": base_result.get("error", "Unknown error"),
                "message": "Error generating base objection sustain fields",
            }

        base_payload = base_result.get("payload", {})
        if not isinstance(base_payload, dict):
            try:
                base_payload = json.loads(base_payload)
            except Exception:
                base_payload = {}

        # Step 2 — derive base case number (strip judge initial, e.g. "25-14980-PDR" → "25-14980")
        case_number_full = base_payload.get("CaseNo", "")
        case_number = "-".join(case_number_full.split("-")[:2]) if case_number_full else ""

        # Step 3 — SlotNumb + Creditor + DocketNumber + TrusteeCalendar:
        #           only extracted when objection PDF is uploaded; otherwise all N/A
        if _objection_pdf_uploaded(session_id):
            print(f"INFO: Objection PDF found for session {session_id} — extracting SlotNumb + Creditor")
            upload_agent = GmailMotionObjectionSustainAgent(session_id=session_id)
            upload_fields = upload_agent.extract_upload_fields(user_hint=user_hint)
            slot_numb = upload_fields.get("SlotNumb", "N/A")
            creditor = upload_fields.get("Creditor", "N/A")

            # Step 4 — fetch the latest "Notice of Hearing" email for DocketNumber + TrusteeCalendar
            #           only runs when objection PDF is uploaded
            hearing_email = search_and_extract_subject_email(
                case_number,
                "Notice of Hearing",
                docket_text_filter="Objection to Claim",
            )

            if not hearing_email:
                print(f"[warn] No 'Notice of Hearing' email found for case {case_number}")
                hearing_fields = {"DocketNumber": "N/A", "TrusteeCalendar": "N/A"}
            else:
                hearing_agent = GmailHearingExtractAgent()
                hearing_fields = hearing_agent.extract(hearing_email["body"], HEARING_EXTRACT_FIELDS_OBJECTION_SUSTAIN)
        else:
            # Step 3 (else) — no PDF uploaded: search all "Objection to Claim" NEF emails
            #   and extract SlotNumb, Creditor, DocketNumber, TrusteeCalendar from each.
            #   Values from multiple emails are joined with "\n".
            print(f"INFO: No objection PDF for session {session_id} — searching 'Objection to Claim' emails")
            objection_emails = search_and_extract_all_subject_emails(
                case_number,
                "Objection to Claim",
                docket_text_filter="Objection to Claim",
            )

            if not objection_emails:
                print(f"[warn] No 'Objection to Claim' emails found for case {case_number}")
                slot_numb = "N/A"
                creditor = "N/A"
                hearing_fields = {"DocketNumber": "N/A", "TrusteeCalendar": "N/A"}
            else:
                hearing_agent = GmailHearingExtractAgent()
                slot_numbs, creditors, docket_numbers, trustee_calendars = [], [], [], []

                for email in objection_emails:
                    fields = hearing_agent.extract(email["body"], OBJECTION_CLAIM_EMAIL_EXTRACT_FIELDS)
                    slot_numbs.append(fields.get("SlotNumb", "N/A"))
                    creditors.append(fields.get("Creditor", "N/A"))
                    docket_numbers.append(fields.get("DocketNumber", "N/A"))
                    trustee_calendars.append(fields.get("TrusteeCalendar", "N/A"))

                slot_numbs, creditors, docket_numbers, trustee_calendars = _deduplicate_objection_entries(
                    slot_numbs, creditors, docket_numbers, trustee_calendars
                )

                slot_numb = "\n".join(slot_numbs)
                creditor = "\n".join(creditors)
                hearing_fields = {
                    "DocketNumber": "\n".join(docket_numbers),
                    "TrusteeCalendar": "\n".join(trustee_calendars),
                }

        # Step 5 — build final payload (DocketNumber + TrusteeCalendar are N/A when no objection PDF)
        order_sustaining_objection_payload = {
            "DebtorName":      base_payload.get("DebtorName", "N/A"),
            "CaseNumber":      base_payload.get("CaseNo", "N/A"),
            "ChapterNumber":   base_payload.get("Chapter", "N/A"),
            "SlotNumb":        slot_numb,
            "Creditor":        creditor,
            "DocketNumber":    hearing_fields.get("DocketNumber", "N/A"),
            "TrusteeCalendar": hearing_fields.get("TrusteeCalendar", "N/A"),
        }

        return {
            "status": "success",
            "order_sustaining_objection_payload": json.dumps(order_sustaining_objection_payload),
            "message": "Order sustaining objection payload generated successfully",
        }

    except Exception as e:
        print(f"ERROR: Order sustaining objection payload generation failed for {session_id}: {str(e)}")
        return {
            "status": "failed",
            "order_sustaining_objection_payload": None,
            "error": str(e),
            "message": "Error generating order sustaining objection payload",
        }

    finally:
        # Clear the objection PDF collection after every generation run so that
        # a subsequent run without a fresh upload does not reuse stale data.
        clear_collection(f"objection_pdf_{session_id}")
