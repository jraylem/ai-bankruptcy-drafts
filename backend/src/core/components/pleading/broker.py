"""Dedicated taskiq broker for the v2 template-draft pipeline.

Separate from `src.taskiq_app.broker` so a distinct worker process owns
v2 jobs (queue_name `taskiq:core`). Both brokers share the same Redis
instance — taskiq's queue_name keeps the work isolated.

Worker invocation:
    taskiq worker src.core.components.pleading.broker:core_broker
"""

from taskiq_redis import ListQueueBroker, RedisAsyncResultBackend

from src.config import settings

core_broker = ListQueueBroker(
    url=settings.REDIS_URL,
    queue_name="taskiq:core",
).with_result_backend(
    RedisAsyncResultBackend(redis_url=settings.REDIS_URL)
)

# Register the v2 tasks on this broker — must happen at module import so the
# worker discovers them when launching against `core_broker`. EVERY task module
# that decorates against core_broker needs an explicit import here, otherwise
# the worker logs "unknown task" and discards the scheduler's messages.
from . import tasks  # noqa: F401, E402  (pleading: run_template_draft, run_template_draft_resume)
from src.core.components.case_inbox import tasks as _case_inbox_tasks  # noqa: F401, E402  (case_inbox: ingest_ecf_inbox, archive_stale_inbox)
from src.core.studio_v2.composer.async_run import tasks as _composer_async_tasks  # noqa: F401, E402  (composer-async: run_composer_generate, run_composer_regenerate)
from src.core.studio_v2.dry_run.async_run import tasks as _dry_run_async_tasks  # noqa: F401, E402  (dry-run-async: run_dry_run_initial, run_dry_run_resume)

# Register every ORM mapper the worker can touch. SQLAlchemy resolves
# string-form relationship targets ("MotionComment", etc.) lazily on
# first query — if the target's module hasn't been imported by then,
# `_configure_registries` raises and EVERY subsequent DB call fails.
# src.main does the same import for the FastAPI app; the worker needs
# its own copy because it doesn't go through main.py.
from src.collaboration import models as _collaboration_models  # noqa: F401, E402  (MotionComment, FirmChatRoom, FirmChatMessage)
