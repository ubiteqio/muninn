"""The pipeline as Celery tasks. Each one is idempotent and can be run again at any time."""

import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from redis.asyncio import Redis

from muninn.ai import service as ai_service
from muninn.ai.base import AiError, AiUnreachableError
from muninn.analysis import service as analysis_service
from muninn.analysis import transcripts
from muninn.core.config import get_settings
from muninn.duplicates import service as duplicates_service
from muninn.faces import people
from muninn.faces import service as faces_service
from muninn.huginn import attempts, jobs
from muninn.huginn.app import celery_app
from muninn.huginn.runtime import run, session_scope
from muninn.library import service
from muninn.media import service as media_service
from muninn.memories import service as memories_service
from muninn.models.ai import AiKind
from muninn.models.change_log import SyncTrigger
from muninn.models.notification import NotificationKind
from muninn.models.publication import ScanStatus
from muninn.notify import events
from muninn.notify import service as notify_service
from muninn.places import service as places_service
from muninn.search import service as search_service
from muninn.settings import service as settings_service

logger = logging.getLogger(__name__)

#: How many media the clock hands the AI queue per minute at most. Enough to keep two slots busy
#: for a minute; the rest waits in the database rather than in Redis.
AI_BATCH = 200

#: The hour of the morning the memories of the day are chosen, where the family lives.
MEMORIES_HOUR = 6

#: Lower means more urgent; the same order the dispatcher uses for the API.
PRIORITY = {SyncTrigger.MANUAL: 0, SyncTrigger.AGENT: 2, SyncTrigger.QUICK: 5, SyncTrigger.FULL: 8}


@celery_app.task(name="muninn.tick", queue="scan")
def tick() -> list[str]:
    """Runs every minute and asks the settings what is due.

    The intervals live in the database, so changing them in the admin area takes effect without
    restarting the scheduler.
    """
    return run(_tick())


@celery_app.task(name="muninn.sync_all", queue="scan")
def sync_all(quick: bool = True) -> list[str]:
    """Queue a sync for every published folder that is switched on."""
    return run(_queue_all(quick=quick))


@celery_app.task(name="muninn.sync", queue="scan")
def sync_publication(
    publication_id: str,
    quick: bool = False,
    confirm_deletions: bool = False,
    trigger: str = SyncTrigger.FULL,
    scope_path: str | None = None,
    with_children: bool = True,
    job_id: str | None = None,
) -> dict[str, Any]:
    """Read one published folder, or one album inside it, and queue what it found."""
    return run(
        _sync(
            uuid.UUID(publication_id),
            quick=quick,
            confirm_deletions=confirm_deletions,
            trigger=SyncTrigger(trigger),
            scope_path=scope_path,
            with_children=with_children,
            job_id=job_id,
        )
    )


@celery_app.task(name="muninn.read_metadata", queue="scan", bind=True)
def read_metadata(self: Any, media_id: str) -> bool:
    """Stage 2 for one medium: date, camera, size, duration and coordinates."""
    return run(_read_metadata(uuid.UUID(media_id), task_id=str(self.request.id)))


@celery_app.task(name="muninn.derive", queue="derive", bind=True)
def derive_media(self: Any, media_id: str) -> bool:
    """Stage 3 for one medium: thumbnail, preview, a playable video and the pixel hash."""
    return run(_derive_media(uuid.UUID(media_id), task_id=str(self.request.id)))


@celery_app.task(name="muninn.embed_image", queue="ai", bind=True)
def embed_image(self: Any, media_id: str) -> bool:
    """Stage 4 for one medium: the vector the picture search and the duplicates work with."""
    return run(_embed_image(uuid.UUID(media_id), task_id=str(self.request.id)))


@celery_app.task(name="muninn.transcribe", queue="ai", bind=True)
def transcribe_media(self: Any, media_id: str) -> bool:
    """What is said in one video, with the time of each part."""
    return run(_transcribe_media(uuid.UUID(media_id), task_id=str(self.request.id)))


@celery_app.task(name="muninn.analyze", queue="ai", bind=True)
def analyze_media(self: Any, media_id: str) -> bool:
    """Stage 5 for one medium: caption, tags, scene and text in the picture."""
    return run(_analyze_media(uuid.UUID(media_id), task_id=str(self.request.id)))


@celery_app.task(name="muninn.embed_caption", queue="ai", bind=True)
def embed_caption(self: Any, media_id: str) -> bool:
    """Stage 6 for one medium: the meaning of its caption as a vector."""
    return run(_embed_caption(uuid.UUID(media_id), task_id=str(self.request.id)))


@celery_app.task(name="muninn.place_media", queue="scan")
def place_media() -> int:
    """Name the towns the media were taken in; loads the places first when they are missing."""
    return run(_place_media())


@celery_app.task(name="muninn.fingerprint", queue="derive")
def fingerprint_media() -> int:
    """Fingerprint the next thumbnails, for finding copies. A few milliseconds each."""
    return run(_fingerprint_media())


@celery_app.task(name="muninn.find_duplicates", queue="scan")
def find_duplicates() -> int:
    """Find the groups of copies again; the clock asks for it every quarter of an hour."""
    return run(_find_duplicates())


@celery_app.task(name="muninn.prepare_memories", queue="scan")
def prepare_memories(day: str) -> int:
    """Choose the memories of a day (ISO date), once."""
    return run(_prepare_memories(date.fromisoformat(day)))


@celery_app.task(name="muninn.detect_faces", queue="ai", bind=True)
def detect_faces(self: Any, media_id: str) -> bool:
    """Stage 7: the faces in a medium, and a vector for each."""
    return run(_detect_faces(uuid.UUID(media_id), self.request.id))


@celery_app.task(name="muninn.sort_faces", queue="people")
def sort_faces(face_ids: list[str]) -> None:
    """One face after a "Nein": its person, or a suggestion and the group it belongs to."""
    run(_sort_faces([uuid.UUID(face_id) for face_id in face_ids]))


@celery_app.task(name="muninn.reassess_faces", queue="people")
def reassess_faces() -> int:
    """After a name was given or taken: the faces nobody assigned by hand are asked again."""
    return run(_reassess_faces())


@celery_app.task(name="muninn.regroup_faces", queue="people")
def regroup_faces() -> dict[str, int]:
    """Build the groups of the unnamed faces again, under the rule as it stands now."""
    return run(_regroup_faces())


@celery_app.task(name="muninn.prune_change_log", queue="scan")
def prune_change_log() -> int:
    """Throw away log lines older than the retention period."""
    return run(_prune_change_log())


@celery_app.task(name="muninn.clean_derived", queue="scan")
def clean_derived() -> int:
    """Remove previews that belong to no medium any more."""
    return run(_clean_derived())


async def _tick() -> list[str]:
    # Local time, because "three at night" is the admin's three, not UTC's. The container gets
    # its zone from TZ in deploy/.env.
    now = datetime.now().astimezone()
    async with session_scope() as session:
        settings = await settings_service.get_settings(session)

    redis = jobs.connect()
    started: list[str] = []
    try:
        last_quick = await redis.get(jobs.LAST_QUICK_KEY)
        due = last_quick is None or now - datetime.fromisoformat(last_quick) >= timedelta(
            seconds=settings.quick_sync_seconds
        )
        if due:
            await redis.set(jobs.LAST_QUICK_KEY, now.isoformat())
            started.extend(await _queue_all(quick=True))

        # The full sync runs once on the day it is due, whenever the hour comes around.
        today = now.date().isoformat()
        if now.hour == settings.full_sync_hour and await redis.get(jobs.LAST_FULL_KEY) != today:
            await redis.set(jobs.LAST_FULL_KEY, today)
            started.extend(await _queue_all(quick=False))
            # The sweep goes with the nightly read: by then the day's work is long finished,
            # and what is left over has had hours to prove that nobody wants it.
            clean_derived.delay()

        # The memories of the day are chosen at six, before anybody looks.
        if now.hour >= MEMORIES_HOUR and await redis.get(jobs.LAST_MEMORIES_KEY) != today:
            await redis.set(jobs.LAST_MEMORIES_KEY, today)
            prepare_memories.delay(today)

        started.extend(await _queue_second_looks(settings.stability_seconds, now))
        await _queue_ai_work(redis)
        place_media.delay()
        fingerprint_media.delay()
    finally:
        await redis.aclose()

    return started


async def recover(queues: set[str]) -> list[str]:
    """After a worker started: free what a stopped predecessor on these queues left behind.

    The claims of their stages go, so the media they were on are handed out again. The reading
    worker also frees the read locks and reads again every folder that still says "running":
    it was being read when the worker stopped, and every step of a read can be repeated.
    Returns the folders read again.
    """
    redis = jobs.connect()
    try:
        for queue in queues:
            await jobs.release_claims(redis, jobs.STAGES_OF_QUEUE.get(queue, ()))
        if "scan" not in queues:
            return []
        await jobs.release_all(redis)
    finally:
        await redis.aclose()

    async with session_scope() as session:
        interrupted = [
            publication
            for publication in await service.list_publications(session)
            if publication.last_sync_status is ScanStatus.RUNNING
        ]

    for publication in interrupted:
        sync_publication.apply_async(
            args=[str(publication.id)],
            kwargs={"trigger": SyncTrigger.MANUAL.value},
            priority=PRIORITY[SyncTrigger.MANUAL],
        )
    return [str(publication.id) for publication in interrupted]


async def _queue_second_looks(stability_seconds: int, now: datetime) -> list[str]:
    """Files that were seen once and have settled since get their confirming listing."""
    async with session_scope() as session:
        due = await service.waiting_for_a_second_look(
            session, stability_seconds=stability_seconds, now=now
        )

    for publication in due:
        sync_publication.apply_async(
            args=[str(publication.id)],
            kwargs={"trigger": SyncTrigger.MANUAL.value},
            priority=PRIORITY[SyncTrigger.MANUAL],
        )
    return [str(publication.id) for publication in due]


async def _queue_ai_work(redis: Redis) -> int:
    """Hand the AI queue what still lacks a picture vector, a description or a caption vector.

    The clock does this rather than the stage before, so a model that is switched, or a machine
    that was away for a day, catches up on its own. A stage without a profile in use waits.
    """
    async with session_scope() as session:
        picture = await ai_service.active_profile(session, AiKind.IMAGE_EMBEDDER)
        analyzer = await ai_service.active_profile(session, AiKind.ANALYZER)
        words = await ai_service.active_profile(session, AiKind.TEXT_EMBEDDER)
        listener = await ai_service.active_profile(session, AiKind.TRANSCRIBER)

        without_vector = (
            await search_service.media_without(
                session,
                search_service.VectorKind.IMAGE,
                model=picture.model,
                version=search_service.IMAGE_VECTOR_VERSION,
                limit=AI_BATCH,
            )
            if picture
            else []
        )
        without_transcript = (
            await transcripts.media_without(session, model=listener.model, limit=AI_BATCH)
            if listener
            else []
        )
        without_caption = (
            await analysis_service.media_without(
                session,
                model=analyzer.model,
                limit=AI_BATCH,
                transcriber_model=listener.model if listener else None,
            )
            if analyzer
            else []
        )
        without_caption_vector = (
            await search_service.captions_without(session, model=words.model, limit=AI_BATCH)
            if words
            else []
        )
        faces = await ai_service.active_profile(session, AiKind.FACE_DETECTOR)
        without_faces = (
            await faces_service.media_without(session, limit=AI_BATCH)
            if faces and await faces_service.enabled(session)
            else []
        )

    return (
        await _hand_out(redis, jobs.IMAGE_VECTOR_STAGE, embed_image, without_vector)
        + await _hand_out(redis, jobs.TRANSCRIPTION_STAGE, transcribe_media, without_transcript)
        + await _hand_out(redis, jobs.ANALYSIS_STAGE, analyze_media, without_caption)
        + await _hand_out(redis, jobs.CAPTION_VECTOR_STAGE, embed_caption, without_caption_vector)
        + await _hand_out(redis, jobs.FACES_STAGE, detect_faces, without_faces)
    )


async def _hand_out(redis: Redis, stage: str, task: Any, media_ids: list[uuid.UUID]) -> int:
    """Queue each medium once per stage; what is already queued stays where it is. A stage
    whose machine did not answer a moment ago gets nothing until its pause is over."""
    if media_ids and await redis.exists(jobs.pause_key(stage)):
        return 0
    queued = 0
    for media_id in media_ids:
        if await jobs.claim(redis, stage, media_id):
            task.delay(str(media_id))
            queued += 1
    return queued


async def _queue_all(*, quick: bool) -> list[str]:
    async with session_scope() as session:
        publications = [
            publication
            for publication in await service.list_publications(session)
            if publication.enabled
        ]

    trigger = SyncTrigger.QUICK if quick else SyncTrigger.FULL
    for publication in publications:
        sync_publication.apply_async(
            args=[str(publication.id)],
            kwargs={"quick": quick, "trigger": trigger.value},
            priority=PRIORITY[trigger],
        )
    return [str(publication.id) for publication in publications]


async def _sync(
    publication_id: uuid.UUID,
    *,
    quick: bool,
    confirm_deletions: bool,
    trigger: SyncTrigger,
    scope_path: str | None,
    with_children: bool,
    job_id: str | None,
) -> dict[str, Any]:
    redis = jobs.connect()
    holds_lock = False
    try:
        if not await jobs.acquire(redis, publication_id):
            # Somebody is already reading this folder. Fold this request into that run instead
            # of queueing a second one behind it.
            await jobs.request_again(redis, publication_id)
            if job_id:
                await jobs.write_job(redis, job_id, "coalesced")
            return {"status": "coalesced", "publication_id": str(publication_id)}

        holds_lock = True
        await jobs.mark_active(redis, f"read-{publication_id}", "read")
        await events.publish(redis, "jobs", kind="read_started", publication_id=str(publication_id))
        if job_id:
            await jobs.write_job(redis, job_id, "running")

        async def report_progress(progress: service.SyncProgress) -> None:
            await jobs.write_progress(redis, publication_id, progress)
            await events.publish(
                redis,
                "jobs",
                kind="read_progress",
                publication_id=str(publication_id),
                files_done=progress.files_done,
                files_total=progress.files_total,
                current=progress.current,
            )

        async def stop_requested() -> bool:
            return await jobs.cancel_requested(redis, publication_id)

        report = await _run_sync(
            publication_id,
            quick=quick,
            confirm_deletions=confirm_deletions,
            trigger=trigger,
            scope_path=scope_path,
            with_children=with_children,
            on_progress=report_progress,
            should_stop=stop_requested,
        )

        await jobs.clear_progress(redis, publication_id)
        if job_id:
            await jobs.write_job(redis, job_id, "done", report)
        if _changed_anything(report):
            await events.publish(redis, events.LIBRARY_TOPIC, kind="changed")

        return _as_dict(report)
    finally:
        if holds_lock:
            await jobs.clear_active(redis, f"read-{publication_id}")
            await events.publish(
                redis, "jobs", kind="read_finished", publication_id=str(publication_id)
            )
            # A cancel is for this run only; the next one starts with a clean slate.
            await jobs.clear_cancel(redis, publication_id)
            # Always: a run that ended badly must not lock its folder away for an hour.
            requested_again = await jobs.release(redis, publication_id)
            if requested_again:
                sync_publication.delay(
                    str(publication_id), quick=False, trigger=SyncTrigger.FULL.value
                )
        await redis.aclose()


async def _run_sync(
    publication_id: uuid.UUID,
    *,
    quick: bool,
    confirm_deletions: bool,
    trigger: SyncTrigger,
    scope_path: str | None,
    with_children: bool,
    on_progress: service.ProgressCallback | None = None,
    should_stop: service.StopCheck | None = None,
) -> service.SyncReport:
    environment = get_settings()

    async with session_scope() as session:
        try:
            publication = await service.get_publication(session, publication_id)
        except service.PublicationNotFoundError:
            return service.SyncReport(
                status=ScanStatus.FAILED, message="This folder is no longer published."
            )

        settings = await settings_service.get_settings(session)
        report = await service.sync_publication(
            session,
            publication,
            settings=settings,
            library_base=environment.library_path,
            trigger=trigger,
            quick=quick,
            scope_path=scope_path,
            with_children=with_children,
            confirm_deletions=confirm_deletions,
            on_progress=on_progress,
            should_stop=should_stop,
        )

    redis = jobs.connect()
    try:
        # Only what is not in the queue already: the clock comes around every minute, and the
        # backlog it sees does not shrink while the worker is still chewing on it.
        for media_id in report.pending_metadata:
            if await jobs.claim(redis, "metadata", media_id):
                read_metadata.delay(str(media_id))
        for media_id in report.pending_derivatives:
            if await jobs.claim(redis, "derive", media_id):
                derive_media.delay(str(media_id))
    finally:
        await redis.aclose()

    if report.added_by_album:
        await _tell_about_new_media(report.added_by_album)

    if report.removed_media:
        # The originals are gone for good, so their previews have no reason to stay.
        await media_service.remove_derivatives(environment.derived_path, report.removed_media)

    return report


async def _tell_about_new_media(added: dict[str, int]) -> None:
    """Everybody hears of new pictures - one notification per album, however many arrived."""
    async with session_scope() as session:
        everybody = await notify_service.everybody(session)
        told: list[uuid.UUID] = []
        for album_id, count in added.items():
            told += await notify_service.notify(
                session,
                everybody,
                NotificationKind.NEW_MEDIA,
                notify_service.About(album_id=uuid.UUID(album_id)),
                count=count,
            )
        await session.commit()

    redis = jobs.connect()
    try:
        await events.announce_notifications(redis, list(dict.fromkeys(told)))
    finally:
        await redis.aclose()


async def _read_metadata(media_id: uuid.UUID, task_id: str) -> bool:
    library_base = get_settings().library_path
    async with _announced("metadata", media_id, task_id), session_scope() as session:
        return await service.apply_metadata(session, media_id, library_base=library_base)


async def _derive_media(media_id: uuid.UUID, task_id: str) -> bool:
    environment = get_settings()
    async with _announced("derive", media_id, task_id), session_scope() as session:
        settings = await settings_service.get_settings(session)
        made = await media_service.apply_derivatives(
            session,
            media_id,
            library_base=environment.library_path,
            derived_root=environment.derived_path,
            settings=settings,
        )
    if made:
        # The grid shows a placeholder until now; whoever looks at it may reload.
        await _announce_library_change()
    return made


#: A thousand previews in a row must not make every open page reload a thousand times: the word
#: goes out once, then not again for this long.
ANNOUNCE_EVERY_SECONDS = 10


async def _announce_library_change() -> None:
    """Tell every open app that the albums look different now. No names, no paths: anybody
    signed in may hear this, and the app only takes it as a hint to ask again.

    At most once every ANNOUNCE_EVERY_SECONDS; whoever comes later in that time stays quiet.
    What changed meanwhile is picked up by the next word, or by the page's own next look.
    """
    redis = jobs.connect()
    try:
        if await redis.set("muninn:library:announced", "1", nx=True, ex=ANNOUNCE_EVERY_SECONDS):
            await events.publish(redis, events.LIBRARY_TOPIC, kind="changed")
    finally:
        await redis.aclose()


def _changed_anything(report: service.SyncReport) -> bool:
    return any(
        (
            report.added,
            report.changed,
            report.moved,
            report.missing,
            report.restored,
            report.removed,
        )
    )


async def _embed_image(media_id: uuid.UUID, task_id: str) -> bool:
    if await _resting(jobs.IMAGE_VECTOR_STAGE, media_id):
        return False
    derived_root = get_settings().derived_path
    async with (
        _announced(jobs.IMAGE_VECTOR_STAGE, media_id, task_id) as outcome,
        session_scope() as session,
    ):
        profile = await ai_service.active_profile(session, AiKind.IMAGE_EMBEDDER)
        if profile is None:
            return False
        try:
            return await search_service.apply_image_vector(
                session,
                media_id,
                embedder=ai_service.embedder_for(profile),
                model=profile.model,
                derived_root=derived_root,
            )
        except AiError as error:
            await _pause_if_unreachable(error, outcome)
            # The machine is away or refused. The claim goes with the task, so the clock asks
            # again in a minute; a traceback per medium would say nothing more than this line.
            logger.warning("No picture vector for %s: %s", media_id, error)
            outcome.failed = True
            return False


async def _transcribe_media(media_id: uuid.UUID, task_id: str) -> bool:
    if await _resting(jobs.TRANSCRIPTION_STAGE, media_id):
        return False
    derived_root = get_settings().derived_path
    async with (
        _announced(jobs.TRANSCRIPTION_STAGE, media_id, task_id) as outcome,
        session_scope() as session,
    ):
        profile = await ai_service.active_profile(session, AiKind.TRANSCRIBER)
        if profile is None:
            return False
        try:
            heard = await transcripts.apply_transcription(
                session,
                media_id,
                transcriber=ai_service.transcriber_for(profile),
                model=profile.model,
                derived_root=derived_root,
            )
        except (AiError, transcripts.SoundError) as error:
            if isinstance(error, AiError):
                await _pause_if_unreachable(error, outcome)
            else:
                # Nothing to hear in this one, and that will not change by asking again.
                await attempts.note_failure(session, media_id, jobs.TRANSCRIPTION_STAGE, str(error))
            logger.warning("No transcript for %s: %s", media_id, error)
            outcome.failed = True
            return False

    if heard:
        # The description of the video was waiting for this.
        redis = jobs.connect()
        try:
            await _hand_out(redis, jobs.ANALYSIS_STAGE, analyze_media, [media_id])
        finally:
            await redis.aclose()
    return heard


async def _analyze_media(media_id: uuid.UUID, task_id: str) -> bool:
    if await _resting(jobs.ANALYSIS_STAGE, media_id):
        return False
    derived_root = get_settings().derived_path
    redis = jobs.connect()

    async def still_going() -> None:
        await jobs.keep_alive(redis, task_id, jobs.ANALYSIS_STAGE, media_id)

    try:
        async with (
            _announced(jobs.ANALYSIS_STAGE, media_id, task_id) as outcome,
            session_scope() as session,
        ):
            profile = await ai_service.active_profile(session, AiKind.ANALYZER)
            if profile is None:
                return False
            try:
                described = await analysis_service.apply_analysis(
                    session,
                    media_id,
                    analyzer=ai_service.analyzer_for(profile),
                    model=profile.model,
                    derived_root=derived_root,
                    heartbeat=still_going,
                )
            except AiError as error:
                await _pause_if_unreachable(error, outcome)
                logger.warning("No description for %s: %s", media_id, error)
                outcome.failed = True
                return False
    finally:
        await redis.aclose()

    if described:
        # Stage 6 depends on this one; no reason to wait for the clock.
        redis = jobs.connect()
        try:
            await _hand_out(redis, jobs.CAPTION_VECTOR_STAGE, embed_caption, [media_id])
        finally:
            await redis.aclose()
    return described


async def _embed_caption(media_id: uuid.UUID, task_id: str) -> bool:
    if await _resting(jobs.CAPTION_VECTOR_STAGE, media_id):
        return False
    async with (
        _announced(jobs.CAPTION_VECTOR_STAGE, media_id, task_id) as outcome,
        session_scope() as session,
    ):
        profile = await ai_service.active_profile(session, AiKind.TEXT_EMBEDDER)
        if profile is None:
            return False
        try:
            return await search_service.apply_caption_vector(
                session, media_id, embedder=ai_service.embedder_for(profile), model=profile.model
            )
        except AiError as error:
            await _pause_if_unreachable(error, outcome)
            logger.warning("No caption vector for %s: %s", media_id, error)
            outcome.failed = True
            return False


async def _detect_faces(media_id: uuid.UUID, task_id: str) -> bool:
    if await _resting(jobs.FACES_STAGE, media_id):
        return False
    derived_root = get_settings().derived_path
    async with (
        _announced(jobs.FACES_STAGE, media_id, task_id) as outcome,
        session_scope() as session,
    ):
        profile = await ai_service.active_profile(session, AiKind.FACE_DETECTOR)
        if profile is None:
            return False
        try:
            return await faces_service.apply_faces(
                session,
                media_id,
                detector=ai_service.face_detector_for(profile),
                model=profile.model,
                derived_root=derived_root,
            )
        except AiError as error:
            if isinstance(error, AiUnreachableError):
                # The machine is away. Not this medium's fault, so it keeps its three tries.
                await _pause_if_unreachable(error, outcome)
            else:
                # The machine answered, and the answer was no. Asking again with the same
                # frames gets the same no, so it is counted - otherwise a picture the detector
                # chokes on comes round again every few minutes for ever.
                await attempts.note_failure(session, media_id, jobs.FACES_STAGE, str(error))
            logger.warning("No faces for %s: %s", media_id, error)
            outcome.failed = True
            return False


@dataclass(slots=True)
class Outcome:
    """How a piece of work ended, for the engine room: done, or failed."""

    failed: bool = False
    #: The stage it belongs to, so a machine that is away can pause it.
    stage: str | None = None


@asynccontextmanager
async def _announced(stage: str, media_id: uuid.UUID, task_id: str) -> AsyncIterator[Outcome]:
    """Say what is being worked on, and let go of the medium when it is done.

    Without this the admin area can only see reads: a worker spending an hour on previews looks
    exactly like a worker with nothing to do. The task's own id is part of it, so an admin can
    stop this one piece of work. A task that failed says so through the outcome, and so does
    one that ended in an exception - the engine room must not list either as done.
    """
    redis = jobs.connect()
    outcome = Outcome(stage=stage)
    try:
        await jobs.mark_active(redis, task_id, stage, media_id)
        await events.publish(redis, "jobs", kind="task_started", stage=stage, task_id=task_id)
        yield outcome
    except BaseException:
        outcome.failed = True
        raise
    finally:
        await jobs.clear_active(redis, task_id)
        await jobs.note_finished(redis, task_id, stage, media_id, failed=outcome.failed)
        await jobs.release_claim(redis, stage, media_id)
        # The open admin pages hear this the moment it happens, which is the only way to see
        # work that is over in a tenth of a second.
        await events.publish(
            redis,
            "jobs",
            kind="task_finished",
            stage=stage,
            task_id=task_id,
            media_id=str(media_id),
        )
        await redis.aclose()


async def _resting(stage: str, media_id: uuid.UUID) -> bool:
    """Whether this stage rests because its machine was away.

    The pause stops the clock from handing out more, but up to a batch is queued already. Each
    of those lets go of its medium at once - before pulling sound out of a video or reading a
    preview for a machine that cannot answer. The claim goes, so the medium is handed out again
    after the pause; it is not counted as done or as failed.
    """
    redis = jobs.connect()
    try:
        if not await redis.exists(jobs.pause_key(stage)):
            return False
        await jobs.release_claim(redis, stage, media_id)
        return True
    finally:
        await redis.aclose()


async def _pause_if_unreachable(error: AiError, outcome: "Outcome") -> None:
    """The machine is away: its stages rest for a while instead of failing a thousand media a
    minute - which keeps the workers, the engine room and every open page busy for nothing."""
    if not isinstance(error, AiUnreachableError) or outcome.stage is None:
        return
    redis = jobs.connect()
    try:
        await redis.set(jobs.pause_key(outcome.stage), "1", ex=jobs.AI_PAUSE_SECONDS)
    finally:
        await redis.aclose()


async def _fingerprint_media() -> int:
    async with session_scope() as session:
        return await duplicates_service.fingerprint_media(session, get_settings().derived_path)


async def _find_duplicates() -> int:
    async with session_scope() as session:
        return await duplicates_service.find_groups(session)


async def _prepare_memories(day: date) -> int:
    async with session_scope() as session:
        return await memories_service.prepare(session, day)


async def _sort_faces(face_ids: list[uuid.UUID]) -> None:
    async with session_scope() as session:
        await people.sort_faces(session, face_ids)


async def _regroup_faces() -> dict[str, int]:
    async with session_scope() as session:
        found = await people.regroup(session)
    # A plain answer: Celery carries the result of a task as JSON.
    return {
        "groups": found.groups,
        "faces": found.faces,
        "largest": found.largest,
        "ungrouped": found.ungrouped,
    }


async def _reassess_faces() -> int:
    redis = jobs.connect()
    try:
        await jobs.reassessment_starts(redis)
    finally:
        await redis.aclose()
    async with session_scope() as session:
        changed = await people.reassess(session)
        # A name given today can put somebody on a video they were already on: a duplicate the
        # moment it happens.
        await faces_service.collapse_all_videos(session, get_settings().derived_path)

    if changed:
        # Somebody may be looking at the questions this pass has just answered.
        redis = jobs.connect()
        try:
            await events.publish(redis, events.PEOPLE_TOPIC, kind="reassessed", changed=changed)
        finally:
            await redis.aclose()
    return changed


async def _place_media() -> int:
    async with session_scope() as session:
        loaded = await places_service.load_gazetteer(session, get_settings().places_file)
        if loaded:
            logger.info("Loaded %d places", loaded)
        return await places_service.place_media(session)


async def _clean_derived() -> int:
    environment = get_settings()
    async with session_scope() as session:
        removed = await media_service.remove_orphans(session, environment.derived_path)
    return len(removed)


async def _prune_change_log() -> int:
    async with session_scope() as session:
        return await service.prune_change_log(session)


def _as_dict(report: service.SyncReport) -> dict[str, Any]:
    return {
        "status": report.status,
        "albums": report.albums,
        "added": report.added,
        "changed": report.changed,
        "touched": report.touched,
        "moved": report.moved,
        "missing": report.missing,
        "restored": report.restored,
        "removed": report.removed,
        "waiting": report.waiting,
        "unchanged_folders": report.unchanged_folders,
        "failed_folders": report.failed_folders,
        "queued_metadata": len(report.pending_metadata),
        "queued_derivatives": len(report.pending_derivatives),
        "message": report.message,
    }
