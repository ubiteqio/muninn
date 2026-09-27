"""Making, keeping and handing out photo books.

The pages are built here and stored; everything the app later needs is in them. Two things are
deliberately not: the addresses of the pictures, which are signed when a book is read, and the
facts each page was written from, which are the analyzer's raw sentences and have no business in
a finished book.

Building a book is two halves. The first needs nothing but the database - which pictures, in
what order, on which kind of page - and always succeeds. The second asks the machine for the
prose, and may find nobody there; then the book is finished all the same, with its plain facts,
and can be asked for its words later.
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from muninn.ai import service as ai_service
from muninn.ai.base import AiError
from muninn.models.ai import AiKind
from muninn.models.album import Album
from muninn.models.analysis import MediaAnalysis
from muninn.models.face import Face, Person
from muninn.models.media import DateSource, Media, MediaKind, shown
from muninn.models.photobook import (
    DEFAULT_MAX_MEDIA,
    PHOTOBOOK_VERSION,
    SIZE_MEDIUM,
    STATE_FAILED,
    STATE_READY,
    STYLE_SCRAPBOOK,
    Photobook,
    PhotobookAlbum,
)
from muninn.models.place import Place
from muninn.photobooks import pages as layout
from muninn.photobooks import words
from muninn.photobooks.selection import Shot, chosen

#: More than this in one call would tie up the worker for an hour.
MOST_AT_ONCE = 20


async def create(
    session: AsyncSession,
    *,
    albums: Sequence[Album],
    size: str = SIZE_MEDIUM,
    max_media: int = DEFAULT_MAX_MEDIA,
    style: str = STYLE_SCRAPBOOK,
    title: str = "",
    count: int = 1,
) -> list[Photobook]:
    """Puts ``count`` books of these folders on the shelf, still empty, and hands them back.

    Several folders make one book: a holiday split into days, a year kept month by month. The
    first is where the book hangs in the tree; the rest only bring their pictures.

    Each book gets its own seed, so the second book of the same folders draws other pictures and
    finds other words. The pages come later, in the worker: a book of 4500 pictures is not built
    while an admin waits for the page to answer.
    """
    if not albums:
        raise ValueError("Ein Buch braucht mindestens einen Ordner.")

    home = albums[0]
    made: list[Photobook] = []
    for number in range(max(1, min(count, MOST_AT_ONCE))):
        book = Photobook(
            album_id=home.id,
            title=title or await _named(session, albums),
            style=style,
            size=size,
            max_media=max(1, max_media),
            seed=int(uuid.uuid4().int % 1_000_000),
            version=PHOTOBOOK_VERSION,
        )
        if count > 1:
            book.title = f"{book.title} {_volume(number)}"
        session.add(book)
        made.append(book)
    await session.flush()
    for book in made:
        session.add_all(PhotobookAlbum(photobook_id=book.id, album_id=album.id) for album in albums)
    await session.flush()
    return made


async def _named(session: AsyncSession, albums: Sequence[Album]) -> str:
    """What a book of several folders is called before an admin says otherwise.

    One folder lends its own name. Several that live in the same folder lend that folder's name
    - "2014 Italien" rather than "Tag 1 · Tag 2" - and folders from all over the tree are named
    after the first two of them.
    """
    if len(albums) == 1:
        return albums[0].display_title

    parents = {album.parent_id for album in albums}
    if len(parents) == 1:
        above = parents.pop()
        parent = await session.get(Album, above) if above is not None else None
        if parent is not None:
            return parent.display_title

    return " · ".join(album.display_title for album in albums[:2]) + (
        f" +{len(albums) - 2}" if len(albums) > 2 else ""
    )


async def albums_of(session: AsyncSession, book: Photobook) -> list[uuid.UUID]:
    """The folders a book draws from. A book from before they were several has only its own."""
    rows = await session.scalars(
        select(PhotobookAlbum.album_id).where(PhotobookAlbum.photobook_id == book.id)
    )
    found = list(rows)
    return found or [book.album_id]


def _volume(number: int) -> str:
    """Several books of one album are told apart by a number, not by their dates."""
    return ("I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X")[number % 10]


async def get(session: AsyncSession, book_id: uuid.UUID) -> Photobook | None:
    return await session.get(Photobook, book_id)


async def listed(session: AsyncSession, *, album_id: uuid.UUID | None = None) -> list[Photobook]:
    """Every book, newest first. The pages are not read here - a list shows covers."""
    query = select(Photobook).order_by(Photobook.created_at.desc())
    if album_id is not None:
        query = query.where(Photobook.album_id == album_id)
    return list((await session.scalars(query)).all())


async def album_titles(
    session: AsyncSession, album_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, str]:
    """What the albums of these books are called, for the shelf."""
    if not album_ids:
        return {}
    albums = await session.scalars(select(Album).where(Album.id.in_(set(album_ids))))
    return {album.id: album.display_title for album in albums}


async def remove(session: AsyncSession, book: Photobook) -> None:
    await session.execute(delete(Photobook).where(Photobook.id == book.id))


async def shots_of(session: AsyncSession, album_ids: Sequence[uuid.UUID]) -> list[Shot]:
    """Everything these folders show, with all a book may know about it, oldest first."""
    confirmed = (
        select(Face.media_id, func.array_agg(func.distinct(Person.name)).label("names"))
        .join(Person, Person.id == Face.person_id)
        .where(Person.hidden.is_(False))
        .group_by(Face.media_id)
        .subquery()
    )
    suspected = (
        select(Face.media_id, func.array_agg(func.distinct(Person.name)).label("names"))
        .join(Person, Person.id == Face.suggested_person_id)
        .where(Person.hidden.is_(False), Face.person_id.is_(None))
        .group_by(Face.media_id)
        .subquery()
    )
    rows = await session.execute(
        select(Media, MediaAnalysis, Place, confirmed.c.names, suspected.c.names)
        .outerjoin(MediaAnalysis, MediaAnalysis.media_id == Media.id)
        .outerjoin(Place, Place.id == Media.place_id)
        .outerjoin(confirmed, confirmed.c.media_id == Media.id)
        .outerjoin(suspected, suspected.c.media_id == Media.id)
        .where(Media.album_id.in_(list(album_ids)), shown(), Media.taken_at.is_not(None))
        .order_by(Media.taken_at, Media.id)
    )
    return [
        _shot_of(medium, analysis, place, names or [], hints or [])
        for medium, analysis, place, names, hints in rows.all()
    ]


def _shot_of(
    medium: Media,
    analysis: MediaAnalysis | None,
    place: Place | None,
    names: Sequence[str],
    hints: Sequence[str],
) -> Shot:
    return Shot(
        id=str(medium.id),
        taken_at=medium.taken_at or datetime.now(UTC),
        guessed=medium.taken_at_source == DateSource.FOLDER_NAME,
        kind=MediaKind.VIDEO.value if medium.kind == MediaKind.VIDEO else MediaKind.IMAGE.value,
        width=medium.width or 0,
        height=medium.height or 0,
        has_preview=bool(medium.preview_path),
        latitude=medium.latitude,
        longitude=medium.longitude,
        place=place.name if place else "",
        region=(place.region or "") if place else "",
        country=(place.country or "") if place else "",
        population=place.population if place else None,
        caption=(analysis.caption or "") if analysis else "",
        scene=(analysis.scene or "") if analysis else "",
        ocr=(analysis.ocr_text or "") if analysis else "",
        people=(analysis.people_count or 0) if analysis else 0,
        tags=tuple(analysis.tags or ()) if analysis else (),
        persons=tuple(sorted(names)),
        suggested=tuple(sorted(set(hints) - set(names))),
        fingerprint=medium.fingerprint,
    )


async def build(session: AsyncSession, book: Photobook) -> Photobook:
    """Builds the pages of one book, and asks the machine for its words if there is one."""
    album = await session.get(Album, book.album_id)
    if album is None:  # pragma: no cover - the foreign key removes the book with the album
        raise ValueError("Zu diesem Buch gibt es kein Album mehr.")

    everything = await shots_of(session, await albums_of(session, book))
    picked = chosen(everything, size=book.size, ceiling=book.max_media, seed=book.seed)
    if not picked:
        book.state = STATE_FAILED
        book.trouble = "In diesem Album ist keine Aufnahme mit Datum, aus der ein Buch würde."
        book.built_at = datetime.now(UTC)
        return book

    built = layout.pages_of(picked, title=book.title)
    book.written = await _write(session, built)
    _tidy(built)

    book.pages = built
    book.page_count = len(built)
    book.media_count = len(picked)
    book.cover_media_id = uuid.UUID(_cover(built, picked))
    book.from_at = picked[0].taken_at
    book.until_at = picked[-1].taken_at
    book.subtitle = str(built[0].get("subtitle", "")) if built else ""
    book.state = STATE_READY
    book.version = PHOTOBOOK_VERSION
    book.built_at = datetime.now(UTC)
    return book


async def _write(session: AsyncSession, built: list[dict[str, Any]]) -> bool:
    """The prose, if a machine answers. A book without it is whole, only plainer."""
    profile = await ai_service.active_profile(session, AiKind.ANALYZER)
    if profile is None:
        return False
    try:
        await words.write_pages(
            ai_service.writer_for(profile), built, at_once=max(1, profile.concurrency)
        )
    except AiError:
        return False
    return True


def _tidy(built: list[dict[str, Any]]) -> None:
    """Strips what only the writing needed. The analyzer's sentences do not travel."""
    for page in built:
        page.pop("facts", None)
        page.pop("_pictures", None)


def _cover(built: Sequence[dict[str, Any]], picked: Sequence[Shot]) -> str:
    """The picture on the cover: the one the opening page opens with."""
    opening = built[0] if built else {}
    hero = opening.get("hero")
    if isinstance(hero, dict) and isinstance(hero.get("id"), str):
        return str(hero["id"])
    return picked[0].id
