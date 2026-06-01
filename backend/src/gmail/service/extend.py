"""
Motion to Extend Service - Revamped

Service layer for Motion to Extend Automatic Stay.
Uses the new GmailMotionExtendAgent with AI recommendations.
"""

from typing import Optional, Dict, Any

from ..agents import GmailMotionExtendAgent

def generate_payload_extend_for_session_gmail(
    session_id: str,
    user_hint: str = "Find case number, dismissed case number, docket entry number, trustee's reason, dismissal date, and chapter information.",
    prefilled: Optional[Dict[str, Any]] = None,
) -> dict:
    """
    Generate the payload JSON for a session using the GmailMotionExtendAgent.
    Returns status dict with payload or error information.

    Args:
        session_id: The session ID.
        user_hint: Hint for extraction.
        prefilled: Optional dict with pre-filled values from user input.
                   Used when resuming extraction after intermediate input.

    This function is called by:
    - generate_order_extend_payload_for_session_gmail (order_extend.py)
    - tasks/orchestrator.py
    - tasks/extractors.py
    """
    try:
        print(f"INFO: Generating motion extend payload JSON for session {session_id} using Gmail")
        if prefilled:
            print(f"INFO: Using prefilled values: {prefilled}")

        gmail_motion_extend_agent = GmailMotionExtendAgent(session_id=session_id)
        payload_result = gmail_motion_extend_agent.extract_payload(user_hint=user_hint, prefilled=prefilled)

        if payload_result.get("status") == "success":
            import json

            payload_data = payload_result.get("payload")
            payload_json = json.dumps(payload_data) if isinstance(payload_data, dict) else payload_data

            return {
                "status": "success",
                "payload": payload_json,
                "message": "Motion extend payload generated successfully from Gmail data",
            }
        elif payload_result.get("status") == "needs_input":
            return {
                "status": "needs_input",
                "missing_field": payload_result.get("missing_field"),
                "missing_fields": payload_result.get("missing_fields"),
                "message": payload_result.get("message"),
                "partial_payload": payload_result.get("partial_payload"),
            }
        else:
            return {
                "status": "failed",
                "payload": None,
                "error": payload_result.get("error", "Unknown error"),
                "message": "Error generating motion extend payload",
            }
    except Exception as payload_error:
        print(f"ERROR: Motion extend payload generation failed for {session_id}: {str(payload_error)}")
        return {
            "status": "failed",
            "payload": None,
            "error": str(payload_error),
            "message": "Error generating motion extend payload",
        }


def generate_payload_extend_with_recommendations_for_session_gmail(
    session_id: str,
    user_hint: str = "",
) -> dict:
    """
    Generate the payload JSON AND AI recommendations for Motion to Extend.
    This is the main entry point for the new extend flow.

    Returns:
        {
            "status": "success" | "needs_input" | "failed",
            "payload": {...} or None,
            "recommendations": {
                "dismissal_reason_chips": [...],
                "change_in_circum_chips": [...],
                "has_old_petition": bool,
                "has_chapter_13_plan": bool,
                "context_warnings": [...],
            } or None,
            "missing_field": str (if needs_input),
            "message": str,
        }
    """
    try:
        print(f"INFO: Generating motion extend payload + recommendations for session {session_id}")

        gmail_motion_extend_agent = GmailMotionExtendAgent(session_id=session_id)
        result = gmail_motion_extend_agent.extract_payload_with_recommendations(user_hint=user_hint)

        if result.get("status") == "success":
            import json

            payload_data = result.get("payload")
            recommendations = result.get("recommendations")
            payload_json = json.dumps(payload_data) if isinstance(payload_data, dict) else payload_data

            return {
                "status": "success",
                "payload": payload_json,
                "recommendations": recommendations,
                "message": "Motion extend payload and recommendations generated successfully",
            }
        elif result.get("status") == "needs_input":
            return {
                "status": "needs_input",
                "missing_field": result.get("missing_field"),
                "missing_fields": result.get("missing_fields"),
                "message": result.get("message"),
                "partial_payload": result.get("partial_payload"),
            }
        else:
            return {
                "status": "failed",
                "payload": None,
                "recommendations": None,
                "error": result.get("error", "Unknown error"),
                "message": result.get("message", "Error generating motion extend payload"),
            }
    except Exception as e:
        print(f"ERROR: Motion extend payload + recommendations generation failed: {str(e)}")
        return {
            "status": "failed",
            "payload": None,
            "recommendations": None,
            "error": str(e),
            "message": "Error generating motion extend payload with recommendations",
        }


def continue_extend_extraction_with_manual_input(
    session_id: str,
    field: str,
    value: str,
    partial_payload: Optional[Dict[str, Any]] = None,
) -> dict:
    """
    Continue the extend extraction flow after user provides manual input
    for a missing field (dismissed_case_number or trustees_reason).

    Args:
        session_id: Session ID
        field: Field name that was manually provided ("dismissed_case_number" or "trustees_reason")
        value: User-provided value for the field
        partial_payload: Partial payload from previous extraction attempt

    Returns:
        Same format as generate_payload_extend_with_recommendations_for_session_gmail
    """
    try:
        print(f"INFO: Continuing extend extraction with manual input: {field}={value}")

        gmail_motion_extend_agent = GmailMotionExtendAgent(session_id=session_id)

        if field == "dismissed_case_number":
            order_dismissing_email = gmail_motion_extend_agent._search_order_dismissing_with_fallback(value)

            if not order_dismissing_email:
                return {
                    "status": "needs_input",
                    "missing_field": "trustees_reason",
                    "message": "It looks like we couldn't find this dismissed case in your courtmail. It's likely that you didn't represent this client in their previous case. Please let us know what the trustee put as the reason for dismissal.",
                    "partial_payload": {
                        **(partial_payload or {}),
                        "dismissed_case_number": value,
                    },
                }

            extracted_fields = gmail_motion_extend_agent._extract_from_order_dismissing_email(order_dismissing_email)

            petition_date = partial_payload.get("petition_date", "N/A") if partial_payload else "N/A"
            petition_date_plus_30 = gmail_motion_extend_agent._calculate_petition_date_plus_30(petition_date)

            payload = {
                **(partial_payload or {}),
                "dismissed_case_number": value,
                "dismissal_date": extracted_fields.get("dismissal_date", "N/A"),
                "trustees_reason": extracted_fields.get("trustees_reason", "N/A"),
                "docket_entry_no": extracted_fields.get("docket_entry_no", "N/A"),
                "dismissal_reason": "N/A",
                "change_in_circum": "N/A",
                "extension_type": "regular",
                "petition_date_plus_30": petition_date_plus_30,
            }

        elif field == "trustees_reason":
            petition_date = partial_payload.get("petition_date", "N/A") if partial_payload else "N/A"
            petition_date_plus_30 = gmail_motion_extend_agent._calculate_petition_date_plus_30(petition_date)

            payload = {
                **(partial_payload or {}),
                "trustees_reason": value,
                "docket_entry_no": partial_payload.get("docket_entry_no", "N/A") if partial_payload else "N/A",
                "dismissal_date": partial_payload.get("dismissal_date", "N/A") if partial_payload else "N/A",
                "dismissal_reason": "N/A",
                "change_in_circum": "N/A",
                "extension_type": "regular",
                "petition_date_plus_30": petition_date_plus_30,
            }

        else:
            return {
                "status": "failed",
                "error": f"Unknown field: {field}",
                "message": f"Cannot continue extraction for unknown field: {field}",
            }

        case_no = payload.get("case_no", "")
        trustees_reason = payload.get("trustees_reason", "N/A")
        dismissed_case_number = payload.get("dismissed_case_number", "")

        current_petition_context = gmail_motion_extend_agent._get_current_petition_schedule_context()
        chapter_13_plan_context, _ = gmail_motion_extend_agent._get_chapter_13_plan_context(case_no)

        recommendations = gmail_motion_extend_agent.generate_recommendations(
            trustees_reason=trustees_reason,
            current_petition_context=current_petition_context,
            chapter_13_plan_context=chapter_13_plan_context,
            dismissed_case_number=dismissed_case_number,
        )

        import json
        return {
            "status": "success",
            "payload": json.dumps(payload),
            "recommendations": {
                "dismissal_reason_chips": recommendations.dismissal_reason_chips,
                "change_in_circum_chips": recommendations.change_in_circum_chips,
                "has_old_petition": recommendations.has_old_petition,
                "has_chapter_13_plan": recommendations.has_chapter_13_plan,
                "context_warnings": recommendations.context_warnings,
            },
            "message": "Motion extend extraction completed with manual input",
        }

    except Exception as e:
        print(f"ERROR: Continue extend extraction failed: {str(e)}")
        return {
            "status": "failed",
            "error": str(e),
            "message": "Error continuing motion extend extraction",
        }
