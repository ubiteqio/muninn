"""Handing work to the worker.

The API never reads the NAS itself: it puts a task into Redis and answers straight away. If the
worker or Redis is not there, the caller learns that instead of waiting.
"""

import uuid

from kombu.exceptions import OperationalError

from muninn.huginn.tasks import reassess_faces, sort_faces, sync_publication
from muninn.models.change_log import SyncTrigger

#: Lower means more urgent. Somebody waiting in front of an album comes before the nightly run.
PRIORITY = {
    SyncTrigger.MANUAL: 0,
    SyncTrigger.AGENT: 2,
    SyncTrigger.QUICK: 5,
    SyncTrigger.FULL: 8,
}


class WorkerUnreachableError(Exception):
    """Redis did not take the task."""


def queue_sync(
    publication_id: uuid.UUID,
    *,
    quick: bool = False,
    confirm_deletions: bool = False,
    trigger: SyncTrigger = SyncTrigger.MANUAL,
    scope_path: str | None = None,
    with_children: bool = True,
    job_id: str | None = None,
) -> str:
    """Queue one sync and return the id of the task that will run it."""
    try:
        result = sync_publication.apply_async(
            args=[str(publication_id)],
            kwargs={
                "quick": quick,
                "confirm_deletions": confirm_deletions,
                "trigger": trigger.value,
                "scope_path": scope_path,
                "with_children": with_children,
                "job_id": job_id,
            },
            priority=PRIORITY[trigger],
            retry=False,
        )
    except OperationalError as error:
        raise WorkerUnreachableError from error

    return str(result.id)


def queue_face_sorting(face_id: uuid.UUID) -> None:
    """A face said "no" to its person: where it belongs now is found in the background.

    Best effort: when Redis is away, the next reassessment picks the face up.
    """
    try:
        sort_faces.apply_async(args=[[str(face_id)]], retry=False)
    except OperationalError:
        return


def queue_face_reassessment() -> None:
    """A name was given or taken: the unnamed faces are looked at again, in the background.

    Best effort: when Redis is away, the next name given does it.
    """
    try:
        reassess_faces.apply_async(retry=False)
    except OperationalError:
        return
