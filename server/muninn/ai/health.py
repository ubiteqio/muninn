"""Whether each AI service answers right now, for the engine room.

Every interface in use is asked the same small question as "Verbindung testen", with a short
timeout and all of them at once. The answer is kept for half a minute in Redis: however many
admin pages are open, a machine is asked at most twice a minute, and only while somebody looks.

A stage the worker has paused because its machine was away counts as well. A kept "it answers"
is not trusted while that pause lasts - the worker saw it fail after the answer was kept.
"""

import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from muninn.ai import service
from muninn.ai.base import Check
from muninn.huginn import jobs
from muninn.models.ai import AiKind, AiProfile

#: How long one answer is kept.
KEEP_SECONDS = 30
#: How long a machine gets to answer. Enough for the describing model's short reply.
CHECK_TIMEOUT_SECONDS = 10

#: The stage of the pipeline each interface works for, and so the pause that applies to it.
STAGE_OF: dict[AiKind, str] = {
    AiKind.ANALYZER: jobs.ANALYSIS_STAGE,
    AiKind.IMAGE_EMBEDDER: jobs.IMAGE_VECTOR_STAGE,
    AiKind.TEXT_EMBEDDER: jobs.CAPTION_VECTOR_STAGE,
    AiKind.TRANSCRIBER: jobs.TRANSCRIPTION_STAGE,
    AiKind.FACE_DETECTOR: jobs.FACES_STAGE,
}


@dataclass(frozen=True, slots=True)
class ServiceHealth:
    kind: AiKind
    #: The profile in use, or nothing when this interface has none.
    profile: AiProfile | None
    ok: bool | None = None
    detail: str | None = None
    milliseconds: int | None = None
    checked_at: datetime | None = None
    #: While the worker rests this stage because its machine did not answer.
    paused_until: datetime | None = None


def _key(kind: AiKind) -> str:
    return f"muninn:ai:health:{kind.value}"


async def _kept(redis: Redis, profile: AiProfile) -> dict[str, object] | None:
    raw = await redis.get(_key(profile.kind))
    if raw is None:
        return None
    kept: dict[str, object] = json.loads(raw)
    # Another profile was switched on since: its answer says nothing about this one.
    return kept if kept.get("profile_id") == str(profile.id) else None


async def _ask(redis: Redis, profile: AiProfile, now: datetime) -> dict[str, object]:
    check: Check = await service.check_profile(profile, timeout_seconds=CHECK_TIMEOUT_SECONDS)
    answer: dict[str, object] = {
        "profile_id": str(profile.id),
        "ok": check.ok,
        "detail": check.detail,
        "milliseconds": check.milliseconds,
        "checked_at": now.isoformat(),
    }
    await redis.set(_key(profile.kind), json.dumps(answer), ex=KEEP_SECONDS)
    return answer


async def resume(redis: Redis, kind: AiKind) -> None:
    """An admin knows the machine is back: the stage's pause ends now, and the kept answer goes,
    so the next look asks the machine afresh instead of repeating that it was away."""
    await redis.delete(jobs.pause_key(STAGE_OF[kind]), _key(kind))


async def services(session: AsyncSession, redis: Redis) -> list[ServiceHealth]:
    """Every interface in the order of the admin area, with what its machine last answered."""
    now = datetime.now(UTC)
    profiles = {kind: await service.active_profile(session, kind) for kind in AiKind}

    paused: dict[AiKind, datetime | None] = {}
    for kind in AiKind:
        left = await redis.ttl(jobs.pause_key(STAGE_OF[kind]))
        paused[kind] = now + timedelta(seconds=left) if left > 0 else None

    answers: dict[AiKind, dict[str, object]] = {}
    to_ask: list[AiProfile] = []
    for kind, profile in profiles.items():
        if profile is None:
            continue
        kept = await _kept(redis, profile)
        if kept is not None and not (kept["ok"] and paused[kind]):
            answers[kind] = kept
        else:
            to_ask.append(profile)

    asked = await asyncio.gather(*(_ask(redis, profile, now) for profile in to_ask))
    answers.update({profile.kind: answer for profile, answer in zip(to_ask, asked, strict=True)})

    health = []
    for kind, profile in profiles.items():
        answer = answers.get(kind)
        if profile is None or answer is None:
            health.append(ServiceHealth(kind=kind, profile=None))
            continue
        health.append(
            ServiceHealth(
                kind=kind,
                profile=profile,
                ok=bool(answer["ok"]),
                detail=str(answer["detail"]),
                milliseconds=int(str(answer["milliseconds"])),
                checked_at=datetime.fromisoformat(str(answer["checked_at"])),
                paused_until=paused[kind],
            )
        )
    return health
