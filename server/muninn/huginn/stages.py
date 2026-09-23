"""What the pipeline has done to one medium, and doing one step of it again on demand.

The engine room says what is outstanding across the library; this says it for a single medium,
and lets an admin ask for one step again - a preview that failed the first time, a description
after a better model was set up, the faces of a video that was still being copied when the
worker first looked at it.

Asking for a step forgets the failed attempts as well: somebody who asks has usually just
changed something, and three old failures should not stand in the way.
"""

from dataclasses import dataclass
from typing import Literal

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from muninn.ai import service as ai_service
from muninn.analysis.service import ANALYSIS_VERSION
from muninn.analysis.transcripts import TRANSCRIPT_VERSION
from muninn.faces.service import FACE_VERSION
from muninn.huginn import attempts, jobs
from muninn.huginn.derive import DERIVE_VERSION
from muninn.library.metadata import METADATA_VERSION
from muninn.models.ai import AiKind
from muninn.models.analysis import MediaAnalysis, MediaTranscript
from muninn.models.media import Media, MediaKind
from muninn.search import service as search_service
from muninn.search.service import VectorKind

#: What the admin can ask for, in the order the pipeline itself works.
ORDER = (
    "metadata",
    "derive",
    jobs.IMAGE_VECTOR_STAGE,
    jobs.TRANSCRIPTION_STAGE,
    jobs.ANALYSIS_STAGE,
    jobs.CAPTION_VECTOR_STAGE,
    jobs.FACES_STAGE,
)

State = Literal["done", "open", "given-up", "not-for-this"]


@dataclass(frozen=True)
class StageState:
    """One step of the pipeline as it stands for one medium."""

    stage: str
    state: State
    attempts: int = 0
    last_error: str | None = None


class UnknownStageError(ValueError):
    """A stage nobody can run."""


async def of_medium(session: AsyncSession, media: Media) -> list[StageState]:
    """Every step, and where this medium stands in it."""
    failures = await attempts.of_media(session, media.id)
    done = await _done(session, media)

    states: list[StageState] = []
    for stage in ORDER:
        failure = failures.get(stage)
        if not _fits(stage, media):
            states.append(StageState(stage=stage, state="not-for-this"))
        elif done[stage]:
            states.append(StageState(stage=stage, state="done"))
        elif failure is not None and failure.attempts >= attempts.GIVE_UP_AFTER:
            states.append(
                StageState(
                    stage=stage,
                    state="given-up",
                    attempts=failure.attempts,
                    last_error=failure.last_error,
                )
            )
        else:
            states.append(
                StageState(
                    stage=stage,
                    state="open",
                    attempts=failure.attempts if failure else 0,
                    last_error=failure.last_error if failure else None,
                )
            )
    return states


async def run(session: AsyncSession, media: Media, stage: str) -> None:
    """Ask for one step again: what it wrote is dropped, its failures are forgotten, and the
    worker gets it now rather than at the next turn of the clock."""
    if stage not in ORDER:
        raise UnknownStageError(stage)

    await _undo(session, media, stage)
    await attempts.forget(session, media.id, stage)
    await session.commit()

    from muninn.huginn import dispatch

    dispatch.queue_stage(media.id, stage)


def _fits(stage: str, media: Media) -> bool:
    """Whether this step has anything to do with this medium at all."""
    if stage == jobs.TRANSCRIPTION_STAGE:
        return media.kind is MediaKind.VIDEO
    return True


async def _done(session: AsyncSession, media: Media) -> dict[str, bool]:
    """Which steps have an answer for this medium. A step whose model is not set up counts as
    outstanding: it is waiting for the machine, not for the medium."""
    analyzer = await ai_service.active_profile(session, AiKind.ANALYZER)
    listener = await ai_service.active_profile(session, AiKind.TRANSCRIBER)

    described = (
        await session.scalar(
            select(func.count())
            .select_from(MediaAnalysis)
            .where(
                MediaAnalysis.media_id == media.id,
                MediaAnalysis.version >= ANALYSIS_VERSION,
                *([MediaAnalysis.model == analyzer.model] if analyzer else []),
            )
        )
        or 0
    )
    heard = (
        await session.scalar(
            select(func.count())
            .select_from(MediaTranscript)
            .where(
                MediaTranscript.media_id == media.id,
                MediaTranscript.version >= TRANSCRIPT_VERSION,
                *([MediaTranscript.model == listener.model] if listener else []),
            )
        )
        or 0
    )

    return {
        "metadata": media.metadata_version >= METADATA_VERSION,
        "derive": media.derive_version >= DERIVE_VERSION,
        jobs.IMAGE_VECTOR_STAGE: await search_service.has_vector(
            session, VectorKind.IMAGE, media.id
        ),
        jobs.TRANSCRIPTION_STAGE: heard > 0,
        jobs.ANALYSIS_STAGE: described > 0,
        jobs.CAPTION_VECTOR_STAGE: await search_service.has_vector(
            session, VectorKind.CAPTION, media.id
        ),
        jobs.FACES_STAGE: media.face_version >= FACE_VERSION,
    }


async def _undo(session: AsyncSession, media: Media, stage: str) -> None:
    """Drop what the step wrote, so it counts as outstanding again."""
    if stage == "metadata":
        media.metadata_version = 0
    elif stage == "derive":
        media.derive_version = 0
    elif stage == jobs.FACES_STAGE:
        media.face_version = 0
    elif stage == jobs.ANALYSIS_STAGE:
        await session.execute(delete(MediaAnalysis).where(MediaAnalysis.media_id == media.id))
    elif stage == jobs.TRANSCRIPTION_STAGE:
        await session.execute(delete(MediaTranscript).where(MediaTranscript.media_id == media.id))
    elif stage == jobs.IMAGE_VECTOR_STAGE:
        await search_service.forget(session, VectorKind.IMAGE, media.id)
    elif stage == jobs.CAPTION_VECTOR_STAGE:
        await search_service.forget(session, VectorKind.CAPTION, media.id)
