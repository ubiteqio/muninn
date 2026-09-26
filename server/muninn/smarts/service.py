"""Finding the chapters of the library, and handing them out again.

The rules themselves live in muninn.smarts.kinds; this puts them together, writes what they
found and reads it back for the app. Nothing here asks a machine: places, dates and faces come
from the database, and what the pictures look like is compared through the vector index, which
is PostgreSQL's work. The Smarts are therefore as good with the AI machine switched off, which
is when somebody usually sits down to browse.

A run replaces everything. The chapters are derived - throwing them away costs a minute of a
worker's night and nothing else - and building them anew is the only way a library that has
grown falls into the right groups rather than yesterday's.
"""

import random
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import ColumnElement, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from muninn.ai import service as ai_service
from muninn.models.ai import AiKind
from muninn.models.album import Album
from muninn.models.analysis import MediaAnalysis
from muninn.models.media import Media, MediaKind, MediaStatus
from muninn.models.settings import DEFAULT_SMART_MAX_MEDIA
from muninn.models.smart import (
    KIND_DAY,
    KIND_MOTIF,
    KIND_PERSON,
    KIND_PLACE,
    KIND_RITUAL,
    KIND_THEME,
    KIND_TRIP,
    KINDS,
    SMART_VERSION,
    SmartChapter,
    SmartChapterMedium,
)
from muninn.settings import service as settings_service
from muninn.smarts import kinds as rules

#: How close two pictures have to be to count as the same kind of thing (cosine distance).
#: Measured on the library: at 0.30 everything falls into one lump, at 0.18 a third of it stays
#: single. Between them the groups are what a person would also have put together.
LOOK_DISTANCE = 0.24

#: How many smart albums there are, when no setting says otherwise.
CHAPTERS_WANTED = 60

#: How many leaders a run may try before it gives up looking for more motifs. Most pictures
#: belong to a group that is already taken, and each try costs a question to the index.
MOTIF_ATTEMPTS = 400

#: The order the kinds take turns in on the screen: a journey, a day, a theme, a face.
ROTATION = (KIND_TRIP, KIND_DAY, KIND_THEME, KIND_PERSON, KIND_PLACE, KIND_RITUAL, KIND_MOTIF)


@dataclass(frozen=True, slots=True)
class Rebuild:
    """What one run produced, by kind."""

    chapters: int
    media: int
    by_kind: dict[str, int]


@dataclass(frozen=True, slots=True)
class State:
    """What the Smarts hold right now, for the admin area."""

    chapters: int
    media: int
    built_at: datetime | None
    by_kind: dict[str, int]
    #: The two numbers an admin sets: how many there are, and how much each one holds.
    max_chapters: int
    max_media: int


async def rebuild(
    session: AsyncSession,
    *,
    wanted: int | None = None,
    max_media: int | None = None,
    distance: float = LOOK_DISTANCE,
    seed: int | None = None,
) -> Rebuild:
    """Find every chapter anew, across the whole library.

    Every rule runs first and hands back everything it found; the kinds then take turns, and
    the list is cut to the number that was asked for. Cutting after the turns rather than
    before is what keeps the mixture: thirty chapters are five of each kind, not the thirty
    largest, which would all be motifs.

    Which of them are kept, and which pictures each one shows, is drawn anew every run. A
    library of ninety journeys, days and themes can only show twenty-one of them, and always
    the same twenty-one would make the screen a poster. So the same button pressed twice gives
    another wall: other journeys, other faces, other pictures of the same lake. ``seed`` fixes
    the draw where somebody needs the same answer twice, which is what the tests do.
    """
    # Which chapters and which pictures, not a secret: nothing here guards anything.
    drawn = random.Random(seed)  # noqa: S311
    settings = await settings_service.get_settings(session)
    cap = max_media if max_media is not None else settings.smart_max_media
    most = wanted if wanted is not None else settings.smart_max_chapters

    home = await rules.home_place(session)
    journeys = await rules.trips(session, home=home)
    spoken_for = _days_of(journeys)
    candidates = [
        *journeys,
        *await rules.days(session, taken=spoken_for),
        *await rules.themes(session),
        *await rules.persons(session),
        *await rules.places(session),
        *await rules.rituals(session),
    ]

    profile = await ai_service.active_profile(session, AiKind.IMAGE_EMBEDDER)
    if profile is not None:
        candidates.extend(
            await rules.motifs(
                session,
                model=profile.model,
                distance=distance,
                # Enough to fill the wall with motifs if the other rules found little.
                wanted=most,
                attempts=MOTIF_ATTEMPTS,
                seed=str(drawn.random()),
            )
        )

    return await _write(session, candidates, cap=cap, most=most, drawn=drawn)


def _days_of(journeys: Sequence[rules.Candidate]) -> list[date]:
    """Every day a journey already tells about, so no day chapter says the same thing again."""
    spoken: list[date] = []
    for journey in journeys:
        first = date.fromisoformat(str(journey.title_args["from"]))
        last = date.fromisoformat(str(journey.title_args["until"]))
        spoken.extend(
            date.fromordinal(day) for day in range(first.toordinal(), last.toordinal() + 1)
        )
    return spoken


async def _write(
    session: AsyncSession,
    candidates: Sequence[rules.Candidate],
    *,
    cap: int,
    most: int,
    drawn: random.Random,
) -> Rebuild:
    """Everything that was found, in the order the screen shows it. The old chapters go."""
    await session.execute(delete(SmartChapter))

    by_kind: dict[str, int] = {}
    media = 0
    for position, candidate in enumerate(_interleaved(candidates, drawn)[:most]):
        kept = _some_of(candidate.media, cap, drawn)
        if not kept:
            continue
        span, albums = await _about(session, kept)
        chapter = SmartChapter(
            kind=candidate.kind,
            title_key=candidate.title_key,
            title_args=candidate.title_args,
            tags=candidate.tags,
            cover_media_id=kept[0],
            size=len(kept),
            rank=position,
            albums=albums,
            album_id=None,
            from_at=span[0],
            until_at=span[1],
            version=SMART_VERSION,
        )
        session.add(chapter)
        await session.flush()
        session.add_all(
            SmartChapterMedium(chapter_id=chapter.id, media_id=one, position=index)
            for index, one in enumerate(kept)
        )
        by_kind[candidate.kind] = by_kind.get(candidate.kind, 0) + 1
        media += len(kept)

    await session.commit()
    return Rebuild(chapters=sum(by_kind.values()), media=media, by_kind=by_kind)


def _some_of(media: Sequence[uuid.UUID], cap: int, drawn: random.Random) -> list[uuid.UUID]:
    """At most this many of them, drawn from the whole chapter rather than off the top.

    A journey of four hundred pictures capped at fifty would otherwise be the first morning,
    four times over. Drawn across the whole of it, the fifty are the whole journey - and other
    fifty next time. What is drawn keeps its order, so a journey still runs from Friday to
    Monday and a motif still leads with what it was built around.
    """
    if len(media) <= cap:
        return list(media)
    chosen = set(drawn.sample(range(len(media)), cap))
    return [one for index, one in enumerate(media) if index in chosen]


def _interleaved(
    candidates: Sequence[rules.Candidate], drawn: random.Random
) -> list[rules.Candidate]:
    """The kinds take turns, and which one of a kind comes next is drawn.

    A screen that lists every journey, then every day, then every motif is a report. Taking
    turns makes it a wall somebody wants to look through: whatever catches the eye next is of
    another kind than the last one. Drawing rather than sorting by size is what makes the
    second press of the button worth pressing - every candidate here has already earned its
    place, so none of them is a worse answer than the largest.
    """
    piles: dict[str, list[rules.Candidate]] = {kind: [] for kind in KINDS}
    for candidate in candidates:
        piles.setdefault(candidate.kind, []).append(candidate)
    for pile in piles.values():
        drawn.shuffle(pile)

    mixed: list[rules.Candidate] = []
    while any(piles.values()):
        for kind in ROTATION:
            pile = piles.get(kind, [])
            if pile:
                mixed.append(pile.pop(0))
    return mixed


async def _about(
    session: AsyncSession, media_ids: Sequence[uuid.UUID]
) -> tuple[tuple[datetime | None, datetime | None], int]:
    """When a chapter's media were taken, and how many folders they lie in."""
    row = (
        await session.execute(
            select(
                func.min(Media.taken_at),
                func.max(Media.taken_at),
                func.count(func.distinct(Media.album_id)),
            ).where(Media.id.in_(media_ids))
        )
    ).one()
    return (row[0], row[1]), int(row[2] or 1)


async def state(session: AsyncSession) -> State:
    """The figures the settings show beside the button."""
    rows = (
        await session.execute(
            select(
                SmartChapter.kind, func.count(), func.coalesce(func.sum(SmartChapter.size), 0)
            ).group_by(SmartChapter.kind)
        )
    ).all()
    built = await session.scalar(select(func.max(SmartChapter.built_at)))
    settings = await settings_service.get_settings(session)
    return State(
        chapters=sum(int(row[1]) for row in rows),
        media=sum(int(row[2]) for row in rows),
        built_at=built,
        by_kind={str(row[0]): int(row[1]) for row in rows},
        max_chapters=settings.smart_max_chapters or CHAPTERS_WANTED,
        max_media=settings.smart_max_media or DEFAULT_SMART_MAX_MEDIA,
    )


async def chapters_of(
    session: AsyncSession, *, kind: str | None = None, offset: int = 0, limit: int = 60
) -> list[SmartChapter]:
    """The chapters in the order they were mixed: the kinds taking turns, biggest first."""
    statement = select(SmartChapter).order_by(SmartChapter.rank, SmartChapter.id)
    if kind is not None:
        statement = statement.where(SmartChapter.kind == kind)
    return list(await session.scalars(statement.offset(offset).limit(limit)))


async def chapter(session: AsyncSession, chapter_id: uuid.UUID) -> SmartChapter | None:
    return await session.get(SmartChapter, chapter_id)


async def media_of(
    session: AsyncSession, chapter_id: uuid.UUID, *, offset: int = 0, limit: int = 60
) -> list[Media]:
    """The media of one chapter, in the order the chapter keeps them."""
    return list(
        await session.scalars(
            select(Media)
            .join(SmartChapterMedium, SmartChapterMedium.media_id == Media.id)
            .where(
                SmartChapterMedium.chapter_id == chapter_id,
                Media.status == MediaStatus.ACTIVE,
            )
            .order_by(SmartChapterMedium.position)
            .offset(offset)
            .limit(limit)
        )
    )


async def album_of(session: AsyncSession, album_id: uuid.UUID) -> Album | None:
    return await session.get(Album, album_id)


#: The shelves, and what stands on each: a condition on what stage 5 wrote down.
SHELVES: dict[str, str] = {
    "people": "pictures with somebody in them",
    "crowd": "four people or more",
    "video": "videos",
    "document": "papers, receipts, whiteboards",
    "screenshot": "screenshots",
    "text": "something readable in the picture",
}


@dataclass(frozen=True, slots=True)
class Shelf:
    """A group that needs no grouping: everything with one trait."""

    key: str
    count: int


class UnknownShelfError(KeyError):
    """A shelf nobody has."""


def _on_shelf(key: str) -> ColumnElement[bool]:
    """What stands on one shelf. One place, so the count and the list can never disagree."""
    conditions: dict[str, ColumnElement[bool]] = {
        "people": MediaAnalysis.people_count > 0,
        "crowd": MediaAnalysis.people_count >= 4,
        "video": Media.kind == MediaKind.VIDEO,
        "document": MediaAnalysis.is_document.is_(True),
        "screenshot": MediaAnalysis.is_screenshot.is_(True),
        "text": MediaAnalysis.ocr_text != "",
    }
    return conditions[key]


async def media_on_shelf(
    session: AsyncSession, key: str, *, offset: int = 0, limit: int = 60
) -> list[Media]:
    """What stands on one shelf, newest first."""
    if key not in SHELVES:
        raise UnknownShelfError(key)
    return list(
        await session.scalars(
            select(Media)
            .join(MediaAnalysis, MediaAnalysis.media_id == Media.id, isouter=True)
            .where(
                Media.status == MediaStatus.ACTIVE,
                Media.duplicate_of.is_(None),
                _on_shelf(key),
            )
            .order_by(func.coalesce(Media.taken_at, Media.created_at).desc(), Media.id)
            .offset(offset)
            .limit(limit)
        )
    )


async def shelves(session: AsyncSession) -> list[Shelf]:
    """What the library is made of, without any grouping: one count per trait."""
    row = (
        await session.execute(
            select(*(func.count().filter(_on_shelf(key)) for key in SHELVES))
            .select_from(Media)
            .join(MediaAnalysis, MediaAnalysis.media_id == Media.id, isouter=True)
            .where(Media.status == MediaStatus.ACTIVE, Media.duplicate_of.is_(None))
        )
    ).one()
    return [
        Shelf(key=key, count=int(count or 0))
        for key, count in zip(SHELVES, row, strict=True)
        if count
    ]
