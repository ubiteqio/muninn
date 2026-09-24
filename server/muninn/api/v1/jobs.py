"""What Huginn is working on (/admin/jobs)."""

import uuid
from contextlib import suppress
from datetime import datetime, time, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from kombu.exceptions import OperationalError
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from muninn.ai import health as ai_health
from muninn.ai import service as ai_service
from muninn.analysis import service as analysis_service
from muninn.analysis import transcripts
from muninn.api.schemas.jobs import (
    ActiveTask,
    AiHealthView,
    AiServiceView,
    FinishedTask,
    JobsView,
    PurgedQueue,
    QueueView,
    RunningRead,
    ScheduleView,
    TaskMedia,
    WaitingFile,
    WaitingItem,
    WaitingView,
)
from muninn.api.schemas.library import SyncProgressView
from muninn.core.deps import AdminUser, get_redis, get_session
from muninn.core.problem import ProblemError, problem_type
from muninn.faces import service as faces_service
from muninn.huginn import jobs, outstanding
from muninn.huginn.app import celery_app
from muninn.library import service
from muninn.media import service as media_service
from muninn.models.ai import AiKind
from muninn.search import service as search_service
from muninn.settings import service as settings_service

router = APIRouter(prefix="/admin/jobs", tags=["admin: jobs"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
RedisDep = Annotated[Redis, Depends(get_redis)]

#: Which stages put their media into which queue. Emptying a queue forgets those claims too.
STAGES_OF = jobs.STAGES_OF_QUEUE


@router.get("", summary="What Huginn is working on")
async def read_jobs(admin: AdminUser, session: SessionDep, redis: RedisDep) -> JobsView:
    """Reads, queues and the clock in one answer, so the admin area can show the whole picture."""
    settings = await settings_service.get_settings(session)
    counts = await service.index_counts(session)
    publications = await service.list_publications(session)

    running = []
    for publication in publications:
        if not await jobs.is_running(redis, publication.id):
            continue
        stored = await jobs.read_progress(redis, publication.id)
        running.append(
            RunningRead(
                publication_id=publication.id,
                relative_path=publication.relative_path,
                name=publication.name,
                progress=SyncProgressView.model_validate(stored) if stored else None,
            )
        )

    active = await _active(session, redis)
    finished = await _finished(session, redis)
    lengths = await jobs.queue_lengths(redis)
    waiting_files = sum(
        [
            await service.waiting_files(session, publication.relative_path)
            for publication in publications
        ]
    )

    read_times = [
        publication.last_sync_at
        for publication in publications
        if publication.last_sync_at is not None
    ]

    return JobsView(
        running=running,
        active=active,
        last_read_at=max(read_times) if read_times else None,
        albums=counts.albums,
        media=counts.media,
        queues=[QueueView(name=name, waiting=waiting) for name, waiting in lengths.items()],
        pending_metadata=counts.pending_metadata,
        pending_derivatives=counts.pending_derivatives,
        pending_image_vectors=await _pending_image_vectors(session),
        pending_transcripts=await _pending_transcripts(session),
        pending_analyses=await _pending_analyses(session),
        pending_caption_vectors=await _pending_caption_vectors(session),
        pending_faces=await _pending_faces(session),
        unreadable_files=await service.count_unreadable(session),
        waiting_files=waiting_files,
        finished=finished,
        done_last_minute=await jobs.done_last_minute(redis),
        schedule=await _schedule(
            redis, settings.quick_sync_seconds, settings.full_sync_hour, settings.stability_seconds
        ),
    )


async def _pending_image_vectors(session: AsyncSession) -> int | None:
    """Media still without a vector from the picture model in use - none when there is none."""
    profile = await ai_service.active_profile(session, AiKind.IMAGE_EMBEDDER)
    if profile is None:
        return None
    return await search_service.count_without(
        session,
        search_service.VectorKind.IMAGE,
        model=profile.model,
        version=search_service.IMAGE_VECTOR_VERSION,
    )


async def _pending_transcripts(session: AsyncSession) -> int | None:
    """Videos not yet listened to by the speech model in use."""
    profile = await ai_service.active_profile(session, AiKind.TRANSCRIBER)
    if profile is None:
        return None
    return await transcripts.count_without(session, model=profile.model)


async def _pending_analyses(session: AsyncSession) -> int | None:
    """Media still without a description from the describing model in use."""
    profile = await ai_service.active_profile(session, AiKind.ANALYZER)
    if profile is None:
        return None
    listener = await ai_service.active_profile(session, AiKind.TRANSCRIBER)
    return await analysis_service.count_without(
        session, model=profile.model, transcriber_model=listener.model if listener else None
    )


async def _pending_faces(session: AsyncSession) -> int | None:
    """Media not yet looked at for faces - none when no face model is in use."""
    if await ai_service.active_profile(session, AiKind.FACE_DETECTOR) is None:
        return None
    return await faces_service.count_without(session)


async def _pending_caption_vectors(session: AsyncSession) -> int | None:
    """Descriptions still without a vector from the word model in use."""
    profile = await ai_service.active_profile(session, AiKind.TEXT_EMBEDDER)
    if profile is None:
        return None
    return await search_service.count_captions_without(session, model=profile.model)


async def _active(session: AsyncSession, redis: Redis) -> list[ActiveTask]:
    """What the workers have in their hands, with the names and albums of the files they are on."""
    entries = await jobs.active_tasks(redis)
    labels = await media_service.labels_of(session, _media_ids(entries))

    tasks = []
    for entry in entries:
        label, media = _label_of(entry, labels)
        tasks.append(
            ActiveTask(
                task_id=str(entry.get("task_id", "")),
                stage=str(entry.get("stage", "")),
                started_at=datetime.fromisoformat(str(entry["started_at"])),
                label=label,
                media=media,
            )
        )
    return tasks


async def _finished(session: AsyncSession, redis: Redis) -> list[FinishedTask]:
    """What was over a moment ago, newest first - done or failed - with names and albums."""
    entries = await jobs.recent_finished(redis)
    labels = await media_service.labels_of(session, _media_ids(entries))

    finished = []
    for entry in entries:
        label, media = _label_of(entry, labels)
        finished.append(
            FinishedTask(
                stage=str(entry.get("stage", "")),
                finished_at=datetime.fromisoformat(str(entry["finished_at"])),
                failed=bool(entry.get("failed", False)),
                label=label,
                media=media,
            )
        )
    return finished


def _media_ids(entries: list[dict[str, object]]) -> list[uuid.UUID]:
    return [uuid.UUID(str(entry["media_id"])) for entry in entries if entry.get("media_id")]


def _label_of(
    entry: dict[str, object], labels: dict[uuid.UUID, media_service.MediaLabel]
) -> tuple[str, TaskMedia | None]:
    """The file name of the medium an entry is about, and where it lies - when still known."""
    media_id = uuid.UUID(str(entry["media_id"])) if entry.get("media_id") else None
    found = labels.get(media_id) if media_id else None
    if media_id is None or found is None:
        return "", None
    return found.filename, TaskMedia(
        id=media_id, kind=found.kind, album_id=found.album_id, album_path=found.album_path
    )


async def _schedule(
    redis: Redis, quick_sync_seconds: int, full_sync_hour: int, stability_seconds: int
) -> ScheduleView:
    last_quick = await jobs.last_quick_sync(redis)
    next_quick = last_quick + timedelta(seconds=quick_sync_seconds) if last_quick else None

    # The nightly read is due at that hour in the installation's own time zone: that is the hour
    # the admin picked, and the one their browser will show.
    now = datetime.now().astimezone()
    tonight = datetime.combine(now.date(), time(hour=full_sync_hour), tzinfo=now.tzinfo)
    next_full = tonight if tonight > now else tonight + timedelta(days=1)

    if await redis.get(jobs.LAST_FULL_KEY) == now.date().isoformat():
        next_full = tonight + timedelta(days=1)

    return ScheduleView(
        next_quick_sync_at=next_quick,
        next_full_sync_at=next_full,
        quick_sync_seconds=quick_sync_seconds,
        full_sync_hour=full_sync_hour,
        stability_seconds=stability_seconds,
    )


@router.get("/waiting/{stage}", summary="What is behind one of the numbers")
async def read_waiting(
    stage: str, admin: AdminUser, session: SessionDep, limit: int = outstanding.MOST
) -> WaitingView:
    """Which media a stage has not finished with, and what stopped each of them.

    The number beside a stage says how much is left; this says what. Every stage is asked the
    same question it is asked when work is handed out, so the list cannot drift from the count.

    ``files`` is for the one number that is not about media at all: files seen once and waiting
    for the listing that confirms them. They have no medium yet to name.
    """
    if stage == jobs.UNREADABLE_FILES:
        walked_past = await service.unreadable_files(session, limit=limit)
        return WaitingView(
            stage=stage,
            items=[],
            files=[
                WaitingFile(
                    relative_path=one.relative_path,
                    first_seen_at=one.last_at,
                    reason=one.reason,
                )
                for one in walked_past
            ],
        )

    if stage == jobs.WAITING_FILES:
        rows = await service.files_waiting(session, limit=limit)
        return WaitingView(
            stage=stage,
            items=[],
            files=[
                WaitingFile(
                    relative_path=row.relative_path,
                    first_seen_at=row.first_seen_at,
                    byte_size=row.byte_size or 0,
                )
                for row in rows
            ],
        )

    waiting = await outstanding.media_waiting_for(session, stage, limit=limit)
    labels = await media_service.labels_of(session, [one.media_id for one in waiting])
    return WaitingView(
        stage=stage,
        items=[
            WaitingItem(
                media_id=one.media_id,
                kind=labels[one.media_id].kind.value,
                filename=labels[one.media_id].filename,
                album=labels[one.media_id].album_path,
                album_id=labels[one.media_id].album_id,
                byte_size=labels[one.media_id].byte_size,
                attempts=one.attempts,
                last_at=one.last_at,
                last_error=one.last_error,
            )
            for one in waiting
            if one.media_id in labels
        ],
        files=[],
    )


@router.post("/ai/retry", summary="Ask every AI machine again, now")
async def retry_ai(admin: AdminUser, session: SessionDep, redis: RedisDep) -> AiHealthView:
    """The machine is back and the admin says so: every pause ends and every service is asked.

    One button rather than one per service. A stage is paused only if it happened to have work
    while the machine was away, so which of them carry a pause says more about what there was
    to do than about the machine - and none of that is what somebody who has just switched it
    on again is thinking about.
    """
    await ai_health.resume_all(redis)
    found = await ai_health.services(session, redis)
    return _ai_health_view(found)


@router.get("/ai", summary="Whether each AI service answers")
async def read_ai_health(admin: AdminUser, session: SessionDep, redis: RedisDep) -> AiHealthView:
    """The same small question as "Verbindung testen", for every interface in use at once.

    Answers are kept for half a minute, so an open page asks each machine at most twice a minute.
    """
    return _ai_health_view(await ai_health.services(session, redis))


def _ai_health_view(services: list[ai_health.ServiceHealth]) -> AiHealthView:
    return AiHealthView(
        services=[
            AiServiceView(
                kind=item.kind.value,
                configured=item.profile is not None,
                name=item.profile.name if item.profile else None,
                model=item.profile.model if item.profile else None,
                ok=item.ok,
                detail=item.detail,
                milliseconds=item.milliseconds,
                checked_at=item.checked_at,
                paused_until=item.paused_until,
            )
            for item in services
        ]
    )


@router.delete(
    "/ai/{kind}/pause",
    summary="End an AI stage's pause now",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def resume_ai(kind: AiKind, admin: AdminUser, redis: RedisDep) -> Response:
    """For when the machine is back before the pause is over. The clock hands the stage work
    again at its next round; should the machine still be away, the first task pauses it anew."""
    await ai_health.resume(redis, kind)
    # The next round of the clock, now rather than within the minute. Without a worker the
    # pause is lifted all the same, and the clock comes by on its own.
    with suppress(OperationalError):
        celery_app.send_task("muninn.tick", retry=False)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/reads/{publication_id}", summary="Stop a running read", status_code=status.HTTP_202_ACCEPTED
)
async def stop_read(publication_id: uuid.UUID, admin: AdminUser, redis: RedisDep) -> Response:
    """Asks the read to stop. It stops between folders, so what it already read is kept."""
    await jobs.request_cancel(redis, publication_id)
    return Response(status_code=status.HTTP_202_ACCEPTED)


@router.delete(
    "/active/{task_id}", summary="Stop one piece of work", status_code=status.HTTP_202_ACCEPTED
)
async def stop_task(task_id: str, admin: AdminUser, redis: RedisDep) -> Response:
    """Stops a single task, ffmpeg and all. Whatever it was doing is simply not done."""
    celery_app.control.revoke(task_id, terminate=True, signal="SIGTERM")
    await jobs.clear_active(redis, task_id)
    return Response(status_code=status.HTTP_202_ACCEPTED)


@router.delete("/queues/{name}", summary="Empty a queue")
async def purge_queue(name: str, admin: AdminUser, redis: RedisDep) -> PurgedQueue:
    """Throws away what waits in a queue.

    Nothing is lost for good: a medium without previews is queued again by the next read, and
    the nightly one looks at everything anyway.
    """
    if name not in jobs.QUEUES:
        raise ProblemError(
            status=status.HTTP_404_NOT_FOUND,
            type=problem_type("queue-not-found"),
            title="Queue not found",
            detail=f"Muninn has the queues {', '.join(jobs.QUEUES)}.",
        )

    removed = await jobs.purge_queue(redis, name, stages=STAGES_OF.get(name, ()))
    return PurgedQueue(name=name, removed=removed)
