"""Finding the chapters of an album, and handing them out again.

Three things are put together here, all of them from what the library already knows:

- media that look alike, by the picture vectors that are in this database anyway. No machine is
  asked: the vectors were made when the medium was indexed, and comparing them is PostgreSQL's
  work. So the Smarts still work while the AI machine is switched off.
- what a group is called: the tags its media carry and the rest of the album does not. "Katze"
  says something in a family album, "Innenraum" does not, and a name nobody wrote is better
  left off than guessed.
- shelves that need no grouping at all: documents, screenshots, videos, pictures with people.
  They come out of the columns stage 5 already filled in.

Everything here can be thrown away and built again. Nothing anybody typed lives in these tables.
"""

import math
import uuid
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import ColumnElement, Select, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from muninn.ai import service as ai_service
from muninn.models.ai import AiKind
from muninn.models.album import Album
from muninn.models.analysis import MediaAnalysis
from muninn.models.media import Media, MediaKind, MediaStatus
from muninn.models.smart import SMART_VERSION, SmartChapter, SmartChapterMedium
from muninn.search import service as search_service

#: How close two pictures have to be to count as the same kind of thing (cosine distance).
#: Measured on the library: at 0.30 a whole album falls into one lump, at 0.18 a third of it
#: stays single. Between them the groups are what a person would also have put together.
LOOK_DISTANCE = 0.24

#: A group that swallows this share of the album says nothing ("Haus", 206 pictures). It is
#: looked at again, this much tighter, as often as it takes - an album of one wedding hall is
#: alike all the way down, and below this distance nothing is told apart any more.
TOO_BIG_SHARE = 0.10
TIGHTER_BY = 0.06
TIGHTEST = 0.06

#: Fewer than this is not a chapter, it is a coincidence.
MIN_CHAPTER = 4

#: An album with fewer media than this needs no chapters: it is one screen.
WORTH_CHAPTERS = 24

#: A tag has to be on this share of a group to name it, and on this many of its media.
NAME_MIN_SHARE = 0.30
NAME_MIN_COUNT = 3
NAME_WORDS = 3


@dataclass(frozen=True, slots=True)
class Look:
    """What stage 5 saw in one medium, as the chapters need it."""

    media_id: uuid.UUID
    taken_at: datetime | None
    tags: tuple[str, ...]
    scene: str


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


@dataclass
class Built:
    """What one run over one album produced."""

    album_id: uuid.UUID
    chapters: int = 0
    placed: int = 0
    single: int = 0
    groups: list[list[uuid.UUID]] = field(default_factory=list)


async def build_album(
    session: AsyncSession, album_id: uuid.UUID, *, distance: float = LOOK_DISTANCE
) -> Built:
    """Find this album's chapters and write them down, replacing what was there.

    Idempotent: the same album with the same media gives the same chapters, and running it
    twice changes nothing but the time it says it was built.
    """
    profile = await ai_service.active_profile(session, AiKind.IMAGE_EMBEDDER)
    looks = await _looks_of(session, album_id)
    built = Built(album_id=album_id)
    if profile is None or len(looks) < WORTH_CHAPTERS:
        await _replace(session, album_id, [], looks)
        return built

    pairs = await search_service.near_pairs(
        session, album_id=album_id, model=profile.model, max_distance=distance
    )
    ids = [look.media_id for look in looks]
    groups, single = _group(ids, pairs, distance=distance, too_big=int(len(ids) * TOO_BIG_SHARE))
    built.groups = groups
    built.chapters = len(groups)
    built.placed = sum(len(group) for group in groups)
    built.single = len(single)
    await _replace(session, album_id, groups, looks, pairs=pairs)
    return built


def _group(
    ids: Sequence[uuid.UUID],
    pairs: Sequence[tuple[uuid.UUID, uuid.UUID, float]],
    *,
    distance: float,
    too_big: int,
) -> tuple[list[list[uuid.UUID]], list[uuid.UUID]]:
    """The densest picture still free takes its free neighbours with it, then the next.

    Plain and repeatable: no centres to settle, no number of groups to guess beforehand, and
    the same input gives the same output - which is what makes the stage idempotent. A group
    that grew too large is looked at again with a tighter distance.
    """
    order = {one: index for index, one in enumerate(ids)}
    limit = max(too_big, MIN_CHAPTER)
    groups: list[list[uuid.UUID]] = []
    for group in _greedy(ids, _neighbours(pairs, distance), order):
        groups.extend(_split(group, pairs, distance=distance, limit=limit, order=order))

    placed = {one for group in groups for one in group}
    single = [one for one in ids if one not in placed]
    groups.sort(key=len, reverse=True)
    return groups, single


def _split(
    group: list[uuid.UUID],
    pairs: Sequence[tuple[uuid.UUID, uuid.UUID, float]],
    *,
    distance: float,
    limit: int,
    order: dict[uuid.UUID, int],
) -> list[list[uuid.UUID]]:
    """A group too large for the album it is in, taken apart until its parts say something.

    One step is not always enough: a folder of one afternoon in one room is alike at every
    distance, and asking once more at 0.18 gives back the same lump. It is asked again, tighter
    each time, and what is still one group at the tightest distance stays one group - that is
    then the truth about those pictures, not a failure of the grouping.
    """
    if len(group) <= limit:
        return [group]
    tighter = distance - TIGHTER_BY
    while tighter >= TIGHTEST:
        parts = _greedy(group, _neighbours(pairs, tighter), order)
        if parts and max(len(part) for part in parts) <= limit:
            return parts
        if parts and len(parts) > 1:
            # It did fall apart, only not far enough: carry on inside the parts that are left.
            return [
                piece
                for part in parts
                for piece in _split(part, pairs, distance=tighter, limit=limit, order=order)
            ]
        tighter -= TIGHTER_BY
    return [group]


def _neighbours(
    pairs: Sequence[tuple[uuid.UUID, uuid.UUID, float]], distance: float
) -> dict[uuid.UUID, set[uuid.UUID]]:
    near: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    for first, second, apart in pairs:
        if apart <= distance:
            near[first].add(second)
            near[second].add(first)
    return near


def _greedy(
    ids: Sequence[uuid.UUID],
    near: dict[uuid.UUID, set[uuid.UUID]],
    order: dict[uuid.UUID, int],
) -> list[list[uuid.UUID]]:
    free = set(ids)
    groups: list[list[uuid.UUID]] = []
    while free:
        # The most connected picture leads; its position breaks a tie, so the run repeats.
        leader = max(free, key=lambda one: (len(near[one] & free), -order[one]))
        taken = (near[leader] & free) | {leader}
        if len(taken) < MIN_CHAPTER:
            break
        groups.append([leader, *sorted(taken - {leader}, key=lambda one: order[one])])
        free -= taken
    return groups


def name_of(
    group: Sequence[uuid.UUID], looks: dict[uuid.UUID, Look], album: Counter[str], total: int
) -> tuple[str, list[str]]:
    """What this group is called: the tags it has that the album as a whole has not.

    A tag on nearly every picture of the album ("innenraum", "tag") says nothing about a group
    inside it, so it is weighed down by how common it is. When nothing stands out, the scene
    may stand in; when that says nothing either, the chapter keeps its pictures and no name.
    """
    here: Counter[str] = Counter()
    scenes: Counter[str] = Counter()
    for one in group:
        look = looks.get(one)
        if look is None:
            continue
        here.update(set(look.tags))
        if look.scene:
            scenes[look.scene] += 1

    scored: list[tuple[float, str]] = []
    for tag, count in here.items():
        share = count / len(group)
        if share < NAME_MIN_SHARE or count < NAME_MIN_COUNT:
            continue
        everywhere = max(album[tag] / total, 1 / total)
        scored.append((share * math.log(1 / everywhere), tag))
    words = [tag for _, tag in sorted(scored, reverse=True)[:NAME_WORDS]]

    if not words:
        common = scenes.most_common(1)
        if common and common[0][1] > len(group) * 0.4 and common[0][0] != "unbekannt":
            words = [common[0][0]]
    return " · ".join(word.capitalize() for word in words), words


async def _replace(
    session: AsyncSession,
    album_id: uuid.UUID,
    groups: Sequence[Sequence[uuid.UUID]],
    looks: Sequence[Look],
    *,
    pairs: Sequence[tuple[uuid.UUID, uuid.UUID, float]] = (),
) -> None:
    """The album's chapters, as they are now. The old ones go; nothing of them is worth keeping."""
    await session.execute(delete(SmartChapter).where(SmartChapter.album_id == album_id))

    by_id = {look.media_id: look for look in looks}
    everywhere: Counter[str] = Counter()
    for look in looks:
        everywhere.update(set(look.tags))
    apart = {(first, second): value for first, second, value in pairs}

    for group in groups:
        title, words = name_of(group, by_id, everywhere, max(len(looks), 1))
        taken = [
            look.taken_at
            for look in (by_id.get(one) for one in group)
            if look is not None and look.taken_at is not None
        ]
        leader = group[0]
        distances = [apart.get((leader, one), apart.get((one, leader), 0.0)) for one in group[1:]]
        chapter = SmartChapter(
            album_id=album_id,
            kind="look",
            title=title,
            tags=words,
            cover_media_id=leader,
            size=len(group),
            from_at=min(taken) if taken else None,
            until_at=max(taken) if taken else None,
            tightness=sum(distances) / len(distances) if distances else 0.0,
            version=SMART_VERSION,
        )
        session.add(chapter)
        await session.flush()
        session.add_all(
            SmartChapterMedium(chapter_id=chapter.id, media_id=one, position=position)
            for position, one in enumerate(group)
        )
    await session.commit()


async def _looks_of(session: AsyncSession, album_id: uuid.UUID) -> list[Look]:
    rows = await session.execute(
        select(
            Media.id,
            Media.taken_at,
            func.coalesce(MediaAnalysis.tags, []),
            func.coalesce(MediaAnalysis.scene, ""),
        )
        .join(MediaAnalysis, MediaAnalysis.media_id == Media.id, isouter=True)
        .where(
            Media.album_id == album_id,
            Media.status == MediaStatus.ACTIVE,
            Media.duplicate_of.is_(None),
        )
        .order_by(func.coalesce(Media.taken_at, Media.created_at), Media.id)
    )
    return [
        Look(media_id=row[0], taken_at=row[1], tags=tuple(row[2] or ()), scene=row[3] or "")
        for row in rows
    ]


async def albums_to_build(session: AsyncSession) -> list[uuid.UUID]:
    """Albums worth looking at: big enough, and not already built from what they hold now."""
    counted = (
        select(
            Media.album_id, func.count().label("media"), func.max(Media.updated_at).label("last")
        )
        .where(Media.status == MediaStatus.ACTIVE, Media.duplicate_of.is_(None))
        .group_by(Media.album_id)
        .having(func.count() >= WORTH_CHAPTERS)
        .subquery()
    )
    built = (
        select(
            SmartChapter.album_id,
            func.min(SmartChapter.version).label("version"),
            func.max(SmartChapter.built_at).label("built"),
        )
        .group_by(SmartChapter.album_id)
        .subquery()
    )
    statement: Select[tuple[uuid.UUID]] = (
        select(counted.c.album_id)
        .join(built, built.c.album_id == counted.c.album_id, isouter=True)
        .where(
            (built.c.album_id.is_(None))
            | (built.c.version < SMART_VERSION)
            | (built.c.built < counted.c.last)
        )
        .order_by(counted.c.media.desc())
    )
    return list(await session.scalars(statement))


#: What the engine room's button asks for when nobody says otherwise: enough new chapters to
#: fill a screen, and little enough that the answer comes back while somebody is looking at it.
CHAPTERS_WANTED = 21


@dataclass(frozen=True, slots=True)
class Rebuild:
    """What one press of the button did."""

    albums: int
    chapters: int
    #: Albums that still have no chapters of this version, after this run.
    outstanding: int


@dataclass(frozen=True, slots=True)
class State:
    """What the Smarts hold right now, for the admin area."""

    chapters: int
    albums: int
    media: int
    outstanding: int
    built_at: datetime | None
    wanted: int = CHAPTERS_WANTED


async def build_some(
    session: AsyncSession, *, wanted: int = CHAPTERS_WANTED, distance: float = LOOK_DISTANCE
) -> Rebuild:
    """Build albums until this many chapters have come out of it, then stop.

    The albums that have none yet come first, the biggest of them first; after those, the ones
    whose chapters are oldest. So pressing the button again carries on where the last press
    stopped rather than doing the same albums over, and a library nobody has looked at yet is
    worked through from the ends that show most.
    """
    made = 0
    albums = 0
    for album_id in await _in_turn(session):
        built = await build_album(session, album_id, distance=distance)
        albums += 1
        made += built.chapters
        if made >= wanted:
            break
    return Rebuild(albums=albums, chapters=made, outstanding=len(await albums_to_build(session)))


async def _in_turn(session: AsyncSession) -> list[uuid.UUID]:
    """Every album worth chapters: those without them first, then the longest untouched."""
    waiting = await albums_to_build(session)
    done = list(
        await session.scalars(
            select(SmartChapter.album_id)
            .group_by(SmartChapter.album_id)
            .order_by(func.max(SmartChapter.built_at))
        )
    )
    seen = set(waiting)
    return [*waiting, *(album_id for album_id in done if album_id not in seen)]


async def state(session: AsyncSession) -> State:
    """The figures the engine room shows beside the button."""
    chapters, albums, media, built = (
        await session.execute(
            select(
                func.count(),
                func.count(func.distinct(SmartChapter.album_id)),
                func.coalesce(func.sum(SmartChapter.size), 0),
                func.max(SmartChapter.built_at),
            ).select_from(SmartChapter)
        )
    ).one()
    return State(
        chapters=int(chapters or 0),
        albums=int(albums or 0),
        media=int(media or 0),
        outstanding=len(await albums_to_build(session)),
        built_at=built,
    )


async def chapters_of(
    session: AsyncSession,
    album_id: uuid.UUID | None = None,
    *,
    offset: int = 0,
    limit: int = 60,
) -> list[SmartChapter]:
    """The chapters, biggest first. Without an album: the whole library's, for the Smarts screen."""
    statement = select(SmartChapter).order_by(SmartChapter.size.desc(), SmartChapter.id)
    if album_id is not None:
        statement = statement.where(SmartChapter.album_id == album_id)
    return list(await session.scalars(statement.offset(offset).limit(limit)))


async def chapter(session: AsyncSession, chapter_id: uuid.UUID) -> SmartChapter | None:
    return await session.get(SmartChapter, chapter_id)


async def media_of(
    session: AsyncSession, chapter_id: uuid.UUID, *, offset: int = 0, limit: int = 60
) -> list[Media]:
    """The media of one chapter, the clearest examples first."""
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


class UnknownShelfError(KeyError):
    """A shelf nobody has."""


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


async def shelves(session: AsyncSession, album_id: uuid.UUID | None = None) -> list[Shelf]:
    """What the library is made of, without any grouping: one count per trait."""
    where = [Media.status == MediaStatus.ACTIVE, Media.duplicate_of.is_(None)]
    if album_id is not None:
        where.append(Media.album_id == album_id)
    row = (
        await session.execute(
            select(*(func.count().filter(_on_shelf(key)) for key in SHELVES))
            .select_from(Media)
            .join(MediaAnalysis, MediaAnalysis.media_id == Media.id, isouter=True)
            .where(*where)
        )
    ).one()
    return [
        Shelf(key=key, count=int(count or 0))
        for key, count in zip(SHELVES, row, strict=True)
        if count
    ]
