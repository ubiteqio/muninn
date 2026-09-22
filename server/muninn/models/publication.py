"""A folder of the library that is published as an album.

The library itself is the folder the host mounts; it is not chosen in Muninn. What is chosen here
is which folders below it appear under Albums - with everything beneath them, and in the place
the original has, so a folder is found where one expects it.

Originals are only ever a source: nothing here writes, moves, renames or deletes them.
"""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from muninn.models.base import Base, TimestampMixin
from muninn.models.enum import pg_enum


class ScanStatus(StrEnum):
    """How the last sync of a folder ended."""

    NEVER = "never"
    RUNNING = "running"
    OK = "ok"
    #: More files than the safety net allows would have been marked as missing.
    PAUSED = "paused"
    #: The folder is not there, or sits on a different file system than when it was published.
    UNAVAILABLE = "unavailable"
    FAILED = "failed"
    #: An admin stopped the read. It stops between folders, so what was read is kept.
    CANCELLED = "cancelled"


class Publication(TimestampMixin, Base):
    """One published folder, stored as its path below the library."""

    __tablename__ = "publications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    #: Path below the mounted library; "" would be the library itself.
    relative_path: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    #: A paused folder keeps its albums but is not read any more.
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    #: The file system the folder was on when it was published. A share that is not mounted sits
    #: on a different one, and that is how Muninn tells "deleted" from "not mounted".
    device_id: Mapped[int | None] = mapped_column(BigInteger)

    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_sync_status: Mapped[ScanStatus] = mapped_column(
        pg_enum(ScanStatus, "scan_status"), nullable=False, default=ScanStatus.NEVER
    )
    last_sync_message: Mapped[str | None] = mapped_column(Text)
    #: Files a paused sync would have marked as missing; above zero it waits for a confirmation.
    pending_deletions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: Subfolders switched off again: not read, and nothing of them in Muninn.
    excluded_paths: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)

    @property
    def name(self) -> str:
        """What the folder is called; the library itself has no name of its own."""
        return self.relative_path.rsplit("/", 1)[-1] if self.relative_path else ""
