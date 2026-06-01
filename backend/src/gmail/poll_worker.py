"""Background scheduler/worker for court-mail trigger polling."""

from __future__ import annotations

import asyncio
import json
from contextlib import suppress
from datetime import datetime, timezone
from typing import Optional

import redis

from ..tasks.redis_client import make_sync_redis
from .workflow_services import EmailIngestionService

_REDIS_KEY = "poll_worker:court_mail:last_run"
_REDIS_TTL = 60 * 60 * 24 * 7  # 7 days

_redis_client_singleton: Optional[redis.Redis] = None


def _redis_client() -> redis.Redis:
    global _redis_client_singleton
    if _redis_client_singleton is None:
        _redis_client_singleton = make_sync_redis()
    return _redis_client_singleton


class CourtMailPollWorker:
    """Periodically polls active court-mail triggers and ingests matching emails."""

    def __init__(
        self,
        interval_seconds: int = 60,
        max_results_per_trigger: int = 25,
        ingestion_service: Optional[EmailIngestionService] = None,
    ):
        self.interval_seconds = max(5, int(interval_seconds))
        self.max_results_per_trigger = max(1, min(200, int(max_results_per_trigger)))
        self.ingestion_service = ingestion_service or EmailIngestionService()
        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
        self._last_run_at: Optional[str] = None
        self._last_result: Optional[dict] = None

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    @property
    def last_run_at(self) -> Optional[str]:
        return self._last_run_at

    @property
    def last_result(self) -> Optional[dict]:
        return self._last_result

    async def start(self, run_immediately: bool = False) -> None:
        if self.is_running:
            return

        self._stop_event.clear()
        self._task = asyncio.create_task(
            self._run_loop(run_immediately=run_immediately),
            name="court_mail_poll_worker",
        )
        print(
            "[worker] Court-mail poll worker started "
            f"(interval={self.interval_seconds}s, max_results={self.max_results_per_trigger})"
        )

    async def stop(self) -> None:
        if not self._task:
            return

        self._stop_event.set()
        self._task.cancel()
        with suppress(asyncio.CancelledError):
            await self._task

        self._task = None
        print("[worker] Court-mail poll worker stopped")

    async def run_once(self) -> dict:
        started_at = datetime.now(timezone.utc).isoformat()
        result = await self.ingestion_service.poll_triggered_cases(
            max_results_per_trigger=self.max_results_per_trigger
        )
        self._last_run_at = started_at
        self._last_result = result
        # Persist to Redis so all processes/workers see the latest state
        try:
            _redis_client().setex(
                _REDIS_KEY,
                _REDIS_TTL,
                json.dumps({"last_run_at": started_at, "last_result": result}),
            )
        except Exception:
            pass  # Redis persistence is best-effort; in-memory state is the source of truth
        return result

    async def _run_loop(self, run_immediately: bool = False) -> None:
        if run_immediately:
            await self._safe_run_once()

        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.interval_seconds)
                break
            except asyncio.TimeoutError:
                pass

            await self._safe_run_once()

    async def _safe_run_once(self) -> None:
        try:
            result = await self.run_once()
            print(
                "[worker] Court-mail poll completed: "
                f"triggers={result.get('triggers_polled', 0)} "
                f"emails={result.get('emails_scanned', 0)} "
                f"docs={result.get('documents_stored', 0)}"
            )
        except Exception as exc:
            self._last_run_at = datetime.now(timezone.utc).isoformat()
            self._last_result = {"status": "failed", "error": str(exc)}
            try:
                _redis_client().setex(
                    _REDIS_KEY,
                    _REDIS_TTL,
                    json.dumps({"last_run_at": self._last_run_at, "last_result": self._last_result}),
                )
            except Exception:
                pass
            print(f"[worker] Court-mail poll failed: {exc}")
