"""
Taskiq client helpers for dispatching tasks.

Provides typed functions for enqueueing Taskiq tasks with proper parameters.
"""
from typing import Any

from .tasks.pleading_tasks_taskiq import extract_pleading_payload, generate_pleading_documents, resume_pleading_extraction
from .tasks.review_tasks_taskiq import run_petition_review


async def enqueue_extract_pleading(
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
) -> Any:
    """
    Dispatch a pleading extraction task.

    Returns the Taskiq task handle for status tracking.
    """
    return await extract_pleading_payload.kiq(
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


async def enqueue_generate_documents(
    task_id: str,
    session_id: str,
    motion_type: str,
    user_input: dict,
    include_cos: bool,
    include_order_sustaining: bool = False,
) -> Any:
    """
    Dispatch a document generation task.

    Returns the Taskiq task handle for status tracking.
    """
    return await generate_pleading_documents.kiq(
        task_id=task_id,
        session_id=session_id,
        motion_type=motion_type,
        user_input=user_input,
        include_cos=include_cos,
        include_order_sustaining=include_order_sustaining,
    )


async def enqueue_resume_extraction(
    task_id: str,
    session_id: str,
    motion_type: str,
    user_input: dict,
    include_cos: bool,
    include_order_sustaining: bool = False,
    modification_type: str = "delinquent",
    extension_type: str = "regular",
) -> Any:
    """
    Dispatch a resume extraction task for intermediate inputs.

    Used when user provides missing fields like dismissed_case_number or trustees_reason.
    Returns the Taskiq task handle for status tracking.
    """
    return await resume_pleading_extraction.kiq(
        task_id=task_id,
        session_id=session_id,
        motion_type=motion_type,
        user_input=user_input,
        include_cos=include_cos,
        include_order_sustaining=include_order_sustaining,
        modification_type=modification_type,
        extension_type=extension_type,
    )


async def enqueue_review(task_id: str) -> Any:
    """
    Dispatch a petition review task.

    Returns the Taskiq task handle for status tracking.
    """
    return await run_petition_review.kiq(task_id=task_id)
