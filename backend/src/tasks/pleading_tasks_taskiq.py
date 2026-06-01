"""
Two-phase Taskiq tasks for pleading generation.

Phase 1: extract_pleading_payload - Extracts payloads, sets AWAITING_INPUT, returns immediately
Phase 2: generate_pleading_documents - Triggered on user input, generates documents

Async-native implementation using Taskiq for better concurrency with I/O-bound LLM calls.
"""

import asyncio
import logging
import time
from typing import Any, Optional

from ..taskiq_app import broker
from .task_state import task_state, TaskStatus
from .orchestrator import get_document_generator
from .extractors import get_extractor
from .schemas import USER_INPUT_FIELDS
from .pleading_helpers import (
    _generate_motion_doc,
    _generate_service_doc,
    _merge_user_input,
    _check_existing_documents,
)

logger = logging.getLogger(__name__)


def _ensure_gmail_ingested(session_id: str, task_id: str) -> dict:
    """
    Ensure Gmail data exists for session, ingest if needed.
    Synchronous function - will be run in thread pool.
    """
    import asyncio
    from ..chatbot.vectorestore import search_vectorstore
    from ..chatbot.database import get_session_chat_thread
    from ..gmail.service import ingest_gmail_emails_for_session
    from ..courtdrive.service import extract_case_number_for_session

    collection_name = f"gmail_{session_id}"

    try:
        docs = search_vectorstore(
            query="case number debtor trustee",
            collection_name=collection_name,
            k=1
        )
        if docs:
            logger.info(f"Gmail collection {collection_name} already has data")
            return {"success": True, "action": "already_exists"}
    except Exception as e:
        logger.warning(f"Error checking Gmail collection: {e}")

    logger.info(f"Gmail collection {collection_name} empty, attempting ingestion...")

    task_state.update_status(
        task_id,
        TaskStatus.EXTRACTING,
        "Fetching court emails..."
    )

    case_number = None
    try:
        loop = asyncio.new_event_loop()
        try:
            thread = loop.run_until_complete(get_session_chat_thread(session_id))
            if thread and thread.case_number:
                case_number = thread.case_number.strip()
                logger.info(f"Got case_number from ChatThread: {case_number}")
        finally:
            loop.close()
    except Exception as e:
        logger.warning(f"Error getting ChatThread: {e}")

    if not case_number:
        try:
            result = extract_case_number_for_session(session_id)
            if result.get("status") == "completed" and result.get("case_number"):
                case_number = result["case_number"].strip()
                logger.info(f"Got case_number from petition: {case_number}")
        except Exception as e:
            logger.warning(f"Error extracting case number from petition: {e}")

    if not case_number:
        logger.warning(f"No case_number found for session {session_id}")
        return {
            "success": False,
            "action": "failed",
            "error": "Could not determine case number for Gmail search"
        }

    try:
        result = ingest_gmail_emails_for_session(
            session_id=session_id,
            case_number=case_number,
            force_reingest=False
        )

        if result.get("status") == "completed":
            emails_found = result.get("result", {}).get("total_emails_found", 0)
            logger.info(f"Gmail ingestion completed: {emails_found} emails found")
            return {
                "success": True,
                "action": "ingested",
                "emails_found": emails_found
            }
        else:
            error_msg = result.get("message", "Unknown error")
            logger.warning(f"Gmail ingestion failed: {error_msg}")
            return {
                "success": False,
                "action": "failed",
                "error": error_msg
            }

    except Exception as e:
        logger.exception(f"Error during Gmail ingestion: {e}")
        return {
            "success": False,
            "action": "failed",
            "error": str(e)
        }


def _build_prefilled(motion_payload: dict, service_payload: Optional[dict]) -> dict[str, Any]:
    """Build prefilled fields dictionary from extracted payloads."""
    prefilled = {}

    if motion_payload:
        prefilled.update(motion_payload)

    if service_payload:
        for key, value in service_payload.items():
            if key not in prefilled:
                prefilled[key] = value

    return prefilled


def _enrich_prefilled(
    motion_type: str,
    motion_payload: dict,
    session_id: str,
    prefilled: dict[str, Any],
) -> dict[str, list]:
    """Apply AI-generated pre-fills for motion types that need them."""
    suggestions: dict[str, list] = {}

    if motion_type == "waive":
        from ..motion_filling.fill_motion_waive import generate_employment_explanation_suggestions
        chips = generate_employment_explanation_suggestions(
            motion_payload=motion_payload,
            session_id=session_id,
        )
        if chips:
            prefilled["employment_explanation"] = ""
            suggestions["employment_explanation"] = chips

    if motion_type == "order-delay":
        from ..motion_filling.fill_motion_order_delay import generate_extension_explanation_suggestions
        chips = generate_extension_explanation_suggestions(
            motion_payload=motion_payload,
            session_id=session_id,
        )
        if chips:
            prefilled["WhyExtensionNeeded"] = ""
            suggestions["WhyExtensionNeeded"] = chips
            prefilled["WithMotion"] = True   # chips found — skip upload step
        else:
            prefilled["WithMotion"] = False  # no chips — user must upload Motion to Delay doc

    if motion_type == "reinstate":
        from ..motion_filling.fill_motion_reinstate import generate_why_dismissed_suggestions
        chips = generate_why_dismissed_suggestions(
            motion_payload=motion_payload,
            session_id=session_id,
        )
        if chips:
            prefilled["WhyDismissedDetailed"] = ""
            suggestions["WhyDismissedDetailed"] = chips

    if motion_type == "objection-sustain":
        def _parse_options(raw_value: Any) -> list[str]:
            if raw_value in (None, ""):
                return []
            return [
                part.strip()
                for part in str(raw_value).split("\n")
                if part and part.strip() and part.strip().upper() != "N/A"
            ]

        slot_options = _parse_options(motion_payload.get("SlotNumb"))
        creditor_options = _parse_options(motion_payload.get("Creditor"))
        trusteecalendar_options = _parse_options(motion_payload.get("TrusteeCalendar"))
        docketnumber_options = _parse_options(motion_payload.get("DocketNumber"))

        if slot_options:
            suggestions["SlotNumb"] = slot_options
        if creditor_options:
            suggestions["Creditor"] = creditor_options
        if trusteecalendar_options:
            suggestions["TrusteeCalendar"] = trusteecalendar_options
        if docketnumber_options:
            suggestions["DocketNumber"] = docketnumber_options

    if motion_type == "modify":
        mod_type = motion_payload.get("modification_type", "delinquent")
        if mod_type in ("delinquent", "both"):
            from ..motion_filling.fill_motion_modify import generate_delinquent_reason_suggestions
            chips = generate_delinquent_reason_suggestions(
                motion_payload=motion_payload,
                session_id=session_id,
            )
            if chips:
                prefilled["delinquent_reason"] = ""
                suggestions["delinquent_reason"] = chips

    if motion_type == "extend":
        from ..motion_filling.fill_motion_extend import generate_extend_suggestions
        extend_chips = generate_extend_suggestions(
            motion_payload=motion_payload,
            session_id=session_id,
        )
        if extend_chips.get("dismissal_reason"):
            prefilled["dismissal_reason"] = ""
            suggestions["dismissal_reason"] = extend_chips["dismissal_reason"]
        if extend_chips.get("change_in_circum"):
            prefilled["change_in_circum"] = ""
            suggestions["change_in_circum"] = extend_chips["change_in_circum"]

    return suggestions


def _generate_documents_sync(
    task_id: str,
    session_id: str,
    motion_type: str,
    motion_payload: dict,
    service_payload: Optional[dict],
    include_cos: bool,
    include_order_sustaining: bool = False,
    order_sustaining_payload: Optional[dict] = None
) -> dict[str, Any]:
    """Generate all documents in parallel using ThreadPoolExecutor."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    documents = {}
    name_slug = f"{motion_type}_{session_id}_{int(time.time())}"

    doc_generator = get_document_generator(motion_type)
    if doc_generator is None:
        logger.error(f"No document generator found for motion_type={motion_type}")
        return documents

    futures_map = {}
    max_workers = 1

    if include_cos and service_payload:
        max_workers += 1
    if include_order_sustaining and order_sustaining_payload:
        max_workers += 1

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures_map[executor.submit(
            _generate_motion_doc, doc_generator, motion_payload, name_slug, session_id, motion_type
        )] = "motion"

        if include_cos and service_payload:
            futures_map[executor.submit(
                _generate_service_doc, service_payload, f"cos_{name_slug}", session_id
            )] = "service"

        if include_order_sustaining and order_sustaining_payload:
            sustain_generator = get_document_generator("objection-sustain")
            if sustain_generator:
                sustain_name_slug = f"objection_sustain_{session_id}_{int(time.time())}"
                futures_map[executor.submit(
                    _generate_motion_doc, sustain_generator, order_sustaining_payload, sustain_name_slug, session_id, "objection-sustain"
                )] = "order_on_objection"
            else:
                logger.error("No document generator found for objection-sustain")

        for future in as_completed(futures_map):
            doc_type = futures_map[future]

            if task_state.is_cancelled(task_id):
                executor.shutdown(wait=False, cancel_futures=True)
                return documents

            try:
                result = future.result()
                if doc_type == "motion":
                    documents["motion"] = result
                elif doc_type == "service":
                    documents["certificate_of_service"] = result
                elif doc_type == "order_on_objection":
                    documents["order_on_objection"] = result
            except Exception as e:
                logger.exception(f"Error generating {doc_type} document: {e}")

    return documents


@broker.task(
    task_name="extract_pleading_payload",
    retry_on_error=True,
    max_retries=2,
)
async def extract_pleading_payload(
    task_id: str,
    session_id: str,
    motion_type: str,
    source: str,
    include_cos: bool,
    include_order_sustaining: bool = False,
    initial_user_input: dict | None = None,
    skip_existing_check: bool = False,
    modification_type: str = "delinquent",
    extension_type: str = "regular",
) -> dict[str, Any]:
    """
    Phase 1: Extract payloads using structured output.

    Async task that runs sync extractors in thread pool to avoid blocking.
    """
    try:
        if task_state.is_cancelled(task_id):
            return {"status": "cancelled", "task_id": task_id}

        task = task_state.get_task(task_id)
        should_skip_existing_check = bool(
            (task and task.get("regenerate")) or skip_existing_check or (task and task.get("skip_existing_check"))
        )

        if not should_skip_existing_check:
            task_state.update_status(
                task_id,
                TaskStatus.CHECKING_EXISTING,
                "Checking for existing documents..."
            )

            existing_docs = await asyncio.to_thread(
                _check_existing_documents, session_id, motion_type, include_cos
            )

            if existing_docs:
                task_state.set_existing_found(task_id, existing_docs)
                return {
                    "status": "existing_found",
                    "task_id": task_id,
                    "documents": existing_docs
                }

        if task_state.is_cancelled(task_id):
            return {"status": "cancelled", "task_id": task_id}

        should_skip_gmail_ingestion = bool(
            skip_existing_check and source == "gmail" and motion_type == "objection-sustain"
        )

        if source == "gmail" and not should_skip_gmail_ingestion:
            gmail_result = await asyncio.to_thread(
                _ensure_gmail_ingested, session_id, task_id
            )

            if not gmail_result["success"]:
                logger.warning(
                    f"Gmail ingestion failed for task {task_id}: {gmail_result.get('error')}. "
                    "Extraction will proceed with limited data."
                )

            if task_state.is_cancelled(task_id):
                return {"status": "cancelled", "task_id": task_id}

        task_state.update_status(
            task_id,
            TaskStatus.EXTRACTING,
            "Extracting case information..."
        )

        extractor = get_extractor(session_id, motion_type, modification_type=modification_type)
        include_order_sustaining_effective = include_order_sustaining and motion_type != "claim"

        extraction_result = await asyncio.to_thread(
            extractor.extract_all,
            motion_type=motion_type,
            include_service=include_cos,
            include_order_sustaining=include_order_sustaining_effective
        )

        if task_state.is_cancelled(task_id):
            return {"status": "cancelled", "task_id": task_id}

        # Handle intermediate input prompts (e.g., trustees_reason when no dismissed case emails found)
        if extraction_result.get("status") == "needs_input":
            missing_field = extraction_result.get("missing_field")
            missing_fields = extraction_result.get("missing_fields") or []
            message = extraction_result.get("message")
            partial_payload = extraction_result.get("partial_payload") or {}

            logger.info(f"Task {task_id}: Extraction needs input - missing_field={missing_field}, missing_fields={missing_fields}")

            task_state.store_extracted_payloads(task_id, partial_payload, None, None)
            task_state.set_input_required(
                task_id,
                fields=missing_fields if missing_fields else [missing_field],
                prefilled=partial_payload,
                suggestions=None,
                missing_field=missing_field,
                missing_fields=missing_fields,
                custom_message=message,
            )

            return {
                "status": "awaiting_input",
                "task_id": task_id,
                "missing_field": missing_field,
                "missing_fields": missing_fields,
                "message": message,
            }

        motion_payload = extraction_result.get("motion_payload")
        service_payload = extraction_result.get("service_payload")
        errors = extraction_result.get("errors", [])

        if motion_type == "extend" and motion_payload:
            motion_payload["extension_type"] = extension_type

        if motion_payload is None:
            error_msg = errors[0] if errors else "Failed to extract motion payload"
            task_state.set_error(task_id, error_msg)
            return {"status": "failed", "task_id": task_id, "error": error_msg}

        if motion_type == "claim" and include_cos and service_payload is None:
            error_msg = "Failed to extract Certificate of Service payload while include_cos=true"
            task_state.set_error(task_id, error_msg)
            return {"status": "failed", "task_id": task_id, "error": error_msg}

        if errors:
            for error in errors:
                logger.warning(f"Task {task_id}: Non-fatal extraction error: {error}")

        input_fields = USER_INPUT_FIELDS.get(motion_type, [])
        prefilled = _build_prefilled(motion_payload, service_payload)

        task_state.store_extracted_payloads(
            task_id,
            motion_payload,
            service_payload,
            extraction_result.get("order_sustaining_payload")
        )

        if not input_fields:
            logger.info(f"Task {task_id}: No input required, proceeding to generation")
            await generate_pleading_documents.kiq(
                task_id=task_id,
                session_id=session_id,
                motion_type=motion_type,
                user_input=initial_user_input or {},
                include_cos=include_cos,
                include_order_sustaining=include_order_sustaining_effective
            )
            return {
                "status": "generating",
                "task_id": task_id,
                "input_fields": [],
                "prefilled_count": len(prefilled)
            }

        suggestions = await asyncio.to_thread(
            _enrich_prefilled, motion_type, motion_payload, session_id, prefilled
        )

        # order-delay: no chips found → ask user to upload Motion to Delay doc first (Step 1 of 2)
        if motion_type == "order-delay" and prefilled.get("WithMotion") is False:
            task_state.set_input_required(
                task_id,
                fields=["motion_to_delay_doc"],
                prefilled=prefilled,
                suggestions=None,
                missing_field="motion_to_delay_doc",
                custom_message=(
                    "We could not find secured creditor information automatically. "
                    "Please upload your Motion to Delay PDF to generate suggestions."
                ),
            )
            logger.info(f"Task {task_id}: order-delay no chips — awaiting Motion to Delay upload (Step 1)")
            return {
                "status": "awaiting_input",
                "task_id": task_id,
                "missing_field": "motion_to_delay_doc",
                "input_fields": ["motion_to_delay_doc"],
                "prefilled_count": len(prefilled),
            }

        task_state.set_input_required(task_id, input_fields, prefilled, suggestions=suggestions)
        logger.info(f"Task {task_id}: Extraction complete, awaiting user input")

        return {
            "status": "awaiting_input",
            "task_id": task_id,
            "input_fields": input_fields,
            "prefilled_count": len(prefilled)
        }

    except Exception as exc:
        logger.exception(f"Extraction task {task_id} failed: {exc}")
        task_state.set_error(task_id, str(exc))
        raise


@broker.task(
    task_name="resume_pleading_extraction",
    retry_on_error=True,
    max_retries=2,
)
async def resume_pleading_extraction(
    task_id: str,
    session_id: str,
    motion_type: str,
    user_input: dict,
    include_cos: bool,
    include_order_sustaining: bool = False,
    modification_type: str = "delinquent",
    extension_type: str = "regular",
) -> dict[str, Any]:
    """
    Resume extraction after intermediate input (e.g., dismissed_case_number, trustees_reason).

    This task:
    1. Merges user input with stored partial payload
    2. Re-runs extraction with the new information
    3. Returns either another AWAITING_INPUT (for next missing field) or proceeds to chips
    """
    try:
        if task_state.is_cancelled(task_id):
            return {"status": "cancelled", "task_id": task_id}

        task_state.update_status(
            task_id,
            TaskStatus.EXTRACTING,
            "Continuing extraction with your input..."
        )

        # Get stored partial payload and merge with user input
        stored = task_state.get_extracted_payloads(task_id)
        partial_payload = stored.get("motion_payload", {}) if stored else {}
        prefilled = {**partial_payload, **user_input}

        logger.info(f"Task {task_id}: Resuming extraction with prefilled={prefilled}")

        # ── order-delay: Step 1 → Step 2 ────────────────────────────────────────────
        # User uploaded Motion to Delay doc. Generate chips from it and present the
        # final AWAITING_INPUT (Step 2: chips form for WhyExtensionNeeded).
        # Skip the Gmail extractor entirely — no further extraction needed.
        if motion_type == "order-delay" and user_input.get("motion_doc_uploaded"):
            from ..motion_filling.order_delay_document_processor import (
                retrieve_doc_from_redis,
                generate_chips_from_uploaded_doc,
            )

            doc_content = retrieve_doc_from_redis(session_id, task_id)
            chips: list[str] = []
            if doc_content:
                chips = await asyncio.to_thread(
                    generate_chips_from_uploaded_doc, doc_content, partial_payload
                )
                logger.info(f"Task {task_id}: Generated {len(chips)} chips from uploaded Motion to Delay")
            else:
                logger.warning(f"Task {task_id}: order-delay — no doc found in Redis, proceeding without chips")

            prefilled_step2: dict = {**partial_payload, "WithMotion": False}
            step2_suggestions: dict = {}
            if chips:
                prefilled_step2["WhyExtensionNeeded"] = ""
                step2_suggestions["WhyExtensionNeeded"] = chips

            task_state.set_input_required(
                task_id,
                fields=["WhyExtensionNeeded"],
                prefilled=prefilled_step2,
                suggestions=step2_suggestions,
                # No missing_field — this is the final AWAITING_INPUT
            )
            logger.info(f"Task {task_id}: order-delay Step 2 — awaiting WhyExtensionNeeded selection")
            return {
                "status": "awaiting_input",
                "task_id": task_id,
                "input_fields": ["WhyExtensionNeeded"],
                "prefilled_count": len(prefilled_step2),
            }
        # ────────────────────────────────────────────────────────────────────────────

        # Re-run extraction with prefilled values (all other motion types)
        extractor = get_extractor(
            session_id, motion_type,
            modification_type=modification_type, prefilled=prefilled
        )
        include_order_sustaining_effective = include_order_sustaining and motion_type != "claim"

        extraction_result = await asyncio.to_thread(
            extractor.extract_all,
            motion_type=motion_type,
            include_service=include_cos,
            include_order_sustaining=include_order_sustaining_effective
        )

        if task_state.is_cancelled(task_id):
            return {"status": "cancelled", "task_id": task_id}

        # Check if we need more input
        if extraction_result.get("status") == "needs_input":
            missing_field = extraction_result.get("missing_field")
            missing_fields = extraction_result.get("missing_fields") or []
            message = extraction_result.get("message")
            new_partial_payload = extraction_result.get("partial_payload") or {}

            logger.info(f"Task {task_id}: Still needs input - missing_field={missing_field}, missing_fields={missing_fields}")

            task_state.store_extracted_payloads(task_id, new_partial_payload, None, None)
            task_state.set_input_required(
                task_id,
                fields=missing_fields if missing_fields else [missing_field],
                prefilled=new_partial_payload,
                suggestions=None,
                missing_field=missing_field,
                missing_fields=missing_fields,
                custom_message=message,
            )

            return {
                "status": "awaiting_input",
                "task_id": task_id,
                "missing_field": missing_field,
                "missing_fields": missing_fields,
                "message": message,
            }

        motion_payload = extraction_result.get("motion_payload")
        service_payload = extraction_result.get("service_payload")
        errors = extraction_result.get("errors", [])

        if motion_type == "extend" and motion_payload:
            motion_payload["extension_type"] = extension_type

        if motion_payload is None:
            error_msg = errors[0] if errors else "Failed to extract motion payload"
            task_state.set_error(task_id, error_msg)
            return {"status": "failed", "task_id": task_id, "error": error_msg}

        input_fields = USER_INPUT_FIELDS.get(motion_type, [])
        prefilled_result = _build_prefilled(motion_payload, service_payload)

        task_state.store_extracted_payloads(
            task_id,
            motion_payload,
            service_payload,
            extraction_result.get("order_sustaining_payload")
        )

        if not input_fields:
            logger.info(f"Task {task_id}: No input required, proceeding to generation")
            await generate_pleading_documents.kiq(
                task_id=task_id,
                session_id=session_id,
                motion_type=motion_type,
                user_input={},
                include_cos=include_cos,
                include_order_sustaining=include_order_sustaining_effective
            )
            return {
                "status": "generating",
                "task_id": task_id,
                "input_fields": [],
                "prefilled_count": len(prefilled_result)
            }

        suggestions = await asyncio.to_thread(
            _enrich_prefilled, motion_type, motion_payload, session_id, prefilled_result
        )

        task_state.set_input_required(task_id, input_fields, prefilled_result, suggestions=suggestions)
        logger.info(f"Task {task_id}: Extraction complete after resume, awaiting final user input")

        return {
            "status": "awaiting_input",
            "task_id": task_id,
            "input_fields": input_fields,
            "prefilled_count": len(prefilled_result)
        }

    except Exception as exc:
        logger.exception(f"Resume extraction task {task_id} failed: {exc}")
        task_state.set_error(task_id, str(exc))
        raise


@broker.task(
    task_name="generate_pleading_documents",
    retry_on_error=True,
    max_retries=2,
)
async def generate_pleading_documents(
    task_id: str,
    session_id: str,
    motion_type: str,
    user_input: dict,
    include_cos: bool,
    include_order_sustaining: bool = False
) -> dict[str, Any]:
    """
    Phase 2: Generate documents after user input.

    Async task that runs document generation in thread pool.
    """
    try:
        if task_state.is_cancelled(task_id):
            return {"status": "cancelled", "task_id": task_id}

        task_state.update_status(
            task_id,
            TaskStatus.GENERATING,
            "Generating documents..."
        )

        stored = task_state.get_extracted_payloads(task_id)
        if stored is None:
            task_state.set_error(task_id, "No extracted payloads found. Task may have expired.")
            return {"status": "failed", "task_id": task_id, "error": "Payloads not found"}

        motion_payload = stored.get("motion_payload", {})
        service_payload = stored.get("service_payload")
        order_sustaining_payload = stored.get("order_sustaining_payload")

        merged_motion = _merge_user_input(motion_payload, user_input)
        merged_service = _merge_user_input(service_payload, user_input) if service_payload else None
        include_order_sustaining_effective = include_order_sustaining and motion_type != "claim"

        if motion_type == "loe" and user_input.get("has_supporting_docs"):
            from ..motion_filling.loe_document_processor import retrieve_docs_from_redis
            supporting_docs = retrieve_docs_from_redis(session_id, task_id)
            if supporting_docs:
                merged_motion["_supporting_docs"] = supporting_docs
                logger.info(f"LOE task {task_id}: Found {len(supporting_docs)} supporting documents")

        if task_state.is_cancelled(task_id):
            return {"status": "cancelled", "task_id": task_id}

        documents = await asyncio.to_thread(
            _generate_documents_sync,
            task_id=task_id,
            session_id=session_id,
            motion_type=motion_type,
            motion_payload=merged_motion,
            service_payload=merged_service,
            include_cos=include_cos,
            include_order_sustaining=include_order_sustaining_effective,
            order_sustaining_payload=order_sustaining_payload
        )

        if motion_type == "claim" and include_cos and "certificate_of_service" not in documents:
            error_msg = "Certificate of Service document generation failed while include_cos=true"
            task_state.set_error(task_id, error_msg)
            return {"status": "failed", "task_id": task_id, "error": error_msg}

        if task_state.is_cancelled(task_id):
            return {"status": "cancelled", "task_id": task_id}

        from .motion_tracker import log_draft_completed, track_motion_for_order
        case_number = merged_motion.get("CaseNumber") or merged_motion.get("case_no")
        _noh_raw = merged_service.get("IfNoticeofHearing") if merged_service else None
        _noh_yes = str(_noh_raw).strip().lower() in ("yes", "true", "y", "1") if _noh_raw else False
        if not include_cos:
            cos_type = "No"
        elif _noh_yes:
            cos_type = "WithNoticeOfHearing"
        else:
            cos_type = "WithoutNoticeOfHearing"
        await log_draft_completed(
            session_id=session_id,
            motion_type=motion_type,
            case_number=case_number,
            cos_type=cos_type,
        )
        await track_motion_for_order(
            session_id=session_id,
            motion_type=motion_type,
            metadata={
                "case_number": case_number,
                "debtor_name": merged_motion.get("DebtorName") or merged_motion.get("debtor_name"),
            },
        )

        if motion_type == "loe" and user_input.get("has_supporting_docs"):
            if not user_input.get("store_docs_permanently", False):
                from ..motion_filling.loe_document_processor import cleanup_temp_docs
                cleanup_temp_docs(session_id, task_id)
                logger.info(f"LOE task {task_id}: Cleaned up temporary supporting documents")

        # order-delay: Cleanup uploaded Motion to Delay doc from Redis after generation
        if motion_type == "order-delay" and not merged_motion.get("WithMotion", True):
            from ..motion_filling.order_delay_document_processor import cleanup_doc
            cleanup_doc(session_id, task_id)
            logger.info(f"order-delay task {task_id}: Cleaned up uploaded Motion to Delay doc from Redis")

        task_state.set_result(
            task_id,
            documents,
            {
                "motion_payload": merged_motion,
                "service_payload": merged_service,
                "order_sustaining_payload": order_sustaining_payload
            }
        )

        return {
            "status": "completed",
            "task_id": task_id,
            "documents": documents
        }

    except Exception as exc:
        logger.exception(f"Document generation task {task_id} failed: {exc}")
        task_state.set_error(task_id, str(exc))
        from .motion_tracker import log_draft_failed
        await log_draft_failed(session_id=session_id, motion_type=motion_type)
        raise
