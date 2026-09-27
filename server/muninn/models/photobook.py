"""Fotobücher: an album read as a book instead of browsed as a grid.

A book is made once and then stands still. Its pages are built from what the library already
knows - times, places, faces, the descriptions the analyzer wrote - and its prose is written by
the machine that describes the pictures. Both are expensive enough that nobody wants them on
every open, and, more to the point, a book that rearranged itself whenever the album grew would
not be a book. So the finished pages are stored, and the album may go on without them.

Several books may come from one album, and each draws its own pictures: the seed decides which
of several near-identical shots is taken and where the spread across the album lands.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from muninn.models.base import Base

#: Raise it when the page building itself changes, so an old book can be told from a new one.
PHOTOBOOK_VERSION = 1

#: How the pages look. One for now; the column is here so a second is a choice, not a migration.
STYLE_SCRAPBOOK = "scrapbook"
STYLES = (STYLE_SCRAPBOOK,)

#: How much of the album a book holds, before the admin's ceiling is applied.
SIZE_SMALL = "small"
SIZE_MEDIUM = "medium"
SIZE_LARGE = "large"
SIZES = (SIZE_SMALL, SIZE_MEDIUM, SIZE_LARGE)

#: What share of an album's pictures each size aims for.
SHARE_OF_ALBUM = {SIZE_SMALL: 0.15, SIZE_MEDIUM: 0.30, SIZE_LARGE: 0.60}

#: What an admin gets when they do not say otherwise.
DEFAULT_MAX_MEDIA = 150

#: Where a book stands. "written" only says that the machine had its say; a book without it is
#: whole and readable, it just speaks in dates and places rather than in sentences.
STATE_BUILDING = "building"
STATE_READY = "ready"
STATE_FAILED = "failed"
STATES = (STATE_BUILDING, STATE_READY, STATE_FAILED)


class Photobook(Base):
    """One book: which album it came from, how it was cut, and its finished pages."""

    __tablename__ = "photobooks"
    __table_args__ = (
        Index("ix_photobooks_album_id", "album_id"),
        Index("ix_photobooks_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    #: The album the pictures come from. Gone with it: a book of a folder nobody publishes any
    #: more has nothing to show.
    album_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("albums.id", ondelete="CASCADE"), nullable=False
    )

    #: What stands on the first page. Taken from the album unless an admin says otherwise.
    title: Mapped[str] = mapped_column(Text, nullable=False)
    #: The line under it: the days the book spans.
    subtitle: Mapped[str] = mapped_column(Text, nullable=False, default="")

    style: Mapped[str] = mapped_column(String(16), nullable=False, default=STYLE_SCRAPBOOK)
    size: Mapped[str] = mapped_column(String(8), nullable=False, default=SIZE_MEDIUM)
    #: The ceiling an admin set. A folder of 4500 holidays is not a book.
    max_media: Mapped[int] = mapped_column(Integer, nullable=False, default=150)
    #: Makes a second book of the same album a different book.
    seed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    state: Mapped[str] = mapped_column(String(16), nullable=False, default=STATE_BUILDING)
    #: Why it failed, for the admin area. Empty while all is well.
    trouble: Mapped[str] = mapped_column(Text, nullable=False, default="")
    #: Whether the machine wrote the prose. False means the pages carry their plain facts and
    #: the texts can be asked for later, when the machine is up again.
    written: Mapped[bool] = mapped_column(nullable=False, default=False)

    #: The finished pages, exactly as the reader draws them. Media are referenced by id; every
    #: address is signed when the book is read, never stored.
    pages: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    page_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    media_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=PHOTOBOOK_VERSION)

    #: The picture on the cover, for the list of books.
    cover_media_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("media.id", ondelete="SET NULL")
    )
    #: The days the book covers, for sorting and for the line under the title.
    from_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    until_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    built_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
