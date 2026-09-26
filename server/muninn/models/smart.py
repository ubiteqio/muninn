"""Smarts: what an album falls into when nobody sorted it.

A folder of 4500 pictures from four years is not an album, it is a heap. The pictures that look
alike are found here once and written down as chapters, so browsing costs a read and no machine
has to be awake for it. What a chapter is called comes from the tags its media carry and the
album as a whole does not - "Katze" says something in a family album, "Innenraum" does not.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from muninn.models.base import Base

#: Raise it when the grouping itself changes; every album is then looked at again.
SMART_VERSION = 1


class SmartChapter(Base):
    """One group of media of one album that belong together by what they show."""

    __tablename__ = "smart_chapters"
    __table_args__ = (
        Index("ix_smart_chapters_album_id", "album_id"),
        Index("ix_smart_chapters_size", "size"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    album_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("albums.id", ondelete="CASCADE"), nullable=False
    )
    #: How it was found: "look" for media that look alike, "trait" for a shelf like documents.
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="look")
    #: What it is called, from the tags of its media. Empty when nothing stood out.
    title: Mapped[str] = mapped_column(Text, nullable=False, default="")
    #: The words the title was made of, for the app to show underneath.
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    cover_media_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("media.id", ondelete="SET NULL")
    )
    size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: When the earliest and the latest of its media were taken.
    from_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    until_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: How tightly it holds together (mean cosine distance to the leader): a hint for ordering.
    tightness: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    version: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=SMART_VERSION)
    built_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class SmartChapterMedium(Base):
    __tablename__ = "smart_chapter_media"
    __table_args__ = (Index("ix_smart_chapter_media_media_id", "media_id"),)

    chapter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("smart_chapters.id", ondelete="CASCADE"), primary_key=True
    )
    media_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("media.id", ondelete="CASCADE"), primary_key=True
    )
    #: Closest to the leader first: the cover and the first row are the clearest examples.
    position: Mapped[int] = mapped_column(Integer, nullable=False)
