"""One read per folder at a time, what a caller may ask about it, and how to stop it.

Two requests for the same folder are not queued behind each other; the second one is folded into
the first. Whoever holds the lock re-runs once at the end if something arrived meanwhile, so
nothing is lost and nothing piles up.
"""

import json
import uuid
from collections.abc import Awaitable, Sequence
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from typing import Any, cast

from redis.asyncio import Redis

from muninn.core.config import get_settings
from muninn.core.redis import create_redis

#: A sync that has not finished within this is assumed dead, and the lock is free again.
LOCK_TTL_SECONDS = 3600
#: How long the result of a job can be asked for.
JOB_TTL_SECONDS = 3600
#: Progress is only interesting while it moves; a stale line disappears by itself.
PROGRESS_TTL_SECONDS = 600

#: What the clock has already done. The API reads these to say when the next read is due.
LAST_QUICK_KEY = "muninn:last-quick-sync"
LAST_FULL_KEY = "muninn:last-full-sync-day"
#: The day whose memories were last chosen, so the clock does it once.
LAST_MEMORIES_KEY = "muninn:memories:last"


def lock_key(root_id: uuid.UUID) -> str:
    return f"muninn:sync-lock:{root_id}"


def again_key(root_id: uuid.UUID) -> str:
    return f"muninn:sync-again:{root_id}"


def job_key(job_id: str) -> str:
    return f"muninn:sync-job:{job_id}"


def progress_key(publication_id: uuid.UUID) -> str:
    return f"muninn:sync-progress:{publication_id}"


def connect() -> Redis:
    return create_redis(get_settings().redis_url)


async def acquire(redis: Redis, root_id: uuid.UUID) -> bool:
    """True when this caller may sync the root now."""
    acquired = await redis.set(lock_key(root_id), "1", nx=True, ex=LOCK_TTL_SECONDS)
    return bool(acquired)


async def release_all(redis: Redis) -> int:
    """Free every read lock. Only for a reading worker that has just started.

    A read holds its lock for up to an hour. When the worker running it is stopped - a deploy,
    a restart of Docker - the lock outlives it, and every later request for that folder is
    folded into a read that no longer exists. There is one reading worker, so when it starts,
    nothing can be reading.
    """
    released = 0
    for pattern in ("muninn:sync-lock:*", "muninn:sync-again:*", "muninn:sync-progress:*"):
        async for key in redis.scan_iter(match=pattern, count=100):
            released += int(await redis.delete(key))
    return released


async def release_claims(redis: Redis, stages: Sequence[str]) -> int:
    """Forget that media of these stages are queued; the clock hands them out again."""
    released = 0
    for stage in stages:
        async for key in redis.scan_iter(match=f"muninn:queued:{stage}:*", count=500):
            released += int(await redis.delete(key))
    return released


async def request_again(redis: Redis, root_id: uuid.UUID) -> None:
    """Remember that somebody asked while a sync was running."""
    await redis.set(again_key(root_id), "1", ex=LOCK_TTL_SECONDS)


async def release(redis: Redis, root_id: uuid.UUID) -> bool:
    """Free the lock. Returns True when a request arrived while the sync was running."""
    await redis.delete(lock_key(root_id))
    return bool(await redis.delete(again_key(root_id)))


async def write_job(redis: Redis, job_id: str, state: str, result: Any = None) -> None:
    """Store what a job is doing, so the caller can ask before the WebSocket exists."""
    payload = {
        "job_id": job_id,
        "state": state,
        "updated_at": datetime.now(UTC).isoformat(),
        "result": _plain(result),
    }
    await redis.set(job_key(job_id), json.dumps(payload), ex=JOB_TTL_SECONDS)


async def read_job(redis: Redis, job_id: str) -> dict[str, Any] | None:
    raw = await redis.get(job_key(job_id))
    if raw is None:
        return None
    parsed: dict[str, Any] = json.loads(raw)
    return parsed


def _plain(value: Any) -> Any:
    """Reports are dataclasses; Redis wants plain data."""
    if value is None:
        return None
    if is_dataclass(value) and not isinstance(value, type):
        return {key: _plain(item) for key, item in asdict(value).items()}
    if isinstance(value, list):
        return [_plain(item) for item in value]
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


async def write_progress(redis: Redis, publication_id: uuid.UUID, progress: Any) -> None:
    """Where a running sync stands, for whoever is watching the admin area."""
    await redis.set(
        progress_key(publication_id), json.dumps(_plain(progress)), ex=PROGRESS_TTL_SECONDS
    )


async def clear_progress(redis: Redis, publication_id: uuid.UUID) -> None:
    await redis.delete(progress_key(publication_id))


async def read_progress(redis: Redis, publication_id: uuid.UUID) -> dict[str, Any] | None:
    raw = await redis.get(progress_key(publication_id))
    if raw is None:
        return None
    parsed: dict[str, Any] = json.loads(raw)
    return parsed


async def last_quick_sync(redis: Redis) -> datetime | None:
    """When the clock last started a quick read of everything."""
    raw = await redis.get(LAST_QUICK_KEY)
    if raw is None:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


#: The queues a worker serves. Their length is what "how much is left" means.
QUEUES = ("scan", "derive", "ai", "people")


async def queue_lengths(redis: Redis) -> dict[str, int]:
    """How many tasks wait in each queue.

    Celery keeps a plain list per queue in Redis, so this is one cheap question per queue - no
    broadcast to the workers, which would cost a round trip and a timeout when none answers.
    """
    lengths: dict[str, int] = {}
    for queue in QUEUES:
        # llen is typed as "answer or awaitable answer" for the sync and async clients alike.
        waiting = cast("Awaitable[int]", redis.llen(queue))
        lengths[queue] = int(await waiting)
    return lengths


async def is_running(redis: Redis, publication_id: uuid.UUID) -> bool:
    """Whether a read of this folder holds the lock right now."""
    found: Any = await redis.exists(lock_key(publication_id))
    return int(found) == 1


#: How long a medium counts as queued. Long enough that a busy queue is not filled twice, short
#: enough that work lost to a crash comes back on its own.
CLAIM_TTL_SECONDS = 3600


def claim_key(stage: str, media_id: uuid.UUID) -> str:
    return f"muninn:queued:{stage}:{media_id}"


async def claim(redis: Redis, stage: str, media_id: uuid.UUID) -> bool:
    """True when this medium is not in the queue for that stage yet.

    Without it a sync every minute re-queues the whole backlog every minute: 500 media waiting
    for previews turn into thousands of tasks that all do the same nothing.
    """
    taken = await redis.set(claim_key(stage, media_id), "1", nx=True, ex=CLAIM_TTL_SECONDS)
    return bool(taken)


async def release_claim(redis: Redis, stage: str, media_id: uuid.UUID) -> None:
    await redis.delete(claim_key(stage, media_id))


#: Set while a reassessment waits for its worker. One pass walks every face nobody assigned by
#: hand, which takes minutes on a grown library, and a name given is not worth a pass of its own
#: when one is already on its way.
REASSESS_KEY = "muninn:faces:reassess-queued"


async def reassessment_queued(redis: Redis) -> bool:
    """True for the caller that queues the pass, false while one is already waiting."""
    taken = await redis.set(REASSESS_KEY, "1", nx=True, ex=CLAIM_TTL_SECONDS)
    return bool(taken)


async def reassessment_starts(redis: Redis) -> None:
    """The pass has begun. A name given from now on queues the next one: this pass may have
    walked past those faces already."""
    await redis.delete(REASSESS_KEY)


#: Stage 4, the picture vector. Its queue is "ai", which runs on a worker of its own.
IMAGE_VECTOR_STAGE = "image_vector"
#: Stage 5, the description, and stage 6, the vector of it. Both on "ai" as well.
ANALYSIS_STAGE = "analysis"
CAPTION_VECTOR_STAGE = "caption_vector"
#: What is said in a video. Before stage 5 for videos, so the summary knows it.
TRANSCRIPTION_STAGE = "transcription"
#: Stage 7, the faces. On "ai" too: the face model runs on the same machine.
FACES_STAGE = "faces"
AI_STAGES = (
    IMAGE_VECTOR_STAGE,
    TRANSCRIPTION_STAGE,
    ANALYSIS_STAGE,
    CAPTION_VECTOR_STAGE,
    FACES_STAGE,
)

#: The stages that work on one medium at a time: what a medium carries into the queues.
MEDIA_STAGES = ("metadata", "derive", *AI_STAGES)

#: Not a stage: the files seen once and waiting to be confirmed. They have no medium yet, so a
#: list of them names paths rather than media.
WAITING_FILES = "files"

#: Nor a stage: the files the reading could not open at all.
UNREADABLE_FILES = "unreadable"

#: How long the clock hands a stage no work after its machine did not answer at all.
AI_PAUSE_SECONDS = 300


def pause_key(stage: str) -> str:
    """Set while a stage rests because its machine was away; the engine room reads it too."""
    return f"muninn:ai:paused:{stage}"


#: Which stages put their media into which queue.
STAGES_OF_QUEUE: dict[str, tuple[str, ...]] = {
    "scan": ("metadata",),
    "derive": ("derive",),
    "ai": AI_STAGES,
}


async def forget_media(redis: Redis, media_ids: Sequence[uuid.UUID]) -> list[str]:
    """Forget what is planned for these media and name the tasks that are on them right now.

    Called when the media themselves go. Returns the task ids so the caller can stop them; a
    task that is only waiting in the queue finds nothing and is done in a moment.
    """
    if not media_ids:
        return []

    wanted = {str(media_id) for media_id in media_ids}
    for media_id in media_ids:
        for stage in MEDIA_STAGES:
            await release_claim(redis, stage, media_id)

    return [
        str(entry["task_id"])
        for entry in await active_tasks(redis)
        if entry.get("media_id") in wanted and entry.get("task_id")
    ]


#: Work too quick to catch in the act - metadata takes about 80 ms, a preview about 110 - would
#: leave the admin area empty while thousands of media go through it. So every finished piece is
#: remembered for a moment: the last few by name, and how many went through per stage.
FINISHED_KEY = "muninn:finished"
FINISHED_KEEP = 10
FINISHED_TTL_SECONDS = 600

#: The window the admin area reports, and how long a count is kept before it falls out.
DONE_WINDOW_SECONDS = 60
DONE_TTL_SECONDS = 300


def done_key(stage: str) -> str:
    return f"muninn:done:{stage}"


async def note_finished(
    redis: Redis,
    task_id: str,
    stage: str,
    media_id: uuid.UUID | None = None,
    *,
    failed: bool = False,
) -> None:
    """Remember that this piece of work is over - done, or failed.

    Only what was done counts towards the minute's throughput; a failure is listed so an admin
    sees it, not counted as progress.
    """
    now = datetime.now(UTC)
    entry = {
        "stage": stage,
        "media_id": str(media_id) if media_id else None,
        "finished_at": now.isoformat(),
        "failed": failed,
    }
    await cast("Awaitable[int]", redis.lpush(FINISHED_KEY, json.dumps(entry)))
    await cast("Awaitable[Any]", redis.ltrim(FINISHED_KEY, 0, FINISHED_KEEP - 1))
    await cast("Awaitable[bool]", redis.expire(FINISHED_KEY, FINISHED_TTL_SECONDS))
    if failed:
        return

    # One sorted set per stage, scored by the second it happened: counting a window is then a
    # single range query, and what has fallen out of it is dropped on the next write.
    key = done_key(stage)
    await cast("Awaitable[int]", redis.zadd(key, {task_id: now.timestamp()}))
    await cast(
        "Awaitable[int]",
        redis.zremrangebyscore(key, 0, now.timestamp() - DONE_TTL_SECONDS),
    )
    await cast("Awaitable[bool]", redis.expire(key, DONE_TTL_SECONDS))


async def recent_finished(redis: Redis) -> list[dict[str, Any]]:
    """The last pieces of work that were finished, newest first."""
    raws = await cast("Awaitable[list[str]]", redis.lrange(FINISHED_KEY, 0, FINISHED_KEEP - 1))
    return [json.loads(raw) for raw in raws]


async def done_last_minute(redis: Redis) -> dict[str, int]:
    """How many media each stage finished in the last minute."""
    since = datetime.now(UTC).timestamp() - DONE_WINDOW_SECONDS
    counts: dict[str, int] = {}
    for stage in MEDIA_STAGES:
        counts[stage] = int(
            await cast("Awaitable[int]", redis.zcount(done_key(stage), since, "+inf"))
        )
    return counts


#: A task that has not reported back within this is assumed dead; its line disappears by itself.
ACTIVE_TTL_SECONDS = 600
_ACTIVE_PREFIX = "muninn:active"


async def mark_active(
    redis: Redis, task_id: str, stage: str, media_id: uuid.UUID | None = None
) -> None:
    """Say that this task is being worked on right now.

    Celery could be asked instead, but that is a broadcast to every worker with a timeout when
    none answers. A key with a lifetime costs one round trip and disappears on its own if the
    worker dies mid-task.
    """
    entry = {
        "task_id": task_id,
        "stage": stage,
        "media_id": str(media_id) if media_id else None,
        "started_at": datetime.now(UTC).isoformat(),
    }
    await redis.set(f"{_ACTIVE_PREFIX}:{task_id}", json.dumps(entry), ex=ACTIVE_TTL_SECONDS)


async def keep_alive(redis: Redis, task_id: str, stage: str, media_id: uuid.UUID) -> None:
    """Tell the queue and the engine room that a long piece of work is still going.

    A video can keep the describing model busy for an hour. Without this its claim would run
    out and the clock would hand the same video out a second time, and the engine room would
    forget that anybody is working on it.
    """
    await cast("Awaitable[bool]", redis.expire(claim_key(stage, media_id), CLAIM_TTL_SECONDS))
    await cast("Awaitable[bool]", redis.expire(f"{_ACTIVE_PREFIX}:{task_id}", ACTIVE_TTL_SECONDS))


async def clear_active(redis: Redis, task_id: str) -> None:
    await redis.delete(f"{_ACTIVE_PREFIX}:{task_id}")


async def active_tasks(redis: Redis) -> list[dict[str, Any]]:
    """What the workers are doing this very moment, newest last."""
    entries: list[dict[str, Any]] = []
    async for key in redis.scan_iter(match=f"{_ACTIVE_PREFIX}:*", count=100):
        raw = await redis.get(key)
        if raw is None:
            continue
        entry: dict[str, Any] = json.loads(raw)
        entries.append(entry)

    return sorted(entries, key=lambda item: str(item.get("started_at", "")))


#: A cancel that nobody picked up disappears by itself; a read checks for it between folders.
CANCEL_TTL_SECONDS = 600


def cancel_key(publication_id: uuid.UUID) -> str:
    return f"muninn:cancel:{publication_id}"


async def request_cancel(redis: Redis, publication_id: uuid.UUID) -> None:
    """Ask a running read to stop. It stops between folders, so nothing is left half written."""
    await redis.set(cancel_key(publication_id), "1", ex=CANCEL_TTL_SECONDS)


async def cancel_requested(redis: Redis, publication_id: uuid.UUID) -> bool:
    found: Any = await redis.exists(cancel_key(publication_id))
    return int(found) == 1


async def clear_cancel(redis: Redis, publication_id: uuid.UUID) -> None:
    await redis.delete(cancel_key(publication_id))


async def purge_queue(redis: Redis, queue: str, stages: Sequence[str] = ()) -> int:
    """Throw away what waits in a queue, and forget that those media were queued.

    Without dropping the claims as well, the media would count as queued for an hour and nothing
    would put them back in - the work would simply disappear.
    """
    waiting = cast("Awaitable[int]", redis.llen(queue))
    length = int(await waiting)
    await redis.delete(queue)

    for stage in stages:
        async for key in redis.scan_iter(match=f"muninn:queued:{stage}:*", count=500):
            await redis.delete(key)

    return int(length)
