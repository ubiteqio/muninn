"""Albums: one folder of the library, one album."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from muninn.models.base import Base, TimestampMixin
from muninn.models.enum import pg_enum
from muninn.models.publication import ScanStatus


class Album(TimestampMixin, Base):
    """A folder of a library root.

    Folders that hold only other folders become collections in the tree; they are albums here all
    the same and simply have no media of their own. Title and description can be changed in
    Muninn, which never touches the folder on the NAS.
    """

    __tablename__ = "albums"
    __table_args__ = (
        UniqueConstraint("relative_path", name="uq_albums_relative_path"),
        Index("ix_albums_parent_id", "parent_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("albums.id", ondelete="CASCADE")
    )

    #: Path of the folder below the mounted library.
    relative_path: Mapped[str] = mapped_column(Text, nullable=False)

    #: Whether this folder is read. False means it only carries the way to a published folder
    #: further down - the same place the original has, so albums are found where one expects.
    is_source: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    #: The folder's own name, as it is spelled on the NAS.
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    #: Signature of the last complete listing: how many media files, how large together, the
    #: newest time among them and a hash over the sorted listing. A quick sync that finds the
    #: same signature leaves every file in this folder alone.
    entry_signature: Mapped[str | None] = mapped_column(String(64))

    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_sync_status: Mapped[ScanStatus] = mapped_column(
        pg_enum(ScanStatus, "scan_status"), nullable=False, default=ScanStatus.NEVER
    )
    #: Why the last sync of this folder stopped, if it did. Shown in the album.
    last_sync_message: Mapped[str | None] = mapped_column(Text)

    #: Set in Muninn; when it is null the folder name is the title.
    title: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    #: Set in Muninn: where the album was taken, for its media without coordinates - and those
    #: of the albums below it that have no place of their own.
    place_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("places.id", ondelete="SET NULL")
    )

    @property
    def display_title(self) -> str:
        return self.title or self.name
