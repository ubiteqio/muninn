"""The Celery application. API, worker and scheduler share one image and differ in the command.

    celery -A muninn.huginn.app worker --queues scan
    celery -A muninn.huginn.app worker --queues derive
    celery -A muninn.huginn.app worker --queues ai --concurrency 2
    celery -A muninn.huginn.app beat

The configuration is read lazily: the API imports this module to queue a scan, and importing it
must not depend on a complete environment.
"""

from typing import Any

from celery import Celery
from celery.schedules import crontab
from celery.signals import worker_ready, worker_shutdown

from muninn.core.config import get_settings
from muninn.huginn import runtime

#: The scheduler only ticks; when a sync is due follows from the settings in the database, so a
#: changed interval takes effect without restarting anything.
TICK_SECONDS = 60

celery_app = Celery("muninn")


def configuration() -> dict[str, Any]:
    """Read when Celery first needs it, not when this module is imported."""
    return {
        "broker_url": get_settings().redis_url,
        "task_default_queue": "scan",
        "task_acks_late": True,
        # One file at a time per worker: a long scan should not sit on reserved tasks.
        "worker_prefetch_multiplier": 1,
        "task_track_started": True,
        "timezone": "UTC",
        "enable_utc": True,
        # A manual sync overtakes the nightly one; with Redis as the broker this is a
        # preference, not a guarantee.
        "broker_transport_options": {
            "priority_steps": list(range(10)),
            "queue_order_strategy": "priority",
        },
        "beat_schedule": {
            "tick": {"task": "muninn.tick", "schedule": float(TICK_SECONDS)},
            "find-duplicates": {
                "task": "muninn.find_duplicates",
                "schedule": crontab(minute="*/15"),
            },
            "build-smarts": {
                "task": "muninn.build_smarts",
                "schedule": crontab(hour=3, minute=30),
            },
            "prune-change-log": {
                "task": "muninn.prune_change_log",
                "schedule": crontab(hour=4, minute=0),
            },
        },
    }


celery_app.add_defaults(configuration)
celery_app.autodiscover_tasks(["muninn.huginn"], related_name="tasks", force=True)


@worker_shutdown.connect
def _close_connections(**_: object) -> None:
    runtime.shutdown()


@worker_ready.connect
def _recover(sender: Any = None, **_: object) -> None:
    """A starting worker frees what a stopped predecessor on its queues left behind.

    The claims of its stages first: a medium that was being worked on when the worker stopped
    would otherwise count as queued for an hour. The reading worker also frees the read locks
    and reads again what it was on. Each worker only touches its own queues, never the work
    running next door.
    """
    consumer = getattr(sender, "task_consumer", None)
    queues = {queue.name for queue in getattr(consumer, "queues", [])}
    if not queues:
        return

    from muninn.huginn import tasks

    runtime.run(tasks.recover(queues))
    # The main process does no work of its own; its pool processes open their own connections.
    runtime.shutdown()
