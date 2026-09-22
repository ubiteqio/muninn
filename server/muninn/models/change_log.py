"""What a sync found: one line per change, kept for 90 days.

The log feeds the notifications ("12 new photos in Sommer 2026"), explains in the admin area why
a sync paused, and answers afterwards what actually happened during the night.
"""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Index, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from muninn.models.base import Base
from muninn.models.enum import pg_enum

#: How long the log is kept.
RETENTION_DAYS = 90


class ChangeKind(StrEnum):
    ALBUM_ADDED = "album_added"
    ALBUM_REMOVED = "album_removed"
    MEDIA_ADDED = "media_added"
    #: The file changed and the derived work has to be done again.
    MEDIA_CHANGED = "media_changed"
    #: Only size or time changed while the content stayed the same; nothing was rebuilt.
    MEDIA_TOUCHED = "media_touched"
    MEDIA_MOVED = "media_moved"
    MEDIA_MISSING = "media_missing"
    #: A missing file came back within the grace period.
    MEDIA_RESTORED = "media_restored"
    #: The grace period ran out; the medium and everything derived from it are gone.
    MEDIA_REMOVED = "media_removed"


class SyncTrigger(StrEnum):
    QUICK = "quick"
    FULL = "full"
    MANUAL = "manual"
    AGENT = "agent"


class ChangeLogEntry(Base):
    """One finding. The rows outlive the media they describe, so the ids may become null."""

    __tablename__ = "change_log"
    __table_args__ = (Index("ix_change_log_occurred_at", "occurred_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    album_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("albums.id", ondelete="SET NULL")
    )
    media_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("media.id", ondelete="SET NULL")
    )

    kind: Mapped[ChangeKind] = mapped_column(pg_enum(ChangeKind, "change_kind"), nullable=False)
    trigger: Mapped[SyncTrigger] = mapped_column(
        pg_enum(SyncTrigger, "sync_trigger"), nullable=False
    )
    #: The path at the time, so a line still says something after the row it points at is gone.
    path: Mapped[str | None] = mapped_column(Text)
