"""Reading the album tree and the media of an album."""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from muninn.models.album import Album
from muninn.models.media import Media, shown

DEFAULT_PAGE_SIZE = 100
MAX_PAGE_SIZE = 500


class AlbumNotFoundError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class AlbumNode:
    """One album plus what a view of the tree needs: two numbers and a cover."""

    album: Album
    media_count: int
    child_count: int
    #: What the tile shows: the album's own newest thumbnail, or up to four from the albums
    #: below it. A folder that only holds folders has pictures too, just one level down.
    cover_media_ids: tuple[uuid.UUID, ...] = ()


#: Media are ordered by when they were taken; until stage 2 has run, by when they were found.
SORT_KEY: ColumnElement[datetime] = func.coalesce(Media.taken_at, Media.created_at)


async def list_tree(session: AsyncSession) -> list[AlbumNode]:
    """The whole tree in one go: it is a few thousand rows at most, and the app needs all of it."""
    albums = list(await session.scalars(select(Album).order_by(Album.relative_path)))

    media_rows = await session.execute(
        select(Media.album_id, func.count()).where(shown()).group_by(Media.album_id)
    )
    media_counts: dict[uuid.UUID, int] = {row[0]: int(row[1]) for row in media_rows}

    child_rows = await session.execute(
        select(Album.parent_id, func.count())
        .where(Album.parent_id.is_not(None))
        .group_by(Album.parent_id)
    )
    child_counts: dict[uuid.UUID, int] = {
        row[0]: int(row[1]) for row in child_rows if row[0] is not None
    }

    covers = await _covers(session)
    # The albums arrive sorted by path, so the children of an album are in the order the app
    # shows them, and a collage is put together from the first subalbums, not from random ones.
    children: dict[uuid.UUID | None, list[Album]] = {}
    for album in albums:
        children.setdefault(album.parent_id, []).append(album)

    return [
        AlbumNode(
            album=album,
            media_count=media_counts.get(album.id, 0),
            child_count=child_counts.get(album.id, 0),
            cover_media_ids=_collage(album, covers, children),
        )
        for album in albums
    ]


#: How many thumbnails a tile can hold. Four fill a square; a fifth would only make them smaller.
COLLAGE_SIZE = 4


def _collage(
    album: Album,
    covers: dict[uuid.UUID, uuid.UUID],
    children: dict[uuid.UUID | None, list[Album]],
) -> tuple[uuid.UUID, ...]:
    """The album's own cover, or the first few from the albums below it.

    An album with pictures of its own speaks for itself. One that only holds folders would show
    an empty box, so it borrows: breadth first, so the collage comes from the albums right below
    it before it reaches into their children.
    """
    own = covers.get(album.id)
    if own is not None:
        return (own,)

    found: list[uuid.UUID] = []
    queue = list(children.get(album.id, []))
    while queue and len(found) < COLLAGE_SIZE:
        current = queue.pop(0)
        cover = covers.get(current.id)
        if cover is not None:
            found.append(cover)
        queue.extend(children.get(current.id, []))

    return tuple(found)


async def _covers(
    session: AsyncSession, album_id: uuid.UUID | None = None
) -> dict[uuid.UUID, uuid.UUID]:
    """One cover per album: the newest medium that already has a thumbnail."""
    query = (
        select(Media.album_id, Media.id)
        .distinct(Media.album_id)
        .where(shown(), Media.thumbnail_path.is_not(None))
        .order_by(Media.album_id, SORT_KEY.desc(), Media.id)
    )
    if album_id is not None:
        query = query.where(Media.album_id == album_id)

    rows = await session.execute(query)
    return {row[0]: row[1] for row in rows}


async def get_album(session: AsyncSession, album_id: uuid.UUID) -> AlbumNode:
    album = await session.get(Album, album_id)
    if album is None:
        raise AlbumNotFoundError

    media_count = await session.scalar(
        select(func.count()).select_from(Media).where(Media.album_id == album.id, shown())
    )
    child_count = await session.scalar(
        select(func.count()).select_from(Album).where(Album.parent_id == album.id)
    )
    own = await _covers(session, album.id)
    cover_ids: tuple[uuid.UUID, ...]
    if own:
        cover_ids = (own[album.id],)
    else:
        # Only an album without pictures of its own needs to look below itself, and only then is
        # reading the tree worth it.
        albums = list(await session.scalars(select(Album).order_by(Album.relative_path)))
        children: dict[uuid.UUID | None, list[Album]] = {}
        for entry in albums:
            children.setdefault(entry.parent_id, []).append(entry)
        cover_ids = _collage(album, await _covers(session), children)

    return AlbumNode(
        album=album,
        media_count=int(media_count or 0),
        child_count=int(child_count or 0),
        cover_media_ids=cover_ids,
    )


async def update_album(
    session: AsyncSession,
    *,
    album: Album,
    title: str | None = None,
    description: str | None = None,
) -> Album:
    """Title and description live in Muninn. The folder on the NAS is never touched."""
    if title is not None:
        album.title = title or None
    if description is not None:
        album.description = description or None
    await session.commit()
    await session.refresh(album)
    return album


@dataclass(frozen=True, slots=True)
class MediaPage:
    """One page of an album and whether there is anything on either side of it."""

    items: list[Media]
    has_next: bool
    has_previous: bool


async def list_media(
    session: AsyncSession,
    *,
    album: Album,
    limit: int = DEFAULT_PAGE_SIZE,
    cursor: tuple[datetime, uuid.UUID] | None = None,
    before: tuple[datetime, uuid.UUID] | None = None,
) -> MediaPage:
    """Oldest first, the way a folder of holiday pictures is looked at.

    ``cursor`` reads the page after that medium, ``before`` the page in front of it. Both are
    keyset lookups: they stay on the same medium however many are added elsewhere in the album,
    which is what makes the address of a page worth sending to somebody.
    """
    limit = min(max(limit, 1), MAX_PAGE_SIZE)
    order = SORT_KEY
    query = select(Media).where(Media.album_id == album.id, shown())

    if before is not None:
        taken_at, media_id = before
        # Walking backwards means reading away from the page, so the rows arrive the wrong way
        # round and are turned back at the end.
        rows = list(
            await session.scalars(
                query.where((order < taken_at) | ((order == taken_at) & (Media.id < media_id)))
                .order_by(order.desc(), Media.id.desc())
                .limit(limit + 1)
            )
        )
        return MediaPage(
            items=list(reversed(rows[:limit])),
            has_next=True,
            has_previous=len(rows) > limit,
        )

    if cursor is not None:
        taken_at, media_id = cursor
        query = query.where((order > taken_at) | ((order == taken_at) & (Media.id > media_id)))

    rows = list(await session.scalars(query.order_by(order, Media.id).limit(limit + 1)))
    # A cursor was handed out from the page before this one, so that page is where "back" leads.
    return MediaPage(
        items=rows[:limit], has_next=len(rows) > limit, has_previous=cursor is not None
    )


def cursor_value(media: Media) -> datetime:
    return media.taken_at or media.created_at
