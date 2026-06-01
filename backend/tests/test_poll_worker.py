import asyncio

from src.gmail.poll_worker import CourtMailPollWorker


class _FakeIngestionService:
    def __init__(self):
        self.calls = 0

    async def poll_triggered_cases(self, max_results_per_trigger: int = 25):
        self.calls += 1
        return {
            "status": "completed",
            "triggers_polled": 1,
            "emails_scanned": 2,
            "documents_stored": 3,
            "max_results_per_trigger": max_results_per_trigger,
        }


def test_court_mail_poll_worker_run_once_updates_state():
    async def _run():
        fake_service = _FakeIngestionService()
        worker = CourtMailPollWorker(
            interval_seconds=5,
            max_results_per_trigger=10,
            ingestion_service=fake_service,
        )

        result = await worker.run_once()
        assert fake_service.calls == 1
        assert result["status"] == "completed"
        assert worker.last_run_at is not None
        assert worker.last_result is not None
        assert worker.last_result.get("documents_stored") == 3

    asyncio.run(_run())
