"""Smarts: what the library falls into when nobody sorted it.

Twenty-six years of folders are not an archive anybody browses, and a folder is only where a
file happens to lie. A chapter is something one recognises: four days in Chessy, the third of
May, Weihnachten over twelve years, every picture of the cat. Each kind has its own rule - time
and place, faces, feasts, or what the pictures look like - and all of them read what the
library already knows, so no machine has to be awake for any of it.

A chapter spans whatever folders its media come from; most span many.
"""

import uuid
from datetime import datetime
from typing import Any

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
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from muninn.models.base import Base

#: Raise it when the grouping itself changes; everything is then found anew.
SMART_VERSION = 3

#: What a chapter was made of. Every kind has its own rule and its own name.
KIND_MOTIF = "motif"
KIND_THEME = "theme"
KIND_TRIP = "trip"
KIND_DAY = "day"
KIND_PLACE = "place"
KIND_RITUAL = "ritual"
KIND_PERSON = "person"
KINDS = (KIND_TRIP, KIND_DAY, KIND_THEME, KIND_PLACE, KIND_PERSON, KIND_RITUAL, KIND_MOTIF)


class SmartChapter(Base):
    """One group of media of one album that belong together by what they show."""

    __tablename__ = "smart_chapters"
    __table_args__ = (
        Index("ix_smart_chapters_album_id", "album_id"),
        Index("ix_smart_chapters_size", "size"),
        Index("ix_smart_chapters_kind", "kind"),
        Index("ix_smart_chapters_rank", "rank"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    #: The album, when everything in the chapter comes from one; nothing when it spans the
    #: library, which most chapters do.
    album_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("albums.id", ondelete="CASCADE")
    )
    #: How many albums it draws from.
    albums: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    #: Which rule found it: a trip, a day, a motif, a place, a person, a recurring feast.
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default=KIND_MOTIF)
    #: What it is called, as a text key and its values - the app writes the German. A title
    #: made here would be German in the database, and German belongs in the app's texts.
    title_key: Mapped[str] = mapped_column(String(32), nullable=False, default="motif")
    title_args: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    #: The words the name was made of, where tags made it.
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    cover_media_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("media.id", ondelete="SET NULL")
    )
    size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: Where it stands on the screen. The kinds take turns, so a wall of chapters is a mixture
    #: of journeys, days, faces and motifs rather than one kind after another.
    rank: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
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
