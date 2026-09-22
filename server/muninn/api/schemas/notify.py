"""The contract of the bell and the news."""

from datetime import datetime, time
from uuid import UUID

from pydantic import BaseModel

from muninn.core.signing import sign_media
from muninn.models.album import Album
from muninn.models.media import Media, MediaKind
from muninn.models.notification import PushEvent


class MediaRef(BaseModel):
    """Enough of a medium to show its thumbnail and to lead to it."""

    id: UUID
    kind: MediaKind
    album_id: UUID
    thumb: str | None

    @classmethod
    def of(cls, media: Media, *, secret: str) -> "MediaRef":
        thumb = (
            f"/api/v1/media/{media.id}/thumb?token={sign_media(media.id, 'thumb', secret=secret)}"
            if media.thumbnail_path
            else None
        )
        return cls(id=media.id, kind=media.kind, album_id=media.album_id, thumb=thumb)


class AlbumRef(BaseModel):
    id: UUID
    title: str

    @classmethod
    def of(cls, album: Album) -> "AlbumRef":
        return cls(id=album.id, title=album.display_title)


class NotificationView(BaseModel):
    id: UUID
    #: reply, mention, comment_like, comment or new_media.
    kind: str
    #: Who did it, the most recent first. Empty for new media.
    actors: list[str]
    #: How many events it gathers: comments, likes, new pictures.
    count: int
    created_at: datetime
    updated_at: datetime
    read: bool
    media: MediaRef | None
    album: AlbumRef | None
    #: The words of the comment it is about.
    excerpt: str | None


class UnreadCount(BaseModel):
    count: int


class MarkRead(BaseModel):
    """Which to mark as read; none named means all of them."""

    ids: list[UUID] | None = None


class ActivityView(BaseModel):
    """One line of the news."""

    key: str
    #: comment, like or new_media.
    kind: str
    #: Who did it; empty for new media.
    actor: str | None
    count: int
    at: datetime
    media: MediaRef | None
    album: AlbumRef | None
    excerpt: str | None
    #: For a like on a medium: which reaction.
    reaction: str | None = None


class NotificationSettingsView(BaseModel):
    """Which events also come as a push notification, and the quiet hours without any.

    In the app every event appears regardless. ``admin_alerts`` exists for admins only.
    """

    push: dict[PushEvent, bool]
    quiet_enabled: bool
    #: Local time, "22:00".
    quiet_start: time
    quiet_end: time
