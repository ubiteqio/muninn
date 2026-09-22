"""Media: reading one medium, and the derivatives that make it fast to look at."""

import asyncio
import shutil
import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from pathlib import Path

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.exc import StaleDataError

from muninn.huginn.derive import DERIVE_VERSION, Derivatives, DeriveError, derive
from muninn.models.media import Media, MediaKind, MediaStatus, shown
from muninn.models.settings import AppSettings


class MediaNotFoundError(Exception):
    pass


async def get_media(session: AsyncSession, media_id: uuid.UUID) -> Media:
    """One medium. A missing medium is still readable; it is only invisible in the lists."""
    media = await session.get(Media, media_id)
    if media is None:
        raise MediaNotFoundError
    return media


# --- the timeline -------------------------------------------------------------

DEFAULT_PAGE_SIZE = 100
MAX_PAGE_SIZE = 500

#: Media are placed by when they were taken; until stage 2 has read a date, by when they were
#: found. The same key the albums use, so a medium sits in the same order in both.
SORT_KEY: ColumnElement[datetime] = func.coalesce(Media.taken_at, Media.created_at)


@dataclass(frozen=True, slots=True)
class TimelinePage:
    """One window of the timeline and whether there is more on either side of it."""

    items: list[Media]
    has_next: bool
    has_previous: bool


class Granularity(StrEnum):
    """How finely the timeline is cut. The same word PostgreSQL uses for it."""

    YEAR = "year"
    MONTH = "month"
    DAY = "day"


@dataclass(frozen=True, slots=True)
class Mark:
    """One slice of the timeline: the day it begins on and how much it holds."""

    start: date
    count: int


@dataclass(frozen=True, slots=True)
class TimelineShape:
    """What the timeline looks like, without reading a single medium.

    A few hundred rows describe a library of any size: the years and months of the overview are
    built from them, and the app knows how tall a level is before it has loaded any of it.
    """

    by: Granularity
    total: int
    marks: list[Mark]


@dataclass(frozen=True, slots=True)
class Period:
    """One year or month of the overview: how much it holds, and a few pictures from it."""

    start: date
    count: int
    covers: list[uuid.UUID]


async def list_timeline(
    session: AsyncSession,
    *,
    limit: int = DEFAULT_PAGE_SIZE,
    cursor: tuple[datetime, uuid.UUID] | None = None,
    before: tuple[datetime, uuid.UUID] | None = None,
    at: datetime | None = None,
    month: date | None = None,
) -> TimelinePage:
    """Media newest first, one window at a time.

    ``month`` keeps the walk inside one month, which is how the app browses: somebody who chose
    August 2014 wants August 2014, not everything that ever happened before it. Without it the
    walk runs through the whole library.

    ``cursor`` walks on into the past, ``before`` back towards today, and ``at`` starts at the
    newest medium not newer than that moment.
    """
    limit = min(max(limit, 1), MAX_PAGE_SIZE)
    order = SORT_KEY
    query = select(Media).where(shown())
    if month is not None:
        query = query.where(func.date_trunc("month", SORT_KEY) == month.replace(day=1))

    if before is not None:
        taken_at, media_id = before
        # Towards today means reading away from the window, so the rows arrive the wrong way
        # round and are turned back at the end.
        rows = list(
            await session.scalars(
                query.where((order > taken_at) | ((order == taken_at) & (Media.id > media_id)))
                .order_by(order, Media.id)
                .limit(limit + 1)
            )
        )
        return TimelinePage(
            items=list(reversed(rows[:limit])),
            has_next=True,
            has_previous=len(rows) > limit,
        )

    has_previous = False
    if cursor is not None:
        taken_at, media_id = cursor
        query = query.where((order < taken_at) | ((order == taken_at) & (Media.id < media_id)))
        has_previous = True
    elif at is not None:
        query = query.where(order <= at)
        # A jump lands in the middle of the timeline, so there is something above it - unless
        # nothing was taken after that moment.
        above = select(Media.id).where(shown(), order > at)
        if month is not None:
            above = above.where(func.date_trunc("month", SORT_KEY) == month.replace(day=1))
        newer = await session.scalar(above.limit(1))
        has_previous = newer is not None

    rows = list(
        await session.scalars(query.order_by(order.desc(), Media.id.desc()).limit(limit + 1))
    )
    return TimelinePage(items=rows[:limit], has_next=len(rows) > limit, has_previous=has_previous)


async def timeline_shape(
    session: AsyncSession, *, by: Granularity = Granularity.MONTH, year: int | None = None
) -> TimelineShape:
    """Counts per year, month or day, newest first. One aggregate, whatever the library holds.

    Days are only ever asked for one year at a time: a library of 26 years has some nine
    thousand of them, and a level only ever needs the year it is standing in.
    """
    slice_start = func.date_trunc(by.value, SORT_KEY)
    query = (
        select(slice_start.label("start"), func.count())
        .where(shown())
        .group_by(slice_start)
        .order_by(slice_start.desc())
    )
    if year is not None:
        query = query.where(func.extract("year", SORT_KEY) == year)

    rows = await session.execute(query)
    marks = [Mark(start=row[0].date(), count=int(row[1])) for row in rows]
    return TimelineShape(by=by, total=sum(mark.count for mark in marks), marks=marks)


async def list_periods(
    session: AsyncSession,
    *,
    by: Granularity = Granularity.YEAR,
    year: int | None = None,
    covers: int = 4,
) -> list[Period]:
    """The years or months of the overview, newest first, each with a few pictures from it.

    Two queries for the whole overview, however many periods there are: one counts, the other
    ranks the media inside every period at once and keeps the first few. A query per period would
    be a hundred round trips for a library of a few years.
    """
    shape = await timeline_shape(session, by=by, year=year)
    if not shape.marks:
        return []

    slice_start = func.date_trunc(by.value, SORT_KEY)
    rank = func.row_number().over(
        partition_by=slice_start, order_by=(SORT_KEY.desc(), Media.id.desc())
    )
    ranked = (
        select(Media.id.label("id"), slice_start.label("start"), rank.label("rank"))
        .where(shown(), Media.thumbnail_path.is_not(None))
        .subquery()
    )
    query = select(ranked.c.start, ranked.c.id).where(ranked.c.rank <= covers)
    if year is not None:
        query = query.where(func.extract("year", ranked.c.start) == year)

    chosen: dict[date, list[uuid.UUID]] = {}
    for row in await session.execute(query.order_by(ranked.c.start.desc(), ranked.c.rank)):
        chosen.setdefault(row[0].date(), []).append(row[1])

    return [
        Period(start=mark.start, count=mark.count, covers=chosen.get(mark.start, []))
        for mark in shape.marks
    ]


def cursor_value(media: Media) -> datetime:
    return media.taken_at or media.created_at


# --- derivatives --------------------------------------------------------------


def folder_of(derived_root: Path, media_id: uuid.UUID) -> Path:
    """Where a medium's derivatives live. Two levels, so no folder holds 150.000 entries."""
    key = media_id.hex
    return derived_root / key[:2] / key


def relative_of(media_id: uuid.UUID, name: str) -> str:
    key = media_id.hex
    return f"{key[:2]}/{key}/{name}"


def _size_of(folder: Path, names: list[str | None]) -> int:
    """How much room the files just written take together."""
    return sum((folder / name).stat().st_size for name in names if name)


async def apply_derivatives(
    session: AsyncSession,
    media_id: uuid.UUID,
    *,
    library_base: Path,
    derived_root: Path,
    settings: AppSettings,
) -> bool:
    """Stage 3 for one medium: thumbnail, preview, a playable video, and the pixel hash.

    Idempotent: a medium whose derivatives match its content and the current stage version is
    left alone. New files are written under a new name and the old ones are only removed once the
    database points at the new ones, so nobody ever sees half a picture.
    """
    media = await session.get(Media, media_id)
    if media is None or media.status is not MediaStatus.ACTIVE:
        return False

    source = library_base / media.primary_file.relative_path
    if not await asyncio.to_thread(source.exists):
        return False

    stem = media.content_hash[:12]
    if media.derive_version == DERIVE_VERSION and media.thumbnail_path == relative_of(
        media_id, f"thumb-{stem}.webp"
    ):
        return True

    folder = folder_of(derived_root, media_id)
    try:
        made: Derivatives = await asyncio.to_thread(
            derive,
            source,
            folder,
            kind=media.kind,
            stem=stem,
            thumbnail_size=settings.thumbnail_size,
            preview_size=settings.preview_size,
            quality=settings.image_quality,
            video_height=settings.video_height,
        )
    except DeriveError:
        # A broken or unreadable original is not worth a failed task: the medium stays in the
        # library without previews, and the admin sees it in the index status.
        return False

    previous = [
        path
        for path in (media.thumbnail_path, media.preview_path, media.video_path, media.poster_path)
        if path is not None
    ]

    media.thumbnail_path = relative_of(media_id, made.thumbnail)
    # A new thumbnail is a new picture to fingerprint (muninn.duplicates).
    media.fingerprint_version = 0
    media.preview_path = relative_of(media_id, made.preview) if made.preview else None
    media.video_path = relative_of(media_id, made.video) if made.video else None
    media.poster_path = relative_of(media_id, made.poster) if made.poster else None
    media.pixel_hash = made.pixel_hash
    media.derived_bytes = await asyncio.to_thread(
        _size_of, folder, [made.thumbnail, made.preview, made.video, made.poster]
    )
    media.derive_version = DERIVE_VERSION
    if made.width is not None:
        # The decoded picture beats the tag: this is the size everything that shows it needs.
        media.width = made.width
        media.height = made.height

    try:
        await session.commit()
    except StaleDataError:
        # The medium was removed while its previews were being made - somebody took the folder
        # out of the albums. The files just written are cleaned up with the rest of its folder.
        await session.rollback()
        return False

    # Only now, with the database pointing at the new files, may the old ones go.
    keep = {media.thumbnail_path, media.preview_path, media.video_path, media.poster_path}
    await asyncio.to_thread(
        _remove_files, derived_root, [path for path in previous if path not in keep]
    )
    return True


async def remove_derivatives(derived_root: Path, media_ids: Sequence[uuid.UUID]) -> int:
    """Everything derived from these media, gone. Called once an original is really gone."""
    return await asyncio.to_thread(_remove_folders, derived_root, media_ids)


#: How long a folder has to lie around before it counts as forgotten. A derivation that is
#: being written right now must never be swept away under the worker's hands.
ORPHAN_AGE_SECONDS = 3600


async def remove_orphans(
    session: AsyncSession,
    derived_root: Path,
    *,
    dry_run: bool = False,
    min_age_seconds: int = ORPHAN_AGE_SECONDS,
    allow_empty: bool = False,
) -> list[uuid.UUID]:
    """Previews that belong to no medium any more, and what would be removed in a dry run.

    Derivatives go with their medium wherever Muninn removes one, but a crash mid-derivation, a
    database restored from a backup or a version that did not clean up yet all leave folders
    behind. Nothing reads them, and nothing would ever remove them either.

    Two things it refuses to do, in the spirit of the scanner's safety net: touch anything
    younger than ``min_age_seconds``, and sweep at all while the media table is empty - which is
    what a database that cannot answer looks like from here.
    """
    known = {
        media_id.hex
        for media_id in (await session.scalars(select(Media.id).where(Media.id.is_not(None))))
    }
    if not known and not allow_empty:
        return []

    return await asyncio.to_thread(
        _orphans, derived_root, known, dry_run=dry_run, min_age_seconds=min_age_seconds
    )


def _orphans(
    derived_root: Path, known: set[str], *, dry_run: bool, min_age_seconds: int
) -> list[uuid.UUID]:
    if not derived_root.is_dir():
        return []

    cutoff = time.time() - min_age_seconds
    found: list[uuid.UUID] = []

    for shard in sorted(derived_root.iterdir()):
        if not shard.is_dir():
            continue
        for folder in sorted(shard.iterdir()):
            if not folder.is_dir() or folder.name in known:
                continue
            try:
                media_id = uuid.UUID(hex=folder.name)
            except ValueError:
                # Not something Muninn wrote, so not something Muninn removes.
                continue
            if folder.stat().st_mtime > cutoff:
                continue

            found.append(media_id)
            if not dry_run:
                shutil.rmtree(folder, ignore_errors=True)

        # A shard left empty by this is noise of its own.
        if not dry_run and not any(shard.iterdir()):
            shard.rmdir()

    return found


def _remove_files(derived_root: Path, relative_paths: Sequence[str]) -> None:
    for relative_path in relative_paths:
        (derived_root / relative_path).unlink(missing_ok=True)


def _remove_folders(derived_root: Path, media_ids: Sequence[uuid.UUID]) -> int:
    removed = 0
    for media_id in media_ids:
        folder = folder_of(derived_root, media_id)
        if folder.exists():
            shutil.rmtree(folder, ignore_errors=True)
            removed += 1
    return removed


@dataclass(frozen=True, slots=True)
class MediaLabel:
    """Enough about a medium to name it and to lead to it."""

    filename: str
    kind: MediaKind
    album_id: uuid.UUID
    album_path: str


async def labels_of(
    session: AsyncSession, media_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, MediaLabel]:
    """What these media are called, what they are and where they lie - for the engine room."""
    if not media_ids:
        return {}

    rows = await session.scalars(
        select(Media)
        .where(Media.id.in_(media_ids))
        .options(selectinload(Media.files), selectinload(Media.album))
    )
    return {
        media.id: MediaLabel(
            filename=media.primary_file.filename,
            kind=media.kind,
            album_id=media.album_id,
            album_path=media.album.relative_path,
        )
        for media in rows
        if media.files
    }


async def filenames_of(
    session: AsyncSession, media_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, str]:
    """What these media are called, for saying out loud which one is being worked on."""
    if not media_ids:
        return {}

    rows = await session.scalars(select(Media).where(Media.id.in_(media_ids)))
    return {media.id: media.primary_file.filename for media in rows if media.files}
