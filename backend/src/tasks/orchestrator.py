"""Central orchestration for motion and document generation tasks."""
import asyncio
from typing import Any, Callable, Optional

from .task_state import task_state


# Called by: get_motion_context(), get_motion_display_name(), start_pleading_generation() (same file)
MOTION_TYPE_MAPPING = {
    "extend": {
        "display_name": "Motion to Extend the Stay",
        "motion_context": "Motion to Extend Automatic Stay",
    },
    "modify": {
        "display_name": "Motion to Modify",
        "motion_context": "Motion to Modify Plan",
    },
    "value": {
        "display_name": "Motion to Value",
        "motion_context": "Motion to Value Personal Property",
    },
    "withdraw": {
        "display_name": "Motion to Withdraw",
        "motion_context": "Motion to Withdraw as Counsel",
    },
    "waive": {
        "display_name": "Motion to Waive",
        "motion_context": "Motion to Waive Filing Fee",
    },
    "claim": {
        "display_name": "Objection to Claim",
        "motion_context": "Motion/Objection to Claim",
    },
    "delay": {
        "display_name": "Motion to Delay",
        "motion_context": "Motion to Delay",
    },
    "reinstate": {
        "display_name": "Motion to Reinstate",
        "motion_context": "Motion to Reinstate",
    },
    "suggestion": {
        "display_name": "Suggestion of Bankruptcy",
        "motion_context": "Suggestion of Bankruptcy",
    },
    "loe": {
        "display_name": "Letter of Explanation",
        "motion_context": "Letter of Explanation to Trustee",
    },
    "ex-parte-extension": {
        "display_name": "Ex Parte Extension",
        "motion_context": "Ex Parte Motion for Extension",
    },
    "order-extend": {
        "display_name": "Order on Extend",
        "motion_context": "Order on Motion to Extend",
    },
    "order-waive": {
        "display_name": "Order on Waive",
        "motion_context": "Order on Motion to Waive",
    },
    "order-withdraw": {
        "display_name": "Order on Withdraw",
        "motion_context": "Order on Motion to Withdraw",
    },
    "order-reinstate": {
        "display_name": "Order on Reinstate",
        "motion_context": "Order on Motion to Reinstate",
    },
    "order-value": {
        "display_name": "Order on Value",
        "motion_context": "Order on Motion to Value Personal Property",
    },
    "order-extension": {
        "display_name": "Order on Motion for Extension",
        "motion_context": "Order on Motion for Extension",
    },
    "order-delay": {
        "display_name": "Order on Motion for Delay",
        "motion_context": "Order on Motion for Delay",
    },
    "notice-withdraw": {
        "display_name": "Notice of Withdrawal",
        "motion_context": "Notice of Withdrawal",
    },
    "objection-sustain": {
        "display_name": "Order on Objection",
        "motion_context": "Order Sustaining Objection to Claim",
    },
    "certificate-of-service": {
        "display_name": "Certificate of Service",
        "motion_context": "Certificate of Service",
    },
}


# Called by: pleading_tasks.extract_pleading_payload() (tasks/pleading_tasks.py)
def get_motion_context(motion_type: str) -> str:
    """Return the motion context string for a given motion type key."""
    mapping = MOTION_TYPE_MAPPING.get(motion_type)
    if mapping:
        return mapping["motion_context"]
    return motion_type.replace("-", " ").title()


# Called by: start_pleading_generation() (same file); route files (for display purposes)
def get_motion_display_name(motion_type: str) -> str:
    """Return the user-friendly display name for a given motion type key."""
    mapping = MOTION_TYPE_MAPPING.get(motion_type)
    if mapping:
        return mapping["display_name"]
    return motion_type.replace("-", " ").title()




# Called by: pleading_tasks._generate_documents() (tasks/pleading_tasks.py)
def get_document_generator(motion_type: str) -> Optional[dict[str, Callable]]:
    """Return a dict of {"docx": callable, "pdf": callable} for a motion type.

    Args:
        motion_type: Motion type key.

    Returns:
        Dict with "docx" and "pdf" generator callables from the motion_filling module,
        or None if the motion type has no mapped document module.
    """
    import importlib

    module_map = {
        "extend": "fill_motion_extend",
        "modify": "fill_motion_modify",
        "value": "fill_motion_value",
        "withdraw": "fill_motion_withdraw",
        "waive": "fill_motion_waive",
        "claim": "fill_motion_claim",
        "delay": "fill_motion_delay",
        "reinstate": "fill_motion_reinstate",
        "suggestion": "fill_motion_suggestion",
        "loe": "fill_motion_loe",
        "ex-parte-extension": "fill_ex_parte_motion_extension",
        "notice-withdraw": "fill_notice_withdraw",
        "certificate-of-service": "fill_motion_service",
        "objection-sustain": "fill_order_sustaining_objection",
        "order-extend": "fill_order_granting_extend",
        "order-waive": "fill_order_waive",
        "order-withdraw": "fill_order_withdraw",
        "order-reinstate": "fill_order_reinstate",
        "order-value": "fill_order_value",
        "order-extension": "fill_motion_order_extension",
        "order-delay": "fill_motion_order_delay",
    }

    module_name = module_map.get(motion_type)
    if not module_name:
        return None

    module = importlib.import_module(f"src.motion_filling.{module_name}")
    return {
        "docx": module.generate_docx_from_payload,
        "pdf": module.generate_pdf_from_payload,
    }


def _create_pleading_task(
    user_id: str,
    session_id: str,
    motion_type: str,
    case_name: str,
    source: str,
    include_cos: bool,
    include_order_sustaining: bool,
    initial_user_input: Optional[dict[str, Any]],
    skip_existing_check: bool,
    modification_type: str,
    extension_type: str = "regular",
) -> str:
    """Create a task record in Redis and return the task_id."""
    return task_state.create_task(
        user_id=user_id,
        session_id=session_id,
        motion_type=motion_type,
        case_name=case_name,
        source=source,
        include_cos=include_cos,
        include_order_sustaining=include_order_sustaining,
        initial_user_input=initial_user_input,
        skip_existing_check=skip_existing_check,
        modification_type=modification_type,
        extension_type=extension_type,
    )


def _build_pleading_response(task_id: str, motion_type: str, case_name: str, worker_task_id: str) -> dict[str, Any]:
    """Build the response dict for a queued pleading task."""
    task = task_state.get_task(task_id)
    return {
        "status": "success",
        "task_id": task_id,
        "worker_task_id": worker_task_id,
        "task_status": task["status"],
        "motion_type": motion_type,
        "motion_type_display": get_motion_display_name(motion_type),
        "case_name": case_name,
        "created_at": task["created_at"],
        "message": "Task queued for processing"
    }


async def start_pleading_generation(
    user_id: str,
    session_id: str,
    motion_type: str,
    case_name: str,
    source: str = "gmail",
    include_cos: bool = True,
    include_order_sustaining: bool = False,
    initial_user_input: Optional[dict[str, Any]] = None,
    skip_existing_check: bool = False,
    modification_type: str = "delinquent",
    extension_type: str = "regular",
) -> dict[str, Any]:
    """Create a task record and enqueue the extraction task via TaskIQ."""
    task_id = await asyncio.to_thread(
        _create_pleading_task,
        user_id=user_id,
        session_id=session_id,
        motion_type=motion_type,
        case_name=case_name,
        source=source,
        include_cos=include_cos,
        include_order_sustaining=include_order_sustaining,
        initial_user_input=initial_user_input,
        skip_existing_check=skip_existing_check,
        modification_type=modification_type,
        extension_type=extension_type,
    )

    from ..taskiq_client import enqueue_extract_pleading

    taskiq_handle = await enqueue_extract_pleading(
        task_id=task_id,
        session_id=session_id,
        motion_type=motion_type,
        source=source,
        include_cos=include_cos,
        include_order_sustaining=include_order_sustaining,
        initial_user_input=initial_user_input,
        skip_existing_check=skip_existing_check,
        modification_type=modification_type,
        extension_type=extension_type,
    )

    worker_task_id = taskiq_handle.task_id
    await asyncio.to_thread(task_state.set_worker_task_id, task_id, worker_task_id)

    from .motion_tracker import log_draft_pending
    await log_draft_pending(session_id=session_id, motion_type=motion_type, case_name=case_name)

    return await asyncio.to_thread(_build_pleading_response, task_id, motion_type, case_name, worker_task_id)
