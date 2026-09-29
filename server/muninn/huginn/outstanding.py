"""What is behind a number in the engine room.

"2 Medien ohne Vorschau" is a true answer to the wrong question. Which two, and what stopped
them, was only ever in a worker's log - and only if something had crashed loudly enough to
print it. This names them: the file, the album it is in, how often the stage has tried, and
what the machine said the last time.

Every stage is asked the same question it is asked when work is handed out, so a list here
cannot drift from the count beside it.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from muninn.ai import service as ai_service
from muninn.analysis import service as analysis_service
from muninn.analysis import transcripts
from muninn.faces import service as faces_service
from muninn.huginn import jobs
from muninn.huginn.derive import DERIVE_VERSION
from muninn.library.metadata import METADATA_VERSION
from muninn.models.ai import AiKind
from muninn.models.attempt import MediaAttempt
from muninn.models.media import Media, MediaStatus
from muninn.search import service as search_service

#: How many items one page of a list names. Long enough to see a pattern, short enough to read.
MOST = 200


@dataclass(frozen=True, slots=True)
class Waiting:
    """One medium a stage has not finished with, and why, as far as anybody knows."""

    media_id: uuid.UUID
    attempts: int
    last_error: str | None
    #: When the stage last tried and failed. Nothing where it has not failed at all.
    last_at: datetime | None


async def media_waiting_for(
    session: AsyncSession, stage: str, *, limit: int = MOST
) -> list[Waiting]:
    """The media behind one of the engine room's numbers, with what went wrong for each.

    An unknown stage has nothing waiting rather than an error: the admin area and the server
    are deployed together, but not always in that order.
    """
    media_ids = await _ids_for(session, stage, limit=limit)
    if not media_ids:
        return []

    rows = await session.execute(
        select(
            MediaAttempt.media_id,
            MediaAttempt.attempts,
            MediaAttempt.last_error,
            MediaAttempt.last_at,
        ).where(MediaAttempt.media_id.in_(media_ids), MediaAttempt.stage == stage)
    )
    tried = {row[0]: (row[1], row[2], row[3]) for row in rows}
    nothing: tuple[int, str | None, datetime | None] = (0, None, None)
    return [
        Waiting(
            media_id=media_id,
            attempts=tried.get(media_id, nothing)[0],
            last_error=tried.get(media_id, nothing)[1],
            last_at=tried.get(media_id, nothing)[2],
        )
        for media_id in media_ids
    ]


async def _ids_for(session: AsyncSession, stage: str, *, limit: int) -> list[uuid.UUID]:
    """The same question each stage asks when work is handed out."""
    if stage == "metadata":
        return await _behind_version(session, Media.metadata_version, METADATA_VERSION, limit)
    if stage == "derive":
        return await _behind_version(session, Media.derive_version, DERIVE_VERSION, limit)
    if stage == jobs.IMAGE_VECTOR_STAGE:
        profile = await ai_service.active_profile(session, AiKind.IMAGE_EMBEDDER)
        if profile is None:
            return []
        return await search_service.media_without(
            session,
            search_service.VectorKind.IMAGE,
            model=profile.model,
            version=search_service.IMAGE_VECTOR_VERSION,
            limit=limit,
        )
    if stage == jobs.TRANSCRIPTION_STAGE:
        profile = await ai_service.active_profile(session, AiKind.TRANSCRIBER)
        if profile is None:
            return []
        return await transcripts.media_without(session, model=profile.model, limit=limit)
    if stage == jobs.ANALYSIS_STAGE:
        analyzer = await ai_service.active_profile(session, AiKind.ANALYZER)
        if analyzer is None:
            return []
        listener = await ai_service.active_profile(session, AiKind.TRANSCRIBER)
        return await analysis_service.media_without(
            session,
            model=analyzer.model,
            limit=limit,
            transcriber_model=listener.model if listener else None,
        )
    if stage == jobs.CAPTION_VECTOR_STAGE:
        profile = await ai_service.active_profile(session, AiKind.TEXT_EMBEDDER)
        if profile is None:
            return []
        return await search_service.captions_without(session, model=profile.model, limit=limit)
    if stage == jobs.FACES_STAGE:
        profile = await ai_service.active_profile(session, AiKind.FACE_DETECTOR)
        if profile is None or not await faces_service.enabled(session):
            return []
        return await faces_service.media_without(session, limit=limit)
    return []


async def _behind_version(
    session: AsyncSession, column: InstrumentedAttribute[int], version: int, limit: int
) -> list[uuid.UUID]:
    """Media a stage has not caught up with: raising a version puts every medium behind it."""
    rows = await session.scalars(
        select(Media.id)
        .where(Media.status == MediaStatus.ACTIVE, column < version)
        .order_by(Media.created_at)
        .limit(limit)
    )
    return list(rows)
