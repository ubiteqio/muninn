"""Handing work to the worker.

The API never reads the NAS itself: it puts a task into Redis and answers straight away. If the
worker or Redis is not there, the caller learns that instead of waiting.
"""

import uuid
from typing import Any

from kombu.exceptions import OperationalError
from redis.exceptions import RedisError

from muninn.huginn import jobs
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


#: Which task does which stage, for the one an admin asks for by hand.
def _task_of(stage: str) -> Any:
    from muninn.huginn import tasks

    return {
        "metadata": tasks.read_metadata,
        "derive": tasks.derive_media,
        jobs.IMAGE_VECTOR_STAGE: tasks.embed_image,
        jobs.TRANSCRIPTION_STAGE: tasks.transcribe_media,
        jobs.ANALYSIS_STAGE: tasks.analyze_media,
        jobs.CAPTION_VECTOR_STAGE: tasks.embed_caption,
        jobs.FACES_STAGE: tasks.detect_faces,
    }[stage]


def queue_stage(media_id: uuid.UUID, stage: str) -> None:
    """One step for one medium, now: an admin asked for it in front of the picture.

    Best effort, like the other handovers: when Redis is away the clock picks the medium up at
    its next turn anyway, because asking dropped what the step had written.
    """
    try:
        _task_of(stage).apply_async(args=[str(media_id)], priority=0, retry=False)
    except OperationalError:
        return


def queue_face_sorting(face_id: uuid.UUID) -> None:
    """A face said "no" to its person: where it belongs now is found in the background.

    Best effort: when Redis is away, the next reassessment picks the face up.
    """
    try:
        sort_faces.apply_async(args=[[str(face_id)]], retry=False)
    except OperationalError:
        return


async def queue_face_reassessment() -> None:
    """A name was given or taken: the unnamed faces are looked at again, in the background.

    One pass at a time. A pass walks every face nobody assigned by hand and takes minutes on a
    grown library; answering a screen full of suggestions would otherwise queue one for every
    click and hold a worker for an hour. The flag is dropped when the pass starts, so a name
    given while one runs still gets a pass of its own afterwards.

    Best effort: when Redis is away, the next name given does it.
    """
    redis = jobs.connect()
    try:
        if not await jobs.reassessment_queued(redis):
            return
        try:
            reassess_faces.apply_async(retry=False)
        except OperationalError:
            # Nothing was queued after all; the next name given must be free to try again.
            await jobs.reassessment_starts(redis)
    except RedisError:
        return
    finally:
        await redis.aclose()
