"""The rules that make chapters. One per kind, each reading what the library already knows.

None of them asks a machine. Time and place come from the files themselves, the faces were
found by stage 7 long ago, and what the pictures look like is the vectors that are in this
database anyway. So the Smarts are built - and browsed - while the AI machine is switched off.

Every rule hands back candidates; the service writes them. A medium may lie in several chapters
at once: a picture of the cat in Chessy belongs to the trip and to the cat, and both are true.
Only the motifs are exclusive among themselves, because one picture looks most like one thing.
"""

import math
import uuid
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import Integer, Text, and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from muninn.models.analysis import MediaAnalysis
from muninn.models.face import Face, Person
from muninn.models.media import Media, MediaStatus
from muninn.models.place import Place
from muninn.models.smart import (
    KIND_DAY,
    KIND_MOTIF,
    KIND_PERSON,
    KIND_PLACE,
    KIND_RITUAL,
    KIND_THEME,
    KIND_TRIP,
)
from muninn.search import service as search_service

#: A trip: this far apart in time and it is another journey, not the same one. Three days let
#: two visits to the same town in one week become one fortnight that never happened.
TRIP_GAP_DAYS = 2
#: What makes a journey rather than an afternoon out.
TRIP_MIN_DAYS = 2
TRIP_MIN_MEDIA = 15

#: A day worth its own chapter has this many pictures. A family takes a handful on an ordinary
#: day; a christening, a match or a birthday leaves dozens.
DAY_MIN_MEDIA = 40

#: A town is worth a chapter from this many pictures, taken on at least this many days - twenty
#: pictures of one afternoon are that afternoon, not a place one keeps coming back to.
PLACE_MIN_MEDIA = 40
PLACE_MIN_DAYS = 3

#: A feast is worth a chapter once it has been kept in this many years.
RITUAL_MIN_YEARS = 3
RITUAL_MIN_MEDIA = 20

#: Somebody in one year, and two people together.
PERSON_MIN_MEDIA = 30
PERSON_MOST = 10
PERSON_YEARS_EACH = 3
PAIR_MIN_MEDIA = 30

#: How many media one motif is measured against at most. Beyond this the chapter is capped
#: anyway, and the index has better things to do.
MOTIF_NEIGHBOURS = 1500
#: A motif of fewer than this is a coincidence, not a thing the library is full of.
MOTIF_MIN_MEDIA = 8

#: The themes: things a family archive is full of, each with the words that give it away.
#:
#: Written out rather than found by a machine, because a name somebody wrote - "Am Wasser",
#: "Ins Grüne" - says more than any three tags a clustering would agree on, and because these
#: are the things one goes looking for. What the library has none of simply does not appear.
#: Measured on 8000 media here: none of these is empty, and the smallest holds two dozen.
THEMES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("water", ("wasser", "pool", "meer", "strand", "see", "welle", "fluss", "schwimmen")),
    ("green", ("wald", "bäume", "gras", "wiese", "berg", "pflanze", "natur")),
    ("sport", ("fußball", "trikot", "sport", "stadion", "basketball", "zuschauer", "tor")),
    ("city", ("stadt", "architektur", "gebäude", "fassade", "plaza", "straße")),
    ("animals", ("katze", "hund", "tier", "pferd", "kuh", "vogel", "haustier")),
    ("table", ("essen", "teller", "restaurant", "grill", "kuchen", "torte", "gericht")),
    ("wheels", ("fahrrad", "auto", "motorrad", "zug", "bus", "roller", "helm")),
    ("flowers", ("blume", "blüte", "blumen", "garten")),
    ("snow", ("schnee", "ski", "schlitten", "eis", "winter")),
    ("beach", ("strand", "sand", "muschel", "düne")),
    ("stage", ("bühne", "konzert", "gitarre", "mikrofon", "instrument", "theater")),
    ("paper", ("dokument", "whiteboard", "bildschirm", "laptop", "handschrift", "diagramm")),
    ("sundown", ("sonnenuntergang", "dämmerung", "abendrot", "sonnenaufgang")),
    ("playground", ("spielplatz", "rutsche", "schaukel", "sandkasten")),
    ("fireworks", ("feuerwerk", "rakete", "wunderkerze")),
)

#: A theme with fewer pictures than this is not something the library is full of.
THEME_MIN_MEDIA = 20

#: How many pictures of one year a theme takes before it moves on to the next. Without it "Am
#: Wasser" would be one summer, and the point of a theme is that it runs through the archive.
THEME_PER_YEAR = 12

#: The feasts that repeat on the calendar, as (key, month, first day, last day).
FEASTS = (
    ("christmas", 12, 24, 26),
    ("newyear", 12, 31, 31),
)


@dataclass(frozen=True, slots=True)
class Away:
    """One picture taken away from home, as the trips need it."""

    media_id: uuid.UUID
    taken_at: datetime
    place: str


@dataclass(frozen=True, slots=True)
class Candidate:
    """A chapter before it is written down."""

    kind: str
    #: The text key the app renders, and what it renders with.
    title_key: str
    title_args: dict[str, Any]
    #: In the order they should be kept: the cover is the first of them.
    media: list[uuid.UUID]
    tags: list[str] = field(default_factory=list)


async def home_place(session: AsyncSession) -> int | None:
    """Where most of the pictures were taken. Everything else is away.

    A library that knows only one place has no home to speak of - everything it knows about is
    somewhere the family went - so nothing is excluded there, or the one journey it holds would
    be taken for home and never become a chapter.
    """
    places_known = await session.scalar(
        select(func.count(func.distinct(Media.place_id))).where(
            Media.status == MediaStatus.ACTIVE, Media.place_id.is_not(None)
        )
    )
    if int(places_known or 0) < 2:
        return None
    return await session.scalar(
        select(Media.place_id)
        .where(Media.status == MediaStatus.ACTIVE, Media.place_id.is_not(None))
        .group_by(Media.place_id)
        .order_by(func.count().desc())
        .limit(1)
    )


async def trips(session: AsyncSession, *, home: int | None) -> list[Candidate]:
    """Days in a row away from home: the journeys.

    A trip is found from the pictures that know where they were taken, and then everything from
    those days joins it - the pictures without a place were taken on the same journey.
    """
    found_rows = (
        await session.execute(
            select(Media.id, Media.taken_at, Media.place_id, Place.name)
            .join(Place, Place.id == Media.place_id)
            .where(
                Media.status == MediaStatus.ACTIVE,
                Media.duplicate_of.is_(None),
                Media.taken_at.is_not(None),
                # Away from home - and everywhere is away when no home stands out yet.
                Media.place_id != home if home is not None else Media.place_id.is_not(None),
            )
            .order_by(Media.taken_at)
        )
    ).all()
    # Only the three the run needs, as plain tuples: id, when, town.
    rows: list[Away] = [
        Away(media_id=row[0], taken_at=row[1], place=str(row[3]))
        for row in found_rows
        if row[1] is not None
    ]

    found: list[Candidate] = []
    for run in _runs(rows, gap=timedelta(days=TRIP_GAP_DAYS)):
        days = {row.taken_at.date() for row in run}
        if len(days) < TRIP_MIN_DAYS or len(run) < TRIP_MIN_MEDIA:
            continue
        # The town most of the pictures were taken in gives the trip its name.
        towns = _most_common(row.place for row in run)
        first, last = run[0].taken_at, run[-1].taken_at
        media = await _media_on(session, sorted(days))
        found.append(
            Candidate(
                kind=KIND_TRIP,
                title_key="trip",
                title_args={
                    "place": towns,
                    "days": len(days),
                    "from": first.date().isoformat(),
                    "until": last.date().isoformat(),
                },
                media=media,
            )
        )
    return found


async def days(session: AsyncSession, *, taken: Sequence[date] = ()) -> list[Candidate]:
    """A single day with far more pictures than an ordinary one.

    Days that a trip already tells about are left to the trip: the same pictures under two
    names, one of them "der 30. Oktober", says less than "Vier Tage Chessy".
    """
    spoken_for = set(taken)
    day = func.date(Media.taken_at)
    rows = (
        await session.execute(
            select(day.label("day"), func.count().label("media"))
            .where(
                Media.status == MediaStatus.ACTIVE,
                Media.duplicate_of.is_(None),
                Media.taken_at.is_not(None),
            )
            .group_by(day)
            .having(func.count() >= DAY_MIN_MEDIA)
            .order_by(func.count().desc())
        )
    ).all()

    found: list[Candidate] = []
    for when, _count in rows:
        if when in spoken_for:
            continue
        media, place = await _media_of_day(session, when)
        if not media:
            continue
        found.append(
            Candidate(
                kind=KIND_DAY,
                title_key="day",
                title_args={"day": when.isoformat(), **({"place": place} if place else {})},
                media=media,
            )
        )
    return found


async def places(session: AsyncSession) -> list[Candidate]:
    """One town, across all the years it turns up in."""
    day = func.date(Media.taken_at)
    rows = (
        await session.execute(
            select(
                Place.id,
                Place.name,
                func.count().label("media"),
                func.count(func.distinct(day)).label("days"),
            )
            .select_from(Media)
            .join(Place, Place.id == Media.place_id)
            .where(Media.status == MediaStatus.ACTIVE, Media.duplicate_of.is_(None))
            .group_by(Place.id, Place.name)
            .having(
                and_(
                    func.count() >= PLACE_MIN_MEDIA,
                    func.count(func.distinct(day)) >= PLACE_MIN_DAYS,
                )
            )
            .order_by(func.count().desc())
        )
    ).all()

    found: list[Candidate] = []
    for place_id, name, _media, _days in rows:
        ids = list(
            await session.scalars(
                _newest(Media.place_id == place_id),
            )
        )
        years = await _years(session, Media.place_id == place_id)
        found.append(
            Candidate(
                kind=KIND_PLACE,
                title_key="place",
                title_args={"place": name, "from": years[0], "until": years[1]},
                media=ids,
            )
        )
    return found


async def rituals(session: AsyncSession) -> list[Candidate]:
    """The feasts: the same days of the calendar, however many years they have been kept."""
    found: list[Candidate] = []
    for key, month, first, last in FEASTS:
        condition = and_(
            func.extract("month", Media.taken_at) == month,
            func.extract("day", Media.taken_at).between(first, last),
        )
        counted = await session.execute(
            select(
                func.count(),
                func.count(func.distinct(func.cast(func.extract("year", Media.taken_at), Integer))),
            ).where(
                Media.status == MediaStatus.ACTIVE,
                Media.duplicate_of.is_(None),
                Media.taken_at.is_not(None),
                condition,
            )
        )
        media, years = counted.one()
        if int(media or 0) < RITUAL_MIN_MEDIA or int(years or 0) < RITUAL_MIN_YEARS:
            continue
        found.append(
            Candidate(
                kind=KIND_RITUAL,
                title_key=key,
                title_args={"years": int(years)},
                media=list(await session.scalars(_newest(condition))),
            )
        )
    return found


async def persons(session: AsyncSession) -> list[Candidate]:
    """Everybody named, one year at a time - and the two who are always in the picture together."""
    year = func.cast(func.extract("year", func.coalesce(Media.taken_at, Media.created_at)), Integer)
    rows = (
        await session.execute(
            select(Person.id, Person.name, year.label("year"), func.count(func.distinct(Media.id)))
            .select_from(Face)
            .join(Person, Person.id == Face.person_id)
            .join(Media, Media.id == Face.media_id)
            .where(
                Media.status == MediaStatus.ACTIVE,
                Media.duplicate_of.is_(None),
                Person.hidden.is_(False),
            )
            .group_by(Person.id, Person.name, "year")
            .having(func.count(func.distinct(Media.id)) >= PERSON_MIN_MEDIA)
            .order_by(func.count(func.distinct(Media.id)).desc())
        )
    ).all()

    found: list[Candidate] = []
    seen: dict[uuid.UUID, int] = {}
    for person_id, name, in_year, _count in rows:
        if len(seen) >= PERSON_MOST and person_id not in seen:
            continue
        if seen.get(person_id, 0) >= PERSON_YEARS_EACH:
            continue
        seen[person_id] = seen.get(person_id, 0) + 1
        condition = and_(
            Media.id.in_(select(Face.media_id).where(Face.person_id == person_id)),
            func.extract("year", func.coalesce(Media.taken_at, Media.created_at)) == in_year,
        )
        found.append(
            Candidate(
                kind=KIND_PERSON,
                title_key="person",
                title_args={"name": name, "year": int(in_year)},
                media=list(await session.scalars(_newest(condition))),
            )
        )
    return [*found, *await _pairs(session)]


async def _pairs(session: AsyncSession) -> list[Candidate]:
    """Two people who keep turning up in the same picture."""
    first = Face.__table__.alias("first")
    second = Face.__table__.alias("second")
    one = Person.__table__.alias("one")
    other = Person.__table__.alias("other")
    rows = (
        await session.execute(
            select(
                one.c.id,
                one.c.name,
                other.c.id,
                other.c.name,
                func.count(func.distinct(first.c.media_id)).label("media"),
            )
            .select_from(first)
            .join(
                second,
                and_(second.c.media_id == first.c.media_id, second.c.person_id > first.c.person_id),
            )
            .join(one, one.c.id == first.c.person_id)
            .join(other, other.c.id == second.c.person_id)
            .join(Media, Media.id == first.c.media_id)
            .where(
                Media.status == MediaStatus.ACTIVE,
                Media.duplicate_of.is_(None),
                one.c.hidden.is_(False),
                other.c.hidden.is_(False),
            )
            .group_by(one.c.id, one.c.name, other.c.id, other.c.name)
            .having(func.count(func.distinct(first.c.media_id)) >= PAIR_MIN_MEDIA)
            .order_by(func.count(func.distinct(first.c.media_id)).desc())
            .limit(6)
        )
    ).all()

    found: list[Candidate] = []
    for one_id, one_name, other_id, other_name, _media in rows:
        condition = and_(
            Media.id.in_(select(Face.media_id).where(Face.person_id == one_id)),
            Media.id.in_(select(Face.media_id).where(Face.person_id == other_id)),
        )
        found.append(
            Candidate(
                kind=KIND_PERSON,
                title_key="pair",
                title_args={"first": one_name, "second": other_name},
                media=list(await session.scalars(_newest(condition))),
            )
        )
    return found


async def themes(session: AsyncSession) -> list[Candidate]:
    """The things a family archive is full of, each under a name somebody wrote.

    Their pictures are gathered a few per year rather than the newest first: a theme that shows
    only last summer says nothing about twenty-six years, and the years next to each other are
    half the pleasure - the same lake, the children a head taller each time. Which of them are
    kept is the service's business, and it picks differently every run.
    """
    found: list[Candidate] = []
    for key, tags in THEMES:
        rows = (
            await session.execute(
                select(
                    Media.id,
                    func.cast(
                        func.extract("year", func.coalesce(Media.taken_at, Media.created_at)),
                        Integer,
                    ).label("year"),
                )
                .join(MediaAnalysis, MediaAnalysis.media_id == Media.id)
                .where(
                    Media.status == MediaStatus.ACTIVE,
                    Media.duplicate_of.is_(None),
                    MediaAnalysis.tags.overlap(list(tags)),
                )
                .order_by("year", func.coalesce(Media.taken_at, Media.created_at))
            )
        ).all()
        if len(rows) < THEME_MIN_MEDIA:
            continue

        by_year: dict[int, list[uuid.UUID]] = {}
        for media_id, year in rows:
            by_year.setdefault(int(year), []).append(media_id)
        found.append(
            Candidate(
                kind=KIND_THEME,
                title_key=key,
                title_args={"years": len(by_year)},
                media=_a_few_per_year(by_year),
            )
        )
    return found


def _a_few_per_year(by_year: dict[int, list[uuid.UUID]]) -> list[uuid.UUID]:
    """Every year in turn, a handful at a time, so the years stand next to each other."""
    taken: list[uuid.UUID] = []
    years = sorted(by_year, reverse=True)
    for start in range(0, max((len(one) for one in by_year.values()), default=0), THEME_PER_YEAR):
        for year in years:
            taken.extend(by_year[year][start : start + THEME_PER_YEAR])
    return taken


async def motifs(
    session: AsyncSession,
    *,
    model: str,
    distance: float,
    wanted: int,
    attempts: int,
    seed: str = "",
) -> list[Candidate]:
    """What the library is full of: the pictures that look alike, across every folder.

    One question per chapter, asked of the index: the first picture nobody has taken yet leads,
    and everything within the distance goes with it. A library of any size costs the same per
    chapter, which a comparison of every picture with every other does not.
    """
    everywhere: dict[str, int] = {}
    tags = await _tags(session)
    for words in tags.values():
        for word in set(words):
            everywhere[word] = everywhere.get(word, 0) + 1
    total = max(len(tags), 1)

    leaders = list(
        await session.scalars(
            select(Media.id)
            .where(Media.status == MediaStatus.ACTIVE, Media.duplicate_of.is_(None))
            # Shuffled, and differently on every run: which picture leads decides what the
            # motif becomes, so a second run finds other things the library is full of - the
            # same seed gives the same order again, which is what the tests hold on to.
            .order_by(func.md5(func.concat(func.cast(Media.id, Text), seed)))
        )
    )

    taken: set[uuid.UUID] = set()
    found: list[Candidate] = []
    tried = 0
    for leader in leaders:
        if len(found) >= wanted or tried >= attempts:
            break
        if leader in taken:
            continue
        tried += 1
        near = await search_service.near_to(
            session, leader, model=model, max_distance=distance, limit=MOTIF_NEIGHBOURS
        )
        group = [media_id for media_id, _ in near if media_id not in taken]
        if len(group) < MOTIF_MIN_MEDIA:
            continue
        taken.update(group)
        words = _distinctive(group, tags, everywhere, total)
        found.append(
            Candidate(
                kind=KIND_MOTIF,
                title_key="motif",
                title_args={"words": " · ".join(word.capitalize() for word in words)},
                media=group,
                tags=words,
            )
        )
    return found


def _distinctive(
    group: Sequence[uuid.UUID],
    tags: dict[uuid.UUID, Sequence[str]],
    everywhere: dict[str, int],
    total: int,
) -> list[str]:
    """The tags this group has that the library as a whole has not."""
    here: Counter[str] = Counter()
    for one in group:
        here.update(set(tags.get(one, ())))
    scored = [
        (share * math.log(1 / max(everywhere.get(tag, 1) / total, 1 / total)), tag)
        for tag, count in here.items()
        if (share := count / len(group)) >= 0.30 and count >= 3
    ]
    return [tag for _, tag in sorted(scored, reverse=True)[:3]]


async def _tags(session: AsyncSession) -> dict[uuid.UUID, Sequence[str]]:
    rows = await session.execute(
        select(MediaAnalysis.media_id, MediaAnalysis.tags).join(
            Media, Media.id == MediaAnalysis.media_id
        )
    )
    return {row[0]: tuple(row[1] or ()) for row in rows}


def _runs(rows: Sequence[Away], *, gap: timedelta) -> list[list[Away]]:
    """Pictures in time order, cut wherever more than the gap lies between two of them."""
    runs: list[list[Away]] = []
    for row in rows:
        if runs and row.taken_at - runs[-1][-1].taken_at <= gap:
            runs[-1].append(row)
        else:
            runs.append([row])
    return runs


def _most_common(values: Any) -> str:
    counted = Counter(values).most_common(1)
    return counted[0][0] if counted else ""


def _newest(condition: Any) -> Any:
    """The media a chapter holds, newest first. The service caps how many are kept."""
    return (
        select(Media.id)
        .where(Media.status == MediaStatus.ACTIVE, Media.duplicate_of.is_(None), condition)
        .order_by(func.coalesce(Media.taken_at, Media.created_at).desc(), Media.id)
    )


async def _media_on(session: AsyncSession, days: Sequence[date]) -> list[uuid.UUID]:
    """Everything from those days, whether or not it knows where it was taken.

    The days themselves, not the range between the first and the last: a journey with a gap in
    it would otherwise swallow the days at home in between, and whole days rather than the
    hours with a place, because the camera that knows nothing of GPS was on the same journey
    and took the last picture of the evening.
    """
    return list(
        await session.scalars(
            select(Media.id)
            .where(
                Media.status == MediaStatus.ACTIVE,
                Media.duplicate_of.is_(None),
                Media.taken_at.is_not(None),
                func.date(Media.taken_at).in_(list(days)),
            )
            .order_by(Media.taken_at, Media.id)
        )
    )


async def _media_of_day(session: AsyncSession, when: date) -> tuple[list[uuid.UUID], str | None]:
    condition = func.date(Media.taken_at) == when
    ids = list(await session.scalars(_newest(condition)))
    place = await session.scalar(
        select(Place.name)
        .select_from(Media)
        .join(Place, Place.id == Media.place_id)
        .where(Media.status == MediaStatus.ACTIVE, condition)
        .group_by(Place.name)
        .order_by(func.count().desc())
        .limit(1)
    )
    return ids, place


async def _years(session: AsyncSession, condition: Any) -> tuple[int, int]:
    row = (
        await session.execute(
            select(
                func.min(func.extract("year", Media.taken_at)),
                func.max(func.extract("year", Media.taken_at)),
            ).where(Media.status == MediaStatus.ACTIVE, Media.taken_at.is_not(None), condition)
        )
    ).one()
    return int(row[0] or 0), int(row[1] or 0)
