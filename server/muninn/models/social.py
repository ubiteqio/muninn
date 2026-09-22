"""Likes, favourites and comments: what people do with the library."""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from muninn.models.base import Base


class _Mark:
    """What a like and a favourite share: somebody, and exactly one medium or album."""

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    media_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("media.id", ondelete="CASCADE")
    )
    album_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("albums.id", ondelete="CASCADE")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Reaction(StrEnum):
    """What a like on a medium may be. The app draws the emoji; the server only knows the name."""

    HEART = "heart"
    THUMBS_UP = "thumbs_up"
    JOY = "joy"
    WOW = "wow"
    MOVED = "moved"
    CLAP = "clap"
    FIRE = "fire"
    HANG_LOOSE = "hang_loose"


class Like(_Mark, Base):
    """Somebody likes a medium, an album or a comment. Everybody may see who, and how.

    One per person and target. On a medium it is one of the reactions; albums and comments get
    the heart.
    """

    __tablename__ = "likes"
    __table_args__ = (
        CheckConstraint(
            "num_nonnulls(media_id, album_id, comment_id) = 1", name="ck_likes_one_target"
        ),
        CheckConstraint(
            "reaction IN ('heart', 'thumbs_up', 'joy', 'wow', 'moved', 'clap', 'fire',"
            " 'hang_loose')",
            name="ck_likes_reaction",
        ),
    )

    reaction: Mapped[str] = mapped_column(String(16), nullable=False, default=Reaction.HEART)

    comment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("comments.id", ondelete="CASCADE")
    )


class Favorite(_Mark, Base):
    """A medium or album somebody keeps in Walhall. Only they see it."""

    __tablename__ = "favorites"
    __table_args__ = (
        CheckConstraint("num_nonnulls(media_id, album_id) = 1", name="ck_favorites_one_target"),
    )


class Comment(Base):
    """What somebody wrote about a medium or album - or in answer to another comment."""

    __tablename__ = "comments"
    __table_args__ = (
        CheckConstraint("num_nonnulls(media_id, album_id) = 1", name="ck_comments_one_target"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    media_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("media.id", ondelete="CASCADE")
    )
    album_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("albums.id", ondelete="CASCADE")
    )
    #: The comment this one answers. Only one level: an answer is never answered itself.
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("comments.id", ondelete="CASCADE")
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Deleted but answered: its place stays, its text goes.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CommentMention(Base):
    """Somebody a comment mentions with @name - for their notifications."""

    __tablename__ = "comment_mentions"

    comment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("comments.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
