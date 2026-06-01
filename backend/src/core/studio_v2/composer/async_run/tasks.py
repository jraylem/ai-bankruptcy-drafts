"""V2 composer-async taskiq tasks.

Two coroutines, both decorated against `core_broker` (the same broker
v1 pleading uses — queue `taskiq:core`, worker
`src.core.components.pleading.broker:core_broker`). No new worker
container is needed; v2 composer tasks ride alongside v2 pleading
tasks on the existing `taskiq_worker_core` service.

- `run_composer_generate` — fresh template upload. PENDING → RUNNING
  → COMPLETED / FAILED.
- `run_composer_regenerate` — re-extract an existing template.
  PENDING → RUNNING → COMPLETED / FAILED.

Both call directly into the existing sync composer services
(`generate_template_v2`, `regenerate_template_v2`) — no fork, no
reimplementation. The async layer just adds Taskiq + Redis state +
SSE around the work.
"""

from __future__ import annotations

import logging
from typing import Any

from src.core.common.cost_tracking import cost_attribution
from src.core.components.pleading.broker import core_broker
from src.core.studio_v2.services.composer.generate import generate_template_v2
from src.core.studio_v2.services.composer.parse import parse_document_v2
from src.core.studio_v2.services.composer.regenerate import regenerate_template_v2

from . import events, state

logger = logging.getLogger(__name__)


async def _try_drain_user_queue(user_id: str) -> None:
    """At every terminal transition, see if a QUEUED task is waiting
    for a slot. Pops the oldest queued task_id, flips its status
    QUEUED → PENDING, kicks the appropriate worker by inspecting the
    record's `kind`. Emits status_changed so the FE pill lights up.
    """
    next_task_id = await state.drain_queue(user_id)
    if next_task_id is None:
        return
    record = await state.get(next_task_id)
    if record is None:
        logger.warning("composer drain_queue: task %s vanished, skipping", next_task_id)
        return
    await state.set_status(next_task_id, "PENDING")
    await events.emit(user_id, next_task_id, "status_changed")
    if record.kind == "generate":
        await run_composer_generate.kiq(task_id=next_task_id, user_id=user_id)
    else:
        await run_composer_regenerate.kiq(task_id=next_task_id, user_id=user_id)


@core_broker.task
async def run_composer_generate(task_id: str, user_id: str) -> None:
    """Fresh template upload — async wrapper around `generate_template_v2`.

    Reads the staged docx bytes from Redis (parked by the /generate
    HTTP handler), runs the full sync flow, persists the result, and
    emits SSE events at every transition.
    """
    record = await state.get(task_id)
    if record is None:
        logger.warning("run_composer_generate: task %s vanished before start", task_id)
        return
    with cost_attribution(
        firm_id=record.firm_id,
        user_id=user_id,
        session_id=task_id,
        semantic_id=task_id,
        semantic_id_kind="composer_async_v2",
    ):
        await _run_composer_generate_impl(task_id=task_id, user_id=user_id, record=record)


async def _run_composer_generate_impl(*, task_id: str, user_id: str, record) -> None:
    if await state.is_cancelled(task_id):
        logger.info("run_composer_generate: task %s already cancelled at start", task_id)
        return
    if not record.upload_blob_key:
        await state.set_failed(task_id, "Missing upload_blob_key — docx never staged")
        await events.emit(user_id, task_id, "failed")
        await _try_drain_user_queue(user_id)
        return

    file_content = await state.fetch_upload_blob(record.upload_blob_key)
    if file_content is None:
        await state.set_failed(
            task_id,
            "Staged upload expired or missing — please re-upload the .docx",
        )
        await events.emit(user_id, task_id, "failed")
        await _try_drain_user_queue(user_id)
        return

    await state.set_status(task_id, "RUNNING")
    await events.emit(user_id, task_id, "status_changed")

    try:
        parsed = await parse_document_v2(
            filename=record.original_filename or "uploaded.docx",
            file_content=file_content,
        )
        result = await generate_template_v2(
            template_name=record.template_name,
            parsed_document=parsed,
            file_content=file_content,
            template_role=record.template_role,
            firm_id=record.firm_id,
            user_id=user_id,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("generate_template_v2 failed for task %s", task_id)
        await state.set_failed(task_id, str(exc))
        await events.emit(user_id, task_id, "failed")
        await _try_drain_user_queue(user_id)
        return
    finally:
        await state.discard_upload_blob(record.upload_blob_key)

    if await state.is_cancelled(task_id):
        logger.info(
            "run_composer_generate: task %s cancelled before persisting result",
            task_id,
        )
        await _try_drain_user_queue(user_id)
        return

    await state.set_completed_generate(
        task_id, result=result, template_id=result.template_id,
    )
    await events.emit(user_id, task_id, "completed")
    await _try_drain_user_queue(user_id)


@core_broker.task
async def run_composer_regenerate(task_id: str, user_id: str) -> None:
    """Re-extract an existing template — async wrapper around
    `regenerate_template_v2`.
    """
    record = await state.get(task_id)
    if record is None:
        logger.warning("run_composer_regenerate: task %s vanished before start", task_id)
        return
    with cost_attribution(
        firm_id=record.firm_id,
        user_id=user_id,
        session_id=task_id,
        semantic_id=task_id,
        semantic_id_kind="composer_async_v2",
    ):
        await _run_composer_regenerate_impl(task_id=task_id, user_id=user_id, record=record)


async def _run_composer_regenerate_impl(*, task_id: str, user_id: str, record) -> None:
    if await state.is_cancelled(task_id):
        logger.info("run_composer_regenerate: task %s already cancelled at start", task_id)
        return
    if not record.template_id:
        await state.set_failed(task_id, "Missing template_id for regenerate")
        await events.emit(user_id, task_id, "failed")
        await _try_drain_user_queue(user_id)
        return

    await state.set_status(task_id, "RUNNING")
    await events.emit(user_id, task_id, "status_changed")

    try:
        result = await regenerate_template_v2(
            template_id=record.template_id,
            ignored_texts=record.ignored_texts,
            merges=record.merges,
            regeneration_instruction=record.regeneration_instruction,
            firm_id=record.firm_id,
            user_id=user_id,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("regenerate_template_v2 failed for task %s", task_id)
        await state.set_failed(task_id, str(exc))
        await events.emit(user_id, task_id, "failed")
        await _try_drain_user_queue(user_id)
        return

    if await state.is_cancelled(task_id):
        logger.info(
            "run_composer_regenerate: task %s cancelled before persisting result",
            task_id,
        )
        await _try_drain_user_queue(user_id)
        return

    await state.set_completed_regenerate(task_id, result=result)
    await events.emit(user_id, task_id, "completed")
    await _try_drain_user_queue(user_id)
