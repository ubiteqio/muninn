"""Counting what a stage could not do, so it stops trying forever.

A stage that cannot handle a medium - a video no decoder here understands, a file damaged on its
way onto the NAS - used to write nothing down, so the medium still counted as outstanding and
the clock handed it out again a minute later. Two such files kept a worker busy all day.

Only the medium's own faults are counted. A machine that is away is not one: that already rests
on its own and comes back by itself, and counting it would use up every attempt in a minute
while the graphics machine is switched off.
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import ColumnElement, and_, delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from muninn.models.attempt import GIVE_UP_AFTER, MediaAttempt

__all__ = ["GIVE_UP_AFTER", "forget", "given_up", "note_failure", "of_media", "still_open"]


async def note_failure(
    session: AsyncSession, media_id: uuid.UUID, stage: str, error: str | None = None
) -> int:
    """One more attempt at this medium that came to nothing. Returns how many there are now."""
    statement = (
        insert(MediaAttempt)
        .values(media_id=media_id, stage=stage, attempts=1, last_error=_short(error))
        .on_conflict_do_update(
            index_elements=[MediaAttempt.media_id, MediaAttempt.stage],
            set_={
                "attempts": MediaAttempt.attempts + 1,
                "last_error": _short(error),
                "last_at": func.now(),
            },
        )
        .returning(MediaAttempt.attempts)
    )
    attempts = await session.scalar(statement)
    await session.commit()
    return int(attempts or 1)


async def forget(session: AsyncSession, media_id: uuid.UUID, stage: str) -> None:
    """It worked after all, or somebody asked for it again: the count starts afresh."""
    await session.execute(
        delete(MediaAttempt).where(MediaAttempt.media_id == media_id, MediaAttempt.stage == stage)
    )


def still_open(stage: str, media_id: InstrumentedAttribute[uuid.UUID]) -> ColumnElement[bool]:
    """The condition every stage adds when it looks for work: not one it has given up on."""
    return (
        ~select(MediaAttempt.media_id)
        .where(
            and_(
                MediaAttempt.media_id == media_id,
                MediaAttempt.stage == stage,
                MediaAttempt.attempts >= GIVE_UP_AFTER,
            )
        )
        .exists()
    )


async def given_up(session: AsyncSession, stages: Sequence[str] | None = None) -> int:
    """How many media the pipeline has given up on, for the engine room."""
    statement = (
        select(func.count()).select_from(MediaAttempt).where(MediaAttempt.attempts >= GIVE_UP_AFTER)
    )
    if stages is not None:
        statement = statement.where(MediaAttempt.stage.in_(stages))
    return int(await session.scalar(statement) or 0)


async def of_media(session: AsyncSession, media_id: uuid.UUID) -> dict[str, MediaAttempt]:
    """What each stage tried and failed on this medium, by stage."""
    rows = await session.scalars(select(MediaAttempt).where(MediaAttempt.media_id == media_id))
    return {row.stage: row for row in rows}


def _short(error: str | None) -> str | None:
    """Enough of the message to recognise the fault, not a whole traceback."""
    if error is None:
        return None
    return error.strip()[:500] or None
