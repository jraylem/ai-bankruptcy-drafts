"""Redis-backed task state management for two-phase pleading generation."""
import json
import logging
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

import redis

from ..config import settings
from .event_stream import emit_task_event
from .redis_client import make_sync_redis

logger = logging.getLogger(__name__)


# Called by: PleadingTaskState methods (same file); pleading_tasks.py; orchestrator.py; route files
class TaskStatus(str, Enum):
    PENDING = "PENDING"
    CHECKING_EXISTING = "CHECKING_EXISTING"
    EXISTING_FOUND = "EXISTING_FOUND"
    EXTRACTING = "EXTRACTING"
    AWAITING_INPUT = "AWAITING_INPUT"
    GENERATING = "GENERATING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


ACTIVE_STATUSES = {
    TaskStatus.PENDING,
    TaskStatus.CHECKING_EXISTING,
    TaskStatus.EXISTING_FOUND,
    TaskStatus.EXTRACTING,
    TaskStatus.AWAITING_INPUT,
    TaskStatus.GENERATING
}
TERMINAL_STATUSES = {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}


# Called by: orchestrator.start_pleading_generation() (tasks/orchestrator.py),
#            pleading_tasks.extract_pleading_payload() (tasks/pleading_tasks.py),
#            pleading_tasks.generate_pleading_documents() (tasks/pleading_tasks.py),
#            route files (cancel, submit-input, status endpoints)
class PleadingTaskState:
    TASK_PREFIX = "pleading_task:"
    USER_TASKS_PREFIX = "user_tasks:"
    TASK_TTL = 7200

    def __init__(self):
        self._redis: Optional[redis.Redis] = None

    @property
    def redis(self) -> redis.Redis:
        if self._redis is None:
            self._redis = make_sync_redis()
        return self._redis

    def _task_key(self, task_id: str) -> str:
        return f"{self.TASK_PREFIX}{task_id}"

    def _user_tasks_key(self, user_id: str) -> str:
        return f"{self.USER_TASKS_PREFIX}{user_id}"

    # Called by: orchestrator.start_pleading_generation() (tasks/orchestrator.py)
    def create_task(
        self,
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
    ) -> str:
        """Create a new task record in Redis and return its task_id.

        Args:
            user_id: Authenticated user identifier.
            session_id: Active session identifier.
            motion_type: Motion type key (e.g., "extend", "claim").
            case_name: Human-readable debtor/case name for display.
            source: Data source — "gmail" or "courtdrive".
            include_cos: Whether to include certificate of service generation.
            include_order_sustaining: Whether to include order sustaining generation.
            modification_type: For "modify" motion - "delinquent", "creditor_alteration", or "both".
            extension_type: For "extend" motion - "regular" or "expedite".

        Returns:
            UUID string for the newly created task.
        """
        from .orchestrator import get_motion_display_name

        task_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        task_data = {
            "task_id": task_id,
            "user_id": user_id,
            "session_id": session_id,
            "motion_type": motion_type,
            "motion_type_display": get_motion_display_name(motion_type),
            "case_name": case_name,
            "source": source,
            "include_cos": include_cos,
            "include_order_sustaining": include_order_sustaining,
            "initial_user_input": initial_user_input,
            "skip_existing_check": skip_existing_check,
            "modification_type": modification_type,
            "extension_type": extension_type,
            "status": TaskStatus.PENDING.value,
            "progress_message": "Task queued for processing",
            "created_at": now,
            "updated_at": now,
            "input_required": None,
            "user_input": None,
            "result": None,
            "error": None,
            "worker_task_id": None,
        }

        self.redis.setex(
            self._task_key(task_id),
            self.TASK_TTL,
            json.dumps(task_data)
        )

        self.redis.sadd(self._user_tasks_key(user_id), task_id)

        emit_task_event(task_data, "pleading", "status_changed")

        return task_id

    # Called by: all PleadingTaskState methods (same file); pleading_tasks.py; route files
    def get_task(self, task_id: str) -> Optional[dict]:
        """Retrieve a task dict from Redis by task_id, or None if not found/expired."""
        data = self.redis.get(self._task_key(task_id))
        if data is None:
            return None
        return json.loads(data)

    # Called by: pleading_tasks.extract_pleading_payload(),
    #            pleading_tasks.generate_pleading_documents() (tasks/pleading_tasks.py)
    def update_status(
        self,
        task_id: str,
        status: TaskStatus,
        progress_message: Optional[str] = None
    ) -> bool:
        """Update the status (and optionally progress_message) of a task.

        Returns:
            True if updated successfully, False if task not found.
        """
        task = self.get_task(task_id)
        if task is None:
            return False

        task["status"] = status.value
        task["updated_at"] = datetime.now(timezone.utc).isoformat()

        if progress_message is not None:
            task["progress_message"] = progress_message

        self.redis.setex(
            self._task_key(task_id),
            self.TASK_TTL,
            json.dumps(task)
        )

        if status == TaskStatus.CANCELLED:
            self.redis.srem(self._user_tasks_key(task["user_id"]), task_id)

        if status == TaskStatus.COMPLETED:
            emit_task_event(task, "pleading", "completed")
        elif status == TaskStatus.FAILED:
            emit_task_event(task, "pleading", "failed")
        elif status == TaskStatus.CANCELLED:
            emit_task_event(task, "pleading", "cancelled")
        else:
            emit_task_event(task, "pleading", "status_changed")

        return True

    # Called by: orchestrator.start_pleading_generation() (tasks/orchestrator.py)
    def set_worker_task_id(self, task_id: str, worker_task_id: str) -> bool:
        """Persist the worker (TaskIQ) task ID onto the task record.

        Returns:
            True if updated successfully, False if task not found.
        """
        task = self.get_task(task_id)
        if task is None:
            return False

        task["worker_task_id"] = worker_task_id
        task["updated_at"] = datetime.now(timezone.utc).isoformat()

        self.redis.setex(
            self._task_key(task_id),
            self.TASK_TTL,
            json.dumps(task)
        )
        return True

    # Called by: pleading_tasks.extract_pleading_payload() (tasks/pleading_tasks.py)
    def set_input_required(
        self,
        task_id: str,
        fields: list[str],
        prefilled: dict[str, Any],
        suggestions: dict[str, list] = None,
        missing_field: str = None,
        missing_fields: list[str] = None,
        custom_message: str = None,
    ) -> bool:
        """Transition task to AWAITING_INPUT and store the prefilled fields.

        Args:
            suggestions: Optional dict of { field_name: [chip1, chip2, chip3] }
                         for rendering recommendation chips on the frontend.
            missing_field: Optional field name that triggered the AWAITING_INPUT
                           (e.g., "dismissed_case_number", "trustees_reason", "prior_case_info")
            missing_fields: Optional list of field names for composite inputs
                            (e.g., ["dismissed_case_number", "docket_entry_no", "dismissal_date"])
            custom_message: Optional custom message to display to the user

        Returns:
            True if updated successfully, False if task not found.
        """
        task = self.get_task(task_id)
        if task is None:
            return False

        task["status"] = TaskStatus.AWAITING_INPUT.value
        task["progress_message"] = custom_message or "Waiting for user input"
        task["updated_at"] = datetime.now(timezone.utc).isoformat()
        task["input_required"] = {
            "fields": fields,
            "prefilled": prefilled,
            "suggestions": suggestions or {},
        }

        # Add missing_field and message for intermediate input prompts
        if missing_field:
            task["input_required"]["missing_field"] = missing_field
        if missing_fields:
            task["input_required"]["missing_fields"] = missing_fields
        if custom_message:
            task["input_required"]["message"] = custom_message

        self.redis.setex(
            self._task_key(task_id),
            self.TASK_TTL,
            json.dumps(task)
        )

        emit_task_event(task, "pleading", "input_required")
        return True

    # Called by: route files (user input submission endpoint)
    def submit_input(self, task_id: str, user_input: dict[str, Any]) -> bool:
        """Accept user-supplied field values and advance task to GENERATING.

        Returns:
            True if accepted, False if task not found or not in AWAITING_INPUT state.
        """
        task = self.get_task(task_id)
        if task is None:
            return False

        if task["status"] != TaskStatus.AWAITING_INPUT.value:
            return False

        task["user_input"] = user_input
        task["status"] = TaskStatus.GENERATING.value
        task["progress_message"] = "Input received, generating documents..."
        task["updated_at"] = datetime.now(timezone.utc).isoformat()

        self.redis.setex(
            self._task_key(task_id),
            self.TASK_TTL,
            json.dumps(task)
        )

        emit_task_event(task, "pleading", "status_changed")
        return True

    # Called by: pleading_tasks.generate_pleading_documents() (tasks/pleading_tasks.py)
    def set_result(
        self,
        task_id: str,
        documents: dict[str, Any],
        payload: dict[str, Any]
    ) -> bool:
        """Mark task as COMPLETED and store the generated document URLs + payload.

        Returns:
            True if updated successfully, False if task not found.
        """
        task = self.get_task(task_id)
        if task is None:
            return False

        task["status"] = TaskStatus.COMPLETED.value
        task["progress_message"] = "Documents generated successfully"
        task["updated_at"] = datetime.now(timezone.utc).isoformat()
        task["result"] = {
            "documents": documents,
            "payload": payload
        }

        self.redis.setex(
            self._task_key(task_id),
            self.TASK_TTL,
            json.dumps(task)
        )

        emit_task_event(task, "pleading", "completed")
        return True

    # Called by: pleading_tasks.extract_pleading_payload(),
    #            pleading_tasks.generate_pleading_documents() (tasks/pleading_tasks.py)
    def set_error(self, task_id: str, error_message: str) -> bool:
        """Mark task as FAILED with an error message.

        Returns:
            True if updated successfully, False if task not found.
        """
        task = self.get_task(task_id)
        if task is None:
            return False

        task["status"] = TaskStatus.FAILED.value
        task["progress_message"] = "Task failed"
        task["error"] = error_message
        task["updated_at"] = datetime.now(timezone.utc).isoformat()

        self.redis.setex(
            self._task_key(task_id),
            self.TASK_TTL,
            json.dumps(task)
        )

        emit_task_event(task, "pleading", "failed")
        return True

    # Called by: route files (cancel task endpoint)
    def cancel_task(self, task_id: str) -> bool:
        """Cancel a non-terminal task and remove it from the user's active set.

        Returns:
            True if cancelled, False if not found or already in a terminal state.
        """
        task = self.get_task(task_id)
        if task is None:
            return False

        if task["status"] in [s.value for s in TERMINAL_STATUSES]:
            return False

        task["status"] = TaskStatus.CANCELLED.value
        task["progress_message"] = "Task cancelled by user"
        task["updated_at"] = datetime.now(timezone.utc).isoformat()

        self.redis.setex(
            self._task_key(task_id),
            self.TASK_TTL,
            json.dumps(task)
        )

        self.redis.srem(self._user_tasks_key(task["user_id"]), task_id)

        emit_task_event(task, "pleading", "cancelled")
        return True

    # Called by: pleading_tasks.extract_pleading_payload() (tasks/pleading_tasks.py)
    def is_cancelled(self, task_id: str) -> bool:
        """Return True if task is cancelled or no longer exists."""
        task = self.get_task(task_id)
        if task is None:
            return True
        return task["status"] == TaskStatus.CANCELLED.value

    def _fetch_user_tasks(self, user_id: str, allowed_statuses: set[str]) -> list[dict]:
        """Pipeline-fetch all task hashes for a user and self-heal stale set members.

        Cuts N+1 round trips on the Redis proxy down to two pipeline calls,
        and SREMs any task_id whose hash has expired so the user_tasks set
        cannot grow unbounded.
        """
        user_tasks_key = self._user_tasks_key(user_id)
        task_ids = list(self.redis.smembers(user_tasks_key))
        if not task_ids:
            return []

        pipe = self.redis.pipeline(transaction=False)
        for task_id in task_ids:
            pipe.get(self._task_key(task_id))
        raw_tasks = pipe.execute()

        tasks: list[dict] = []
        stale_ids: list[str] = []
        for task_id, data in zip(task_ids, raw_tasks):
            if data is None:
                stale_ids.append(task_id)
                continue
            task = json.loads(data)
            if task["status"] in allowed_statuses:
                tasks.append(task)

        if stale_ids:
            self.redis.srem(user_tasks_key, *stale_ids)

        tasks.sort(key=lambda t: t["created_at"], reverse=True)
        return tasks

    # Called by: orchestrator.start_pleading_generation() (tasks/orchestrator.py);
    #            count_active_tasks() (same file)
    def get_active_tasks(self, user_id: str) -> list[dict]:
        """Return all non-terminal tasks for a user, sorted newest-first."""
        return self._fetch_user_tasks(user_id, {s.value for s in ACTIVE_STATUSES})

    # Called by: SSE snapshot, /tasks list endpoint
    def get_visible_tasks(self, user_id: str) -> list[dict]:
        """Return all tasks the user has not dismissed (active + completed + failed).

        Used to rehydrate the FE on refresh so terminal cards persist until the
        user explicitly dismisses them or the 2h Redis TTL expires. CANCELLED
        tasks are excluded — cancellation is the user's own dismiss action.
        """
        visible_statuses = (
            {s.value for s in ACTIVE_STATUSES}
            | {TaskStatus.COMPLETED.value, TaskStatus.FAILED.value}
        )
        return self._fetch_user_tasks(user_id, visible_statuses)

    # Called by: route files (DELETE /tasks/{task_id} endpoint)
    def delete_task(self, task_id: str) -> bool:
        """Permanently delete a task record (user-initiated dismiss).

        Removes both the task record and its membership in the user's set,
        then emits a 'removed' event so other tabs/devices drop the card too.

        Returns:
            True if deleted, False if task not found.
        """
        task = self.get_task(task_id)
        if task is None:
            return False

        self.redis.delete(self._task_key(task_id))
        self.redis.srem(self._user_tasks_key(task["user_id"]), task_id)

        emit_task_event(task, "pleading", "removed")
        return True

    # Called by: can_start_new_task() (same file)
    def count_active_tasks(self, user_id: str) -> int:
        """Return the number of currently active (non-terminal) tasks for a user."""
        return len(self.get_active_tasks(user_id))

    # Called by: orchestrator.start_pleading_generation() (tasks/orchestrator.py)
    def can_start_new_task(self, user_id: str) -> bool:
        """Return True if the user is below the MAX_CONCURRENT_PLEADING_TASKS limit."""
        return self.count_active_tasks(user_id) < settings.MAX_CONCURRENT_PLEADING_TASKS

    # Called by: pleading_tasks.extract_pleading_payload() (tasks/pleading_tasks.py)
    def get_user_input(self, task_id: str, timeout: float = 300.0, poll_interval: float = 1.0) -> Optional[dict]:
        """Poll Redis until user_input is submitted or timeout is reached.

        Args:
            task_id: Task to poll.
            timeout: Max seconds to wait before returning None.
            poll_interval: Seconds between Redis checks.

        Returns:
            User-supplied input dict, or None if cancelled/timed out.
        """
        import time

        elapsed = 0.0
        while elapsed < timeout:
            task = self.get_task(task_id)
            if task is None:
                return None

            if task["status"] == TaskStatus.CANCELLED.value:
                return None

            if task["user_input"] is not None:
                return task["user_input"]

            time.sleep(poll_interval)
            elapsed += poll_interval

        return None

    # Called by: pleading_tasks.extract_pleading_payload() (tasks/pleading_tasks.py)
    def store_extracted_payloads(
        self,
        task_id: str,
        motion_payload: Optional[dict],
        service_payload: Optional[dict],
        order_sustaining_payload: Optional[dict] = None
    ) -> bool:
        """Store extracted payloads for later use in document generation phase."""
        task = self.get_task(task_id)
        if task is None:
            return False

        task["extracted_payloads"] = {
            "motion_payload": motion_payload,
            "service_payload": service_payload,
            "order_sustaining_payload": order_sustaining_payload
        }
        task["updated_at"] = datetime.now(timezone.utc).isoformat()

        self.redis.setex(
            self._task_key(task_id),
            self.TASK_TTL,
            json.dumps(task)
        )
        return True

    # Called by: pleading_tasks.generate_pleading_documents() (tasks/pleading_tasks.py)
    def get_extracted_payloads(self, task_id: str) -> Optional[dict]:
        """Retrieve stored extracted payloads for document generation."""
        task = self.get_task(task_id)
        if task is None:
            return None
        return task.get("extracted_payloads")

    # Called by: pleading_tasks.extract_pleading_payload() (tasks/pleading_tasks.py)
    def set_existing_found(
        self,
        task_id: str,
        existing_documents: dict[str, Any]
    ) -> bool:
        """Set task to EXISTING_FOUND state with document URLs."""
        task = self.get_task(task_id)
        if task is None:
            return False

        task["status"] = TaskStatus.EXISTING_FOUND.value
        task["progress_message"] = "Existing document found"
        task["updated_at"] = datetime.now(timezone.utc).isoformat()
        task["existing_documents"] = existing_documents

        self.redis.setex(
            self._task_key(task_id),
            self.TASK_TTL,
            json.dumps(task)
        )

        emit_task_event(task, "pleading", "existing_found")
        return True

    # Called by: route files (regenerate / continue-to-extract endpoint)
    def continue_to_extract(self, task_id: str) -> bool:
        """Continue from EXISTING_FOUND to EXTRACTING when user chooses to regenerate."""
        task = self.get_task(task_id)
        if task is None:
            return False

        if task["status"] != TaskStatus.EXISTING_FOUND.value:
            return False

        task["status"] = TaskStatus.EXTRACTING.value
        task["progress_message"] = "Extracting case information..."
        task["updated_at"] = datetime.now(timezone.utc).isoformat()
        task["existing_documents"] = None
        task["regenerate"] = True

        self.redis.setex(
            self._task_key(task_id),
            self.TASK_TTL,
            json.dumps(task)
        )

        emit_task_event(task, "pleading", "status_changed")
        return True

    # Called by: pleading_tasks.extract_pleading_payload() (tasks/pleading_tasks.py)
    def should_wait_for_existing_decision(self, task_id: str) -> bool:
        """Check if task is waiting for user decision on existing document."""
        task = self.get_task(task_id)
        if task is None:
            return False
        return task["status"] == TaskStatus.EXISTING_FOUND.value

    # Called by: pleading_tasks.extract_pleading_payload() (tasks/pleading_tasks.py)
    def wait_for_existing_decision(
        self,
        task_id: str,
        timeout: float = 300.0,
        poll_interval: float = 1.0
    ) -> Optional[str]:
        """Wait for user to decide whether to use existing or regenerate.
        Returns 'regenerate' if user chose to regenerate, 'use_existing' if cancelled/completed, None if timeout."""
        import time

        elapsed = 0.0
        while elapsed < timeout:
            task = self.get_task(task_id)
            if task is None:
                return None

            if task["status"] == TaskStatus.CANCELLED.value:
                return "use_existing"

            if task["status"] == TaskStatus.COMPLETED.value:
                return "use_existing"

            if task.get("regenerate"):
                return "regenerate"

            if task["status"] == TaskStatus.EXTRACTING.value:
                return "regenerate"

            time.sleep(poll_interval)
            elapsed += poll_interval

        return None

    def cleanup_stale_tasks(self, stale_threshold_minutes: int = 15) -> dict[str, int]:
        """Scan for and cleanup stale tasks that have been stuck in active status.

        A task is considered stale if:
        - Status is in ACTIVE_STATUSES (PENDING, CHECKING_EXISTING, EXTRACTING, GENERATING, etc.)
        - updated_at is older than stale_threshold_minutes

        Returns:
            Dict with counts: {"scanned": N, "cleaned": N, "errors": N}
        """
        from datetime import timedelta

        stats = {"scanned": 0, "cleaned": 0, "errors": 0}
        threshold = datetime.now(timezone.utc) - timedelta(minutes=stale_threshold_minutes)

        for key in self.redis.scan_iter(match=f"{self.TASK_PREFIX}*"):
            stats["scanned"] += 1
            try:
                task_data = self.redis.get(key)
                if not task_data:
                    continue

                task = json.loads(task_data)
                status = task.get("status")
                updated_at_str = task.get("updated_at")

                if status not in [s.value for s in ACTIVE_STATUSES]:
                    continue

                if not updated_at_str:
                    continue

                updated_at = datetime.fromisoformat(updated_at_str.replace("Z", "+00:00"))
                if updated_at < threshold:
                    task_id = task.get("task_id")
                    user_id = task.get("user_id")

                    logger.warning(
                        f"Cleaning up stale pleading task {task_id}: "
                        f"status={status}, updated_at={updated_at_str}"
                    )

                    task["status"] = TaskStatus.FAILED.value
                    task["progress_message"] = "Task timed out (stale cleanup)"
                    task["error"] = f"Task was stuck in {status} state for over {stale_threshold_minutes} minutes"
                    task["updated_at"] = datetime.now(timezone.utc).isoformat()

                    self.redis.setex(key, self.TASK_TTL, json.dumps(task))

                    if user_id:
                        self.redis.srem(self._user_tasks_key(user_id), task_id)

                    stats["cleaned"] += 1

            except Exception as e:
                logger.exception(f"Error cleaning up task {key}: {e}")
                stats["errors"] += 1

        return stats


# Called by: orchestrator.py, pleading_tasks.py, and route files (imported as `task_state`)
task_state = PleadingTaskState()
