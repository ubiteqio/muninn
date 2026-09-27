"""The contract of the Fotobücher."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from muninn.core.signing import sign_media
from muninn.models.photobook import (
    DEFAULT_MAX_MEDIA,
    SIZE_MEDIUM,
    STYLE_SCRAPBOOK,
    Photobook,
)


class PhotobookView(BaseModel):
    """One book on the shelf: everything the list of books shows."""

    id: uuid.UUID
    album_id: uuid.UUID
    album: str
    title: str
    subtitle: str
    style: str
    size: str
    state: str
    #: Whether the machine wrote its prose. A book without it reads plainer, not shorter.
    written: bool
    trouble: str
    pages: int
    media: int
    #: A signed address for the cover picture, or nothing while the book is still being built.
    cover: str | None
    from_at: datetime | None
    until_at: datetime | None
    built_at: datetime | None
    created_at: datetime


class PhotobookList(BaseModel):
    items: list[PhotobookView]


class PhotobookRead(PhotobookView):
    """The book itself: its pages, with every picture addressed and signed for this hour."""

    leaves: list[dict[str, Any]]


class NewPhotobook(BaseModel):
    """What an admin says when they make books of an album."""

    album_id: uuid.UUID
    size: str = SIZE_MEDIUM
    style: str = STYLE_SCRAPBOOK
    #: The ceiling on pictures. A folder of 4500 holidays is not a book.
    max_media: int = Field(default=DEFAULT_MAX_MEDIA, ge=4, le=400)
    #: How many books to make of this album at once. Each draws its own pictures.
    count: int = Field(default=1, ge=1, le=20)
    title: str = ""


class PhotobookQueued(BaseModel):
    """The books that were put on the shelf, and the job that fills them."""

    items: list[PhotobookView]
    job_id: str | None = None


def signed_pages(book: Photobook, *, secret: str) -> list[dict[str, Any]]:
    """The stored pages with a signed address on every picture.

    The book keeps ids, not addresses: a token is good for an hour, and a book is meant to
    outlive it. So the addresses are minted here, on the way out, as everywhere else.
    """
    return [_signed_page(page, secret=secret) for page in book.pages]


def _signed_page(page: dict[str, Any], *, secret: str) -> dict[str, Any]:
    shown = dict(page)
    for field, held in page.items():
        if isinstance(held, dict) and "id" in held and "variant" in held:
            shown[field] = _addressed(held, secret=secret)
        elif isinstance(held, list) and held and isinstance(held[0], dict) and "variant" in held[0]:
            shown[field] = [_addressed(one, secret=secret) for one in held]
    return shown


def _addressed(shown: dict[str, Any], *, secret: str) -> dict[str, Any]:
    media_id = uuid.UUID(str(shown["id"]))
    variant = str(shown["variant"])
    token = sign_media(media_id, variant, secret=secret)
    return {**shown, "src": f"/api/v1/media/{media_id}/{variant}?token={token}"}


def view_of(book: Photobook, *, album: str, secret: str) -> PhotobookView:
    return PhotobookView(
        id=book.id,
        album_id=book.album_id,
        album=album,
        title=book.title,
        subtitle=book.subtitle,
        style=book.style,
        size=book.size,
        state=book.state,
        written=book.written,
        trouble=book.trouble,
        pages=book.page_count,
        media=book.media_count,
        cover=_cover_of(book, secret=secret),
        from_at=book.from_at,
        until_at=book.until_at,
        built_at=book.built_at,
        created_at=book.created_at,
    )


def _cover_of(book: Photobook, *, secret: str) -> str | None:
    if book.cover_media_id is None:
        return None
    token = sign_media(book.cover_media_id, "thumb", secret=secret)
    return f"/api/v1/media/{book.cover_media_id}/thumb?token={token}"
