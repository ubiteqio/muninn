"""Midgard: where the media were taken, as the map asks for it.

The map never loads every point. It asks for the part it shows, and the database groups the
points of that part into clusters on a grid whose cells are a fixed number of screen pixels
wide at the zoom level asked for - so a cluster dissolves into smaller ones as one zooms in, and
150,000 points cost no more than a few dozen circles. The grid lies in Web Mercator, the
projection the map draws in, so a cell is square on the screen wherever it lies.
"""

import asyncio
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from muninn.albums.service import SORT_KEY
from muninn.models.album import Album
from muninn.models.media import Media, MediaStatus, shown
from muninn.models.place import Place
from muninn.places import gazetteer

#: How wide a cluster's cell is on the screen. About the size of the circle that shows it.
CELL_PIXELS = 60

#: Web Mercator ends here; a point beyond cannot be projected and is left off the map.
MERCATOR_LIMIT = 85.05

#: The earth's circumference in Web Mercator metres, and the width of one map tile in pixels.
_EQUATOR_METRES = 40_075_016.686
_TILE_PIXELS = 256

MAX_PAGE_SIZE = 200


@dataclass(frozen=True, slots=True)
class Area:
    """The visible part of the map, in degrees. West is left of east; nothing wraps around."""

    west: float
    south: float
    east: float
    north: float


@dataclass(frozen=True, slots=True)
class Cluster:
    latitude: float
    longitude: float
    count: int
    #: The newest medium of the cluster, whose thumbnail stands for it.
    cover_id: uuid.UUID
    cover_has_thumbnail: bool
    #: The box around its points, so a tap can zoom the map to exactly them.
    bounds: Area


def cell_metres(zoom: float) -> float:
    """The width of a cluster cell at this zoom level."""
    return _EQUATOR_METRES / (2**zoom) / _TILE_PIXELS * CELL_PIXELS


_CLUSTERS = text(
    """
    WITH located AS (
        SELECT m.id, m.location, m.thumbnail_path, m.taken_at, m.created_at
          FROM media m
         WHERE m.status = :active AND m.duplicate_of IS NULL
           AND m.location && ST_MakeEnvelope(:west, :south, :east, :north, 4326)
        UNION ALL
        -- Media without coordinates stand where their album's place is.
        SELECT m.id, p.location, m.thumbnail_path, m.taken_at, m.created_at
          FROM media m JOIN places p ON p.id = m.place_id
         WHERE m.status = :active AND m.duplicate_of IS NULL AND m.place_estimated
           AND p.location && ST_MakeEnvelope(:west, :south, :east, :north, 4326)
    ),
    points AS (
        SELECT id, location, thumbnail_path IS NOT NULL AS has_thumbnail,
               coalesce(taken_at, created_at) AS sort_key,
               ST_SnapToGrid(ST_Transform(location, 3857), CAST(:cell AS float)) AS cell
          FROM located
         WHERE ST_Y(location) BETWEEN -CAST(:limit AS float) AND :limit
    )
    SELECT count(*) AS total,
           ST_Y(ST_Centroid(ST_Collect(location))) AS latitude,
           ST_X(ST_Centroid(ST_Collect(location))) AS longitude,
           (array_agg(id ORDER BY sort_key DESC, id DESC))[1] AS cover_id,
           (array_agg(has_thumbnail ORDER BY sort_key DESC, id DESC))[1] AS cover_has_thumbnail,
           ST_XMin(ST_Extent(location)) AS west,
           ST_YMin(ST_Extent(location)) AS south,
           ST_XMax(ST_Extent(location)) AS east,
           ST_YMax(ST_Extent(location)) AS north
    FROM points
    GROUP BY cell
    ORDER BY total DESC
    """
)


async def clusters(session: AsyncSession, area: Area, *, zoom: float) -> list[Cluster]:
    """The points of this part of the map, grouped into cells of about CELL_PIXELS."""
    rows = await session.execute(
        _CLUSTERS,
        {
            "cell": cell_metres(zoom),
            "active": MediaStatus.ACTIVE.value,
            "west": area.west,
            "south": area.south,
            "east": area.east,
            "north": area.north,
            "limit": MERCATOR_LIMIT,
        },
    )
    return [
        Cluster(
            latitude=row.latitude,
            longitude=row.longitude,
            count=row.total,
            cover_id=row.cover_id,
            cover_has_thumbnail=row.cover_has_thumbnail,
            bounds=Area(west=row.west, south=row.south, east=row.east, north=row.north),
        )
        for row in rows
    ]


@dataclass(frozen=True, slots=True)
class AreaPage:
    items: list[Media]
    has_next: bool


async def media_in(
    session: AsyncSession,
    area: Area,
    *,
    limit: int,
    cursor: tuple[datetime, uuid.UUID] | None = None,
) -> AreaPage:
    """The media taken in this part of the map, newest first - what a tapped cluster holds."""
    limit = min(max(limit, 1), MAX_PAGE_SIZE)
    query = select(Media).where(
        shown(),
        text(
            "(media.location && ST_MakeEnvelope(:west, :south, :east, :north, 4326)"
            " OR (media.place_estimated AND media.place_id IN (SELECT id FROM places"
            " WHERE location && ST_MakeEnvelope(:west, :south, :east, :north, 4326))))"
        ).bindparams(west=area.west, south=area.south, east=area.east, north=area.north),
    )
    if cursor is not None:
        taken_at, media_id = cursor
        order = SORT_KEY
        query = query.where((order < taken_at) | ((order == taken_at) & (Media.id < media_id)))
    rows = list(
        await session.scalars(query.order_by(SORT_KEY.desc(), Media.id.desc()).limit(limit + 1))
    )
    return AreaPage(items=rows[:limit], has_next=len(rows) > limit)


# --- the gazetteer: which town a medium was taken in -----------------------------------------

#: A medium further than this from any town is not placed: a photo from the open sea is from
#: nowhere, not from the nearest harbour 200 km away.
PLACE_RADIUS_METRES = 50_000

#: How many media are placed in one go. The clock comes back every minute.
PLACE_BATCH = 2_000


async def load_gazetteer(session: AsyncSession, path: Path) -> int:
    """Fill the places from the prepared file, once. Returns how many were loaded, 0 when the
    table was filled already or the file is missing (a development machine without the image's
    file simply has no places)."""
    if await session.scalar(select(Place.id).limit(1)) is not None:
        return 0
    # Reading 170,000 places takes a few seconds; the event loop keeps going meanwhile.
    records = await asyncio.to_thread(_records, path)
    if not records:
        return 0
    connection = await session.connection()
    raw = await connection.get_raw_connection()
    await raw.driver_connection.copy_records_to_table(  # type: ignore[union-attr]
        "places",
        records=records,
        columns=[
            "id",
            "name",
            "region",
            "country",
            "country_code",
            "population",
            "latitude",
            "longitude",
            "keys",
        ],
    )
    await session.commit()
    return len(records)


async def place_of(session: AsyncSession, media: Media) -> Place | None:
    return await session.get(Place, media.place_id) if media.place_id is not None else None


def _records(path: Path) -> list[tuple[object, ...]]:
    if not path.exists():
        return []
    return [
        (
            place.id,
            place.name,
            place.region,
            place.country,
            place.country_code,
            place.population,
            place.latitude,
            place.longitude,
            list(place.keys),
        )
        for place in gazetteer.read(path)
    ]


_PLACE = text(
    """
    WITH due AS (
        SELECT m.id, m.location FROM media m
         WHERE m.location IS NOT NULL
           AND (m.place_version < :version OR m.placed_for IS DISTINCT FROM m.location
                OR m.place_estimated)
         LIMIT :batch
    ),
    nearest AS (
        SELECT d.id, d.location,
               (SELECT c.id FROM (
                    -- The index finds the nearest by degrees; the true distance decides among
                    -- them, since a degree of longitude shrinks towards the poles.
                    SELECT p.id, p.location FROM places p
                     ORDER BY p.location <-> d.location LIMIT 8
                ) c
                WHERE ST_DistanceSphere(c.location, d.location) <= :radius
                ORDER BY ST_DistanceSphere(c.location, d.location)
                LIMIT 1) AS place_id
          FROM due d
    )
    UPDATE media m
       SET place_id = n.place_id,
           placed_for = n.location,
           place_estimated = false,
           place_version = :version
      FROM nearest n
     WHERE m.id = n.id
    """
)


#: For every album, the place it lends its media without coordinates: its own, or else that of
#: the nearest album above it that has one. Only albums with a place are looked at, and those
#: are few.
_ALBUM_PLACES = """
    SELECT a.id AS album_id,
           (SELECT b.place_id FROM albums b
             WHERE b.place_id IS NOT NULL
               AND (b.id = a.id OR starts_with(a.relative_path, b.relative_path || '/'))
             ORDER BY length(b.relative_path) DESC
             LIMIT 1) AS place_id
      FROM albums a
"""

_ESTIMATE = text(
    f"""
    WITH lent AS ({_ALBUM_PLACES}),
    due AS (
        SELECT m.id, l.place_id FROM media m JOIN lent l ON l.album_id = m.album_id
         WHERE m.location IS NULL
           AND (m.place_id IS DISTINCT FROM l.place_id OR m.placed_for IS NOT NULL
                OR m.place_version < :version
                OR m.place_estimated IS DISTINCT FROM (l.place_id IS NOT NULL))
         LIMIT :batch
    )
    UPDATE media m
       SET place_id = d.place_id,
           placed_for = NULL,
           place_estimated = d.place_id IS NOT NULL,
           place_version = :version
      FROM due d
     WHERE m.id = d.id
    """  # noqa: S608 - a fixed piece of SQL, no values
)


async def place_media(session: AsyncSession, *, batch: int = PLACE_BATCH) -> int:
    """Give the next batch of media the town they were taken in: by their coordinates, or by
    their album's place when they have none. Returns how many changed. Does nothing without
    places."""
    if await session.scalar(select(Place.id).limit(1)) is None:
        return 0
    placed = 0
    for statement in (_PLACE, _ESTIMATE):
        result = await session.execute(
            statement,
            {
                "version": gazetteer.GAZETTEER_VERSION,
                "batch": batch,
                "radius": PLACE_RADIUS_METRES,
            },
        )
        placed += int(getattr(result, "rowcount", 0) or 0)
    await session.commit()
    return placed


async def set_album_place(session: AsyncSession, album: Album, place_id: int | None) -> None:
    """Give an album a place, or take it away, and pass it on to its media straight away."""
    album.place_id = place_id
    await session.commit()
    while await place_media(session):
        pass


async def get_place(session: AsyncSession, place_id: int) -> Place | None:
    return await session.get(Place, place_id)


async def suggest(session: AsyncSession, words: str, *, limit: int = 10) -> list[Place]:
    """Places whose German name begins like this, or that are called exactly this in any
    language ("Firenze"), the larger first - what an album's place is picked from."""
    typed = " ".join(words.split()).lower()
    if not typed:
        return []
    escaped = typed.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    rows = await session.scalars(
        select(Place)
        .where(
            func.lower(Place.name).like(f"{escaped}%", escape="\\") | Place.keys.contains([typed])
        )
        .order_by(Place.population.desc(), Place.id)
        .limit(limit)
    )
    return list(rows)


# --- places in a search ----------------------------------------------------------------------

#: A place is at most this many words: "San Gimignano", "Bad Tölz", "Sankt Peter Ording".
_MAX_PLACE_WORDS = 3
_WORD = re.compile(r"[^\W\d_](?:[\w'.-]*\w)?", re.UNICODE)
_BEFORE_PLACE = re.compile(r"\b(?:in|aus|bei|von|nach)\s*$", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class PlacesInQuery:
    #: What is left once the places are taken out.
    text: str
    #: The places as they were typed, for the chip.
    phrases: tuple[str, ...]
    #: The keys to filter by: a medium counts when its place carries one of them.
    keys: tuple[str, ...]


async def places_in(session: AsyncSession, words: str) -> PlacesInQuery:
    """Take the names of places out of a search - only places the library has photos from.

    "Hund Toskana" becomes a search for "Hund" among the photos from Tuscany. A word that is
    also a place somewhere in the world ("Essen") only counts when there are photos from there.
    """
    matches = list(_WORD.finditer(words))
    candidates: dict[str, list[tuple[int, int]]] = {}
    for size in range(_MAX_PLACE_WORDS, 0, -1):
        for first in range(len(matches) - size + 1):
            phrase = " ".join(match.group() for match in matches[first : first + size]).lower()
            candidates.setdefault(phrase, []).append((first, first + size))
    if not candidates:
        return PlacesInQuery(text=words, phrases=(), keys=())

    found = set(
        await session.scalars(
            text(
                """
                SELECT DISTINCT k FROM places p, unnest(p.keys) k
                 WHERE p.keys && CAST(:candidates AS text[])
                   AND k = ANY(CAST(:candidates AS text[]))
                   AND p.id IN (SELECT DISTINCT place_id FROM media
                                 WHERE status = :active AND duplicate_of IS NULL
                                   AND place_id IS NOT NULL)
                """
            ),
            {"candidates": list(candidates), "active": MediaStatus.ACTIVE.value},
        )
    )
    if not found:
        return PlacesInQuery(text=words, phrases=(), keys=())

    # Longest first, so "Bad Tölz" is taken whole before "Bad" could be.
    taken: list[tuple[int, int]] = []
    keys: list[str] = []
    for phrase, spans in sorted(candidates.items(), key=lambda item: -len(item[0].split())):
        if phrase not in found:
            continue
        for start, end in spans:
            if all(end <= other_start or start >= other_end for other_start, other_end in taken):
                taken.append((start, end))
                if phrase not in keys:
                    keys.append(phrase)
    taken.sort()

    rest = ""
    position = 0
    phrases = []
    for start, end in taken:
        before = _BEFORE_PLACE.sub("", words[position : matches[start].start()])
        rest += before
        phrases.append(words[matches[start].start() : matches[end - 1].end()])
        position = matches[end - 1].end()
    rest += words[position:]
    return PlacesInQuery(text=" ".join(rest.split()), phrases=tuple(phrases), keys=tuple(keys))
