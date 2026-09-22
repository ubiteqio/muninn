"""Rückblicke: "Heute vor X Jahren".

For a day, every earlier year with photos from the same calendar day becomes one memory. When
no year has any, the week around the day is taken instead. Only photos whose date can be relied
on (from the camera, GPS or the file name - not a folder name or a file time), no screenshots or
documents, and of every group of copies only the best. Named people, likes and stars come
first; at most twelve per year, shown in the order they were taken.

The choice is made once per day - by the clock at 06:00, or by whoever asks first - and kept, so
the cards do not change while the day goes on.
"""

import hashlib
import os
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import delete, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from muninn.models.album import Album
from muninn.models.media import Media
from muninn.models.memory import Memory, MemoryMedium

#: At most this many photos per year.
PER_YEAR = 12

#: When the day itself has nothing: this many days before and after it.
WEEK_REACH = 3

#: How long chosen memories are kept. Only today's are shown; the rest is for a later look back.
KEEP_DAYS = 14

_CANDIDATES = text(
    """
    WITH candidates AS (
        SELECT m.id, m.album_id, m.taken_at,
               extract(year FROM m.taken_at AT TIME ZONE :zone)::int AS year,
               -- Somebody the family named counts most, anybody at all a little.
               (CASE WHEN EXISTS (SELECT 1 FROM faces f JOIN persons p ON p.id = f.person_id
                                   WHERE f.media_id = m.id AND NOT p.hidden) THEN 4
                     WHEN coalesce(a.people_count, 0) > 0 THEN 2 ELSE 0 END)
               + (SELECT count(*) FROM likes l WHERE l.media_id = m.id)
               + 2 * (SELECT count(*) FROM favorites f WHERE f.media_id = m.id) AS score
          FROM media m
          LEFT JOIN media_analyses a ON a.media_id = m.id
         WHERE m.status = 'active' AND m.duplicate_of IS NULL AND m.kind = 'image'
           AND m.taken_at_source IN ('exif', 'gps', 'filename')
           AND NOT coalesce(a.is_screenshot, false) AND NOT coalesce(a.is_document, false)
           AND to_char(m.taken_at AT TIME ZONE :zone, 'MM-DD') = ANY(CAST(:days AS text[]))
           AND extract(year FROM m.taken_at AT TIME ZONE :zone) < :this_year
           -- Of a group of copies nobody decided on yet, only the best.
           AND NOT EXISTS (SELECT 1 FROM duplicate_members d
                            WHERE d.media_id = m.id AND NOT d.best)
    )
    SELECT id, album_id, taken_at, year, score FROM candidates
    """
)


def local_zone() -> str:
    """The zone the family lives in, from TZ in deploy/.env: a day starts at their midnight."""
    return os.environ.get("TZ") or "UTC"


def _calendar_days(day: date, reach: int) -> list[str]:
    return [(day + timedelta(days=offset)).strftime("%m-%d") for offset in range(-reach, reach + 1)]


def _shuffle_key(media_id: uuid.UUID, day: date) -> str:
    """Among equal scores, a different order every day - but the same one all day."""
    return hashlib.blake2s(f"{media_id}{day}".encode(), digest_size=8).hexdigest()


type Chosen = dict[uuid.UUID, list[uuid.UUID]]


async def _choose(session: AsyncSession, day: date) -> tuple[list[Memory], Chosen]:
    zone = local_zone()
    from_week = False
    rows = list(
        await session.execute(
            _CANDIDATES,
            {"zone": zone, "days": _calendar_days(day, 0), "this_year": day.year},
        )
    )
    if not rows:
        from_week = True
        rows = list(
            await session.execute(
                _CANDIDATES,
                {"zone": zone, "days": _calendar_days(day, WEEK_REACH), "this_year": day.year},
            )
        )

    by_year: dict[int, list[tuple[uuid.UUID, uuid.UUID, object, int]]] = defaultdict(list)
    for row in rows:
        by_year[row.year].append((row.id, row.album_id, row.taken_at, row.score))

    memories: list[Memory] = []
    chosen: Chosen = {}
    for year in sorted(by_year, reverse=True):
        best = sorted(by_year[year], key=lambda item: (-item[3], _shuffle_key(item[0], day)))
        picked = sorted(best[:PER_YEAR], key=lambda item: (str(item[2]), str(item[0])))
        album = Counter(item[1] for item in picked).most_common(1)[0][0]
        memory = Memory(id=uuid.uuid4(), day=day, year=year, from_week=from_week, album_id=album)
        memories.append(memory)
        chosen[memory.id] = [item[0] for item in picked]
    return memories, chosen


async def prepare(session: AsyncSession, day: date) -> int:
    """Choose the memories of a day, once. Returns how many there are."""
    existing = await session.scalar(select(Memory.id).where(Memory.day == day).limit(1))
    if existing is not None:
        return len(list(await session.scalars(select(Memory.id).where(Memory.day == day))))

    memories, chosen = await _choose(session, day)
    try:
        for memory in memories:
            session.add(memory)
            await session.flush()
            await session.execute(
                insert(MemoryMedium),
                [
                    {"memory_id": memory.id, "media_id": media_id, "position": position}
                    for position, media_id in enumerate(chosen[memory.id])
                ],
            )
        await session.execute(delete(Memory).where(Memory.day < day - timedelta(days=KEEP_DAYS)))
        await session.commit()
    except IntegrityError:
        # The clock and a first visitor chose at the same moment; the other one's choice stays.
        await session.rollback()
    return len(memories)


@dataclass(frozen=True, slots=True)
class DayMemory:
    memory: Memory
    album: Album | None
    media: list[Media]


async def of_day(session: AsyncSession, day: date) -> list[DayMemory]:
    """The memories of a day, the most recent year first. Chosen now if nobody did yet.

    Media hidden since the choice was made are left out; a memory left with none is too.
    """
    await prepare(session, day)
    memories = list(
        await session.scalars(select(Memory).where(Memory.day == day).order_by(Memory.year.desc()))
    )
    if not memories:
        return []
    rows = await session.execute(
        select(MemoryMedium.memory_id, Media)
        .join(Media, Media.id == MemoryMedium.media_id)
        .where(
            MemoryMedium.memory_id.in_([memory.id for memory in memories]),
            Media.status == "active",
            Media.duplicate_of.is_(None),
        )
        .order_by(MemoryMedium.memory_id, MemoryMedium.position)
        .options(selectinload(Media.files))
    )
    media: dict[uuid.UUID, list[Media]] = defaultdict(list)
    for memory_id, medium in rows:
        media[memory_id].append(medium)
    albums = {
        album.id: album
        for album in await session.scalars(
            select(Album).where(
                Album.id.in_([memory.album_id for memory in memories if memory.album_id])
            )
        )
    }
    return [
        DayMemory(
            memory=memory,
            album=albums.get(memory.album_id) if memory.album_id else None,
            media=media[memory.id],
        )
        for memory in memories
        if media[memory.id]
    ]
