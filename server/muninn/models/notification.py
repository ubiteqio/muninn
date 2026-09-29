"""What concerns one person, for the bell."""

import uuid
from datetime import datetime, time
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, Time, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from muninn.models.base import Base


class NotificationKind(StrEnum):
    #: Somebody answered my comment.
    REPLY = "reply"
    #: Somebody named me with @.
    MENTION = "mention"
    #: Somebody liked my comment.
    COMMENT_LIKE = "comment_like"
    #: A new comment on something I keep in Walhall or commented on myself.
    COMMENT = "comment"
    #: New pictures and videos in an album.
    NEW_MEDIA = "new_media"
    #: A stage gave up on a medium. Admins only, and never for a machine that is merely away.
    STAGE_FAILED = "stage_failed"


class Notification(Base):
    """One entry of the bell. Bundles several events of the same kind on the same thing."""

    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    #: Who did it, the most recent last. Empty for new media, which nobody in particular added.
    actor_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    #: How many events went into it: comments, likes, new media.
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    media_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("media.id", ondelete="CASCADE")
    )
    album_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("albums.id", ondelete="CASCADE")
    )
    comment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("comments.id", ondelete="CASCADE")
    )
    #: The step of the pipeline that gave up, for a stage_failed entry: "derive", "faces", ...
    stage: Mapped[str | None] = mapped_column(String(24))
    #: What went wrong, in the machine's own words, so an admin can act without digging.
    detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    #: When the last event joined it; the bell is ordered by this.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PushEvent(StrEnum):
    """What somebody may want on their phone, as the concept lists it."""

    REPLY = "reply"
    MENTION = "mention"
    COMMENT_LIKE = "comment_like"
    #: A new comment on something I keep or commented on.
    COMMENT = "comment"
    #: Every like, comment and favourite of the others - a lot, so off unless asked for.
    ACTIVITY = "activity"
    NEW_MEDIA = "new_media"
    #: NAS not reachable, indexing errors. Admins only.
    ADMIN_ALERTS = "admin_alerts"


#: The concept's defaults: everything that concerns me on, everybody's every move off.
PUSH_DEFAULTS: dict[PushEvent, bool] = {
    PushEvent.REPLY: True,
    PushEvent.MENTION: True,
    PushEvent.COMMENT_LIKE: True,
    PushEvent.COMMENT: True,
    PushEvent.ACTIVITY: False,
    PushEvent.NEW_MEDIA: True,
    PushEvent.ADMIN_ALERTS: True,
}

DEFAULT_QUIET_START = time(22, 0)
DEFAULT_QUIET_END = time(7, 0)


class NotificationSettings(Base):
    """Which events come as push, and when none come at all. Missing means the defaults."""

    __tablename__ = "notification_settings"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    #: Event name to on or off; an event not in it has its default.
    push: Mapped[dict[str, bool]] = mapped_column(JSONB, nullable=False, default=dict)
    quiet_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    quiet_start: Mapped[time] = mapped_column(Time, nullable=False, default=DEFAULT_QUIET_START)
    quiet_end: Mapped[time] = mapped_column(Time, nullable=False, default=DEFAULT_QUIET_END)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
