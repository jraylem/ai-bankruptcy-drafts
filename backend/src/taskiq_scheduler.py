"""
Taskiq scheduler configuration — TWO scheduler instances, one per broker.

TaskiqScheduler dispatches via the single broker it was constructed with;
it does NOT route to the task's declaring broker. A mixed-source scheduler
on the v1 broker enqueues v2 tasks onto the v1 queue, where the v1 worker
logs "task not found" and drops them. The split keeps each task on its
native queue:

  - `scheduler`       → v1 broker / queue 'taskiq'        → taskiq_worker
  - `core_scheduler`  → v2 core_broker / queue 'taskiq:core' → taskiq_worker_core

Each scheduler runs in its own container. Run with:
  v1: taskiq scheduler src.taskiq_scheduler:scheduler
  v2: taskiq scheduler src.taskiq_scheduler:core_scheduler

Adding a new scheduled task: (a) decorate against the broker whose worker
should execute it, (b) import its module here for the side-effect of
registration on the broker (LabelScheduleSource only sees tasks already
registered).
"""

from taskiq import TaskiqScheduler
from taskiq.schedule_sources import LabelScheduleSource

from src.core.components.pleading.broker import core_broker

from .taskiq_app import broker

# v1 scheduled tasks (registered against `broker`)
import src.tasks.cleanup_tasks_taskiq  # noqa: F401

# v2 scheduled tasks (registered against `core_broker`)
import src.core.components.case_inbox.tasks  # noqa: F401

scheduler = TaskiqScheduler(
    broker=broker,
    sources=[LabelScheduleSource(broker)],
)

core_scheduler = TaskiqScheduler(
    broker=core_broker,
    sources=[LabelScheduleSource(core_broker)],
)
