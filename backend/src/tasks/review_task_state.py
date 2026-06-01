"""Redis-backed task state management for petition review tasks."""
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


# Called by: ReviewTaskState methods (same file); review_orchestrator.py; review_tasks.py; route files
class ReviewTaskStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


ACTIVE_STATUSES = {ReviewTaskStatus.PENDING, ReviewTaskStatus.PROCESSING}
TERMINAL_STATUSES = {ReviewTaskStatus.COMPLETED, ReviewTaskStatus.FAILED, ReviewTaskStatus.CANCELLED}


# Called by: review_orchestrator.start_review_task() (tasks/review_orchestrator.py),
#            review_tasks.run_petition_review() (tasks/review_tasks.py),
#            route files (status, cancel endpoints)
class ReviewTaskState:
    TASK_PREFIX = "review_task:"
    USER_TASKS_PREFIX = "review_user_tasks:"
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

    # Called by: review_orchestrator.start_review_task() (tasks/review_orchestrator.py)
    def create_task(
        self,
        user_id: str,
        session_id: str,
        case_name: str,
        pdf_path: str
    ) -> str:
        """Create a new review task record in Redis and return its task_id."""
        task_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        task_data = {
            "task_id": task_id,
            "user_id": user_id,
            "session_id": session_id,
            "case_name": case_name,
            "pdf_path": pdf_path,
            "status": ReviewTaskStatus.PENDING.value,
            "progress_message": "Review queued for processing",
            "created_at": now,
            "updated_at": now,
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

        emit_task_event(task_data, "review", "status_changed")

        return task_id

    # Called by: all ReviewTaskState methods (same file); review_tasks.py; route files
    def get_task(self, task_id: str) -> Optional[dict]:
        """Retrieve a review task dict from Redis, or None if not found/expired."""
        data = self.redis.get(self._task_key(task_id))
        if data is None:
            return None
        return json.loads(data)

    # Called by: review_tasks.run_petition_review() (tasks/review_tasks.py)
    def update_status(
        self,
        task_id: str,
        status: ReviewTaskStatus,
        progress_message: Optional[str] = None
    ) -> bool:
        """Update task status and optionally its progress_message.

        Returns:
            True if updated, False if task not found.
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

        if status == ReviewTaskStatus.CANCELLED:
            self.redis.srem(self._user_tasks_key(task["user_id"]), task_id)

        if status == ReviewTaskStatus.COMPLETED:
            emit_task_event(task, "review", "completed")
        elif status == ReviewTaskStatus.FAILED:
            emit_task_event(task, "review", "failed")
        elif status == ReviewTaskStatus.CANCELLED:
            emit_task_event(task, "review", "cancelled")
        else:
            emit_task_event(task, "review", "status_changed")

        return True

    # Called by: review_tasks._create_progress_callback() (tasks/review_tasks.py)
    def update_progress(self, task_id: str, progress_message: str) -> bool:
        """Update only the progress message without changing status."""
        task = self.get_task(task_id)
        if task is None:
            return False

        task["progress_message"] = progress_message
        task["updated_at"] = datetime.now(timezone.utc).isoformat()

        self.redis.setex(
            self._task_key(task_id),
            self.TASK_TTL,
            json.dumps(task)
        )

        emit_task_event(task, "review", "progress")
        return True

    # Called by: review_orchestrator.start_review_task() (tasks/review_orchestrator.py)
    def set_worker_task_id(self, task_id: str, worker_task_id: str) -> bool:
        """Persist the worker (TaskIQ) task ID onto the review task record.

        Returns:
            True if updated, False if task not found.
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

    # Called by: review_tasks.run_petition_review() (tasks/review_tasks.py)
    def set_result(
        self,
        task_id: str,
        debtor_name: str,
        case_number: str,
        master_review: str,
        group_reviews: dict[str, Any]
    ) -> bool:
        """Mark task as COMPLETED and store the review result data.

        Returns:
            True if updated, False if task not found.
        """
        task = self.get_task(task_id)
        if task is None:
            return False

        task["status"] = ReviewTaskStatus.COMPLETED.value
        task["progress_message"] = "Review completed successfully"
        task["updated_at"] = datetime.now(timezone.utc).isoformat()
        task["result"] = {
            "debtor_name": debtor_name,
            "case_number": case_number,
            "master_review": master_review,
            "group_reviews": group_reviews
        }

        self.redis.setex(
            self._task_key(task_id),
            self.TASK_TTL,
            json.dumps(task)
        )

        emit_task_event(task, "review", "completed")
        return True

    # Called by: review_tasks.run_petition_review() (tasks/review_tasks.py)
    def set_error(self, task_id: str, error_message: str) -> bool:
        """Mark task as FAILED with an error message.

        Returns:
            True if updated, False if task not found.
        """
        task = self.get_task(task_id)
        if task is None:
            return False

        task["status"] = ReviewTaskStatus.FAILED.value
        task["progress_message"] = "Review failed"
        task["error"] = error_message
        task["updated_at"] = datetime.now(timezone.utc).isoformat()

        self.redis.setex(
            self._task_key(task_id),
            self.TASK_TTL,
            json.dumps(task)
        )

        emit_task_event(task, "review", "failed")
        return True

    # Called by: route files (cancel review task endpoint)
    def cancel_task(self, task_id: str) -> bool:
        """Cancel a non-terminal review task.

        Returns:
            True if cancelled, False if not found or already in a terminal state.
        """
        task = self.get_task(task_id)
        if task is None:
            return False

        if task["status"] in [s.value for s in TERMINAL_STATUSES]:
            return False

        task["status"] = ReviewTaskStatus.CANCELLED.value
        task["progress_message"] = "Review cancelled by user"
        task["updated_at"] = datetime.now(timezone.utc).isoformat()

        self.redis.setex(
            self._task_key(task_id),
            self.TASK_TTL,
            json.dumps(task)
        )

        self.redis.srem(self._user_tasks_key(task["user_id"]), task_id)

        emit_task_event(task, "review", "cancelled")
        return True

    # Called by: review_tasks.run_petition_review() (tasks/review_tasks.py)
    def is_cancelled(self, task_id: str) -> bool:
        """Return True if review task is cancelled or no longer exists."""
        task = self.get_task(task_id)
        if task is None:
            return True
        return task["status"] == ReviewTaskStatus.CANCELLED.value

    def _fetch_user_tasks(self, user_id: str, allowed_statuses: set[str]) -> list[dict]:
        """Pipeline-fetch all task hashes for a user and self-heal stale set members."""
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

    # Called by: review_orchestrator.start_review_task() (tasks/review_orchestrator.py);
    #            count_active_tasks() (same file)
    def get_active_tasks(self, user_id: str) -> list[dict]:
        """Return all non-terminal review tasks for a user, sorted newest-first."""
        return self._fetch_user_tasks(user_id, {s.value for s in ACTIVE_STATUSES})

    # Called by: SSE snapshot, /tasks list endpoint
    def get_visible_tasks(self, user_id: str) -> list[dict]:
        """Return all tasks the user has not dismissed (active + completed + failed).

        CANCELLED tasks are excluded — cancellation is the user's own dismiss action.
        """
        visible_statuses = (
            {s.value for s in ACTIVE_STATUSES}
            | {ReviewTaskStatus.COMPLETED.value, ReviewTaskStatus.FAILED.value}
        )
        return self._fetch_user_tasks(user_id, visible_statuses)

    # Called by: can_start_new_task() (same file)
    def count_active_tasks(self, user_id: str) -> int:
        """Return the number of currently active review tasks for a user."""
        return len(self.get_active_tasks(user_id))

    # Called by: review_orchestrator.start_review_task() (tasks/review_orchestrator.py)
    def can_start_new_task(self, user_id: str) -> bool:
        """Return True if the user is below the MAX_CONCURRENT_REVIEW_TASKS limit."""
        return self.count_active_tasks(user_id) < settings.MAX_CONCURRENT_REVIEW_TASKS

    # Called by: review_orchestrator.start_review_task() (tasks/review_orchestrator.py)
    def has_active_task_for_session(self, session_id: str) -> bool:
        """Check if there's already an active review task for this session."""
        for key in self.redis.scan_iter(match=f"{self.TASK_PREFIX}*"):
            task_data = self.redis.get(key)
            if task_data:
                task = json.loads(task_data)
                if (task.get("session_id") == session_id and
                    task.get("status") in [s.value for s in ACTIVE_STATUSES]):
                    return True
        return False

    # Called by: route files (delete review task endpoint)
    def delete_task(self, task_id: str) -> bool:
        """Permanently delete a review task from Redis (user-initiated dismiss).

        Returns:
            True if deleted, False if task not found.
        """
        task = self.get_task(task_id)
        if task is None:
            return False

        self.redis.delete(self._task_key(task_id))
        self.redis.srem(self._user_tasks_key(task["user_id"]), task_id)

        emit_task_event(task, "review", "removed")
        return True

    def cleanup_stale_tasks(self, stale_threshold_minutes: int = 35) -> dict[str, int]:
        """Scan for and cleanup stale review tasks that have been stuck in active status.

        A task is considered stale if:
        - Status is in ACTIVE_STATUSES (PENDING, PROCESSING)
        - updated_at is older than stale_threshold_minutes

        Note: Review tasks have a higher threshold (35 min) because they can take up to 30 min.

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
                        f"Cleaning up stale review task {task_id}: "
                        f"status={status}, updated_at={updated_at_str}"
                    )

                    task["status"] = ReviewTaskStatus.FAILED.value
                    task["progress_message"] = "Review timed out (stale cleanup)"
                    task["error"] = f"Task was stuck in {status} state for over {stale_threshold_minutes} minutes"
                    task["updated_at"] = datetime.now(timezone.utc).isoformat()

                    self.redis.setex(key, self.TASK_TTL, json.dumps(task))

                    if user_id:
                        self.redis.srem(self._user_tasks_key(user_id), task_id)

                    stats["cleaned"] += 1

            except Exception as e:
                logger.exception(f"Error cleaning up review task {key}: {e}")
                stats["errors"] += 1

        return stats


# Called by: review_orchestrator.py, review_tasks.py, and route files (imported as `review_task_state`)
review_task_state = ReviewTaskState()
