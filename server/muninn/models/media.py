"""A medium and the files it is made of."""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    ColumnElement,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    and_,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from muninn.models.base import Base, TimestampMixin
from muninn.models.enum import pg_enum

if TYPE_CHECKING:
    from muninn.models.album import Album


class MediaKind(StrEnum):
    IMAGE = "image"
    VIDEO = "video"


class MediaStatus(StrEnum):
    ACTIVE = "active"
    #: The file is gone from the NAS. Kept for 30 days, then removed for good.
    MISSING = "missing"


class MediaFileRole(StrEnum):
    """What a file is to its medium."""

    #: The file Muninn shows and derives from.
    PRIMARY = "primary"
    #: The raw file next to a JPEG of the same name.
    RAW = "raw"
    #: The short clip of a Live Photo.
    MOTION = "motion"


class DateSource(StrEnum):
    """Where the capture date came from. The last two are guesses and are marked as such."""

    EXIF = "exif"
    GPS = "gps"
    FILENAME = "filename"
    FOLDER_NAME = "folder_name"
    FILE_MTIME = "file_mtime"


#: Sources 4 and 5 of the concept: shown discreetly as approximate in the app.
IMPRECISE_DATE_SOURCES = frozenset({DateSource.FOLDER_NAME, DateSource.FILE_MTIME})


class Media(TimestampMixin, Base):
    """One photo or video, identified by its id and its content hash - never by its path.

    Likes, comments and faces hang on the id, so renaming or moving a file on the NAS keeps
    everything that people added.
    """

    __tablename__ = "media"
    __table_args__ = (
        Index("ix_media_album_id_taken_at", "album_id", "taken_at"),
        Index("ix_media_content_hash", "content_hash"),
        Index("ix_media_status", "status"),
        Index("ix_media_place_id", "place_id"),
        Index("ix_media_taken_at", "taken_at"),
        Index(
            "ix_media_duplicate_of",
            "duplicate_of",
            postgresql_where=text("duplicate_of IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    album_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("albums.id", ondelete="CASCADE"), nullable=False
    )

    kind: Mapped[MediaKind] = mapped_column(pg_enum(MediaKind, "media_kind"), nullable=False)
    status: Mapped[MediaStatus] = mapped_column(
        pg_enum(MediaStatus, "media_status"), nullable=False, default=MediaStatus.ACTIVE
    )
    missing_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    #: BLAKE3 of the primary file. Identity across renames and moves.
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    #: Hash over the first and last mebibyte plus the size: tells "edited" from "only touched"
    #: without reading a 4 GB video, and finds a moved file before it is read in full.
    quick_hash: Mapped[str | None] = mapped_column(String(64))
    #: Hash over the decoded pixels, written by stage 3. Equal pixels after a change mean only
    #: metadata were written, and the expensive stages keep their results.
    pixel_hash: Mapped[str | None] = mapped_column(String(64))
    #: What stage 3's files for this medium take on the server, together: thumbnail, preview,
    #: playable video and poster. Empty until they are made.
    derived_bytes: Mapped[int | None] = mapped_column(BigInteger)

    taken_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    taken_at_source: Mapped[DateSource | None] = mapped_column(pg_enum(DateSource, "date_source"))

    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    duration_seconds: Mapped[float | None] = mapped_column(Float)

    camera_make: Mapped[str | None] = mapped_column(String(120))
    camera_model: Mapped[str | None] = mapped_column(String(120))
    lens: Mapped[str | None] = mapped_column(String(160))

    #: Plain degrees. Migration 0021 generates the PostGIS point "location" from them, which only
    #: the map's SQL reads (muninn.places), so the model leaves it out.
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)

    #: The town or city it was taken at or near, found from the coordinates (muninn.places).
    #: The point it was placed for is kept beside it, so changed coordinates place it again.
    place_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("places.id", ondelete="SET NULL")
    )
    #: True when the place is its album's, not its own coordinates': shown as "geschätzt".
    place_estimated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    #: Version of the gazetteer that placed it; 0 means "not placed yet".
    place_version: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)

    #: 64 bits of the picture that survive shrinking and compressing (muninn.duplicates), read
    #: from the thumbnail. Stored signed, as PostgreSQL's bigint is.
    fingerprint: Mapped[int | None] = mapped_column(BigInteger)
    fingerprint_version: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    #: Set when an admin hid this medium as a copy of another. It then leaves albums, timeline,
    #: search and map; the file on the NAS stays where it is.
    duplicate_of: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("media.id", ondelete="SET NULL")
    )

    #: Version of the face stage that looked at it; 0 means "not looked at yet".
    face_version: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)

    #: Version of the metadata stage that last wrote these fields; 0 means "not read yet".
    metadata_version: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    #: Version of the preview stage; 0 means the derivatives are still missing.
    derive_version: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)

    #: Where the derivatives lie, relative to the derived path on the local SSD. They are written
    #: under a new name and the old ones are only removed once these columns point at them, so
    #: the app never sees half a picture.
    thumbnail_path: Mapped[str | None] = mapped_column(Text)
    preview_path: Mapped[str | None] = mapped_column(Text)
    #: The playable version of a video, plus its still image.
    video_path: Mapped[str | None] = mapped_column(Text)
    poster_path: Mapped[str | None] = mapped_column(Text)

    album: Mapped["Album"] = relationship(lazy="raise")
    files: Mapped[list["MediaFile"]] = relationship(
        back_populates="media", cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def primary_file(self) -> "MediaFile":
        """Every medium has exactly one primary file; the scanner keeps it that way."""
        return next(file for file in self.files if file.role is MediaFileRole.PRIMARY)

    @property
    def date_is_estimated(self) -> bool:
        return self.taken_at_source in IMPRECISE_DATE_SOURCES


class MediaFile(TimestampMixin, Base):
    """One file on the NAS.

    A RAW next to its JPEG and the clip of a Live Photo are files of the same medium.
    """

    __tablename__ = "media_files"
    __table_args__ = (
        UniqueConstraint("relative_path", name="uq_media_files_relative_path"),
        Index("ix_media_files_content_hash", "content_hash"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    media_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("media.id", ondelete="CASCADE"), nullable=False
    )

    role: Mapped[MediaFileRole] = mapped_column(
        pg_enum(MediaFileRole, "media_file_role"), nullable=False
    )
    #: Path below the mounted library, with forward slashes: this locates the original.
    relative_path: Mapped[str] = mapped_column(Text, nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)

    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    #: The same short hash as on the medium, per file: this is what a comparison starts with.
    quick_hash: Mapped[str | None] = mapped_column(String(64))
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    #: Modification time on the NAS, used to notice an edited file without hashing it again.
    modified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    media: Mapped["Media"] = relationship(back_populates="files", lazy="raise")


def shown() -> ColumnElement[bool]:
    """The media the app lists: on the NAS, and not hidden as a copy of another."""
    return and_(Media.status == MediaStatus.ACTIVE, Media.duplicate_of.is_(None))
