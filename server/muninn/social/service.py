"""Likes and favourites.

A like is public in the family: everybody sees who liked a picture. A favourite is private: it
puts a picture or an album into the person's own Walhall. Both are idempotent - liking twice is
one like, taking away a like that is not there is nothing.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from sqlalchemy import ColumnElement, delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from muninn.models.album import Album
from muninn.models.change_log import ChangeKind, ChangeLogEntry
from muninn.models.media import Media, MediaStatus, shown
from muninn.models.social import Comment, Favorite, Like, Reaction
from muninn.models.user import User

#: How many names a summary carries. "Anna, Boris und 5 weitere" - more says nothing more.
NAMES_SHOWN = 3


class TargetKind(StrEnum):
    MEDIA = "media"
    ALBUM = "album"


@dataclass(frozen=True, slots=True)
class Target:
    kind: TargetKind
    id: uuid.UUID


class TargetNotFoundError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class Summary:
    """What the app shows beside a heart and a star."""

    likes: int
    liked: bool
    #: The people who liked it, the viewer first when they did, then the most recent.
    likers: list[str]
    favorite: bool
    #: How many comments there are to read.
    comments: int = 0
    #: The viewer's own reaction, if any.
    reaction: str | None = None
    #: How often each reaction was given, the most frequent first.
    reactions: list[tuple[str, int]] = field(default_factory=list)
    #: The reaction of each of the likers, in the same order.
    liker_reactions: list[str] = field(default_factory=list)


def _on(model: type[Like] | type[Favorite], target: Target) -> ColumnElement[bool]:
    column = model.media_id if target.kind is TargetKind.MEDIA else model.album_id
    return column == target.id


async def ensure_exists(session: AsyncSession, target: Target) -> None:
    """A like on a medium that is gone from the NAS would be a like on nothing anybody sees."""
    if target.kind is TargetKind.MEDIA:
        media = await session.get(Media, target.id)
        if media is None or media.status is not MediaStatus.ACTIVE:
            raise TargetNotFoundError
    elif await session.get(Album, target.id) is None:
        raise TargetNotFoundError


async def _mark(
    session: AsyncSession, model: type[Like] | type[Favorite], user: User, target: Target
) -> None:
    await ensure_exists(session, target)
    column = "media_id" if target.kind is TargetKind.MEDIA else "album_id"
    await session.execute(
        insert(model)
        .values(id=uuid.uuid4(), user_id=user.id, **{column: target.id})
        .on_conflict_do_nothing()
    )
    await session.commit()


async def _unmark(
    session: AsyncSession, model: type[Like] | type[Favorite], user: User, target: Target
) -> None:
    await session.execute(delete(model).where(model.user_id == user.id, _on(model, target)))
    await session.commit()


async def like(
    session: AsyncSession, user: User, target: Target, reaction: Reaction = Reaction.HEART
) -> None:
    """One reaction per person: a new one replaces the old."""
    await ensure_exists(session, target)
    await session.execute(delete(Like).where(Like.user_id == user.id, _on(Like, target)))
    column = "media_id" if target.kind is TargetKind.MEDIA else "album_id"
    await session.execute(
        insert(Like).values(
            id=uuid.uuid4(), user_id=user.id, reaction=reaction.value, **{column: target.id}
        )
    )
    await session.commit()


async def unlike(session: AsyncSession, user: User, target: Target) -> None:
    await _unmark(session, Like, user, target)


async def favorite(session: AsyncSession, user: User, target: Target) -> None:
    await _mark(session, Favorite, user, target)


async def unfavorite(session: AsyncSession, user: User, target: Target) -> None:
    await _unmark(session, Favorite, user, target)


async def summary(session: AsyncSession, user: User, target: Target) -> Summary:
    count = int(
        await session.scalar(select(func.count()).select_from(Like).where(_on(Like, target))) or 0
    )
    rows = await session.execute(
        select(User.id, User.display_name, Like.reaction)
        .join(Like, Like.user_id == User.id)
        .where(_on(Like, target))
        # The viewer first when they liked it, then the most recent.
        .order_by((User.id == user.id).desc(), Like.created_at.desc())
        .limit(NAMES_SHOWN)
    )
    people = rows.all()
    liked = any(row.id == user.id for row in people)
    mine = await session.scalar(
        select(Like.reaction).where(Like.user_id == user.id, _on(Like, target))
    )
    counts = await session.execute(
        select(Like.reaction, func.count())
        .where(_on(Like, target))
        .group_by(Like.reaction)
        .order_by(func.count().desc(), func.max(Like.created_at).desc())
    )
    favorited = await session.scalar(
        select(func.count())
        .select_from(Favorite)
        .where(Favorite.user_id == user.id, _on(Favorite, target))
    )
    # Imported here: the comments module builds on this one.
    from muninn.social.comments import count_of

    return Summary(
        likes=count,
        liked=liked,
        likers=[row.display_name for row in people],
        favorite=bool(favorited),
        comments=await count_of(session, target),
        reaction=mine,
        reactions=[(reaction, int(count)) for reaction, count in counts.tuples()],
        liker_reactions=[row.reaction for row in people],
    )


@dataclass(frozen=True, slots=True)
class FavoritePage:
    media: list[Media]
    #: When the last one on this page was made a favourite; pass it on for the next page.
    next_before: datetime | None


async def favorite_media(
    session: AsyncSession, user: User, *, before: datetime | None = None, limit: int = 60
) -> FavoritePage:
    """Walhall's pictures: the ones this person keeps, the most recently kept first."""
    query = (
        select(Media, Favorite.created_at)
        .join(Favorite, Favorite.media_id == Media.id)
        .where(Favorite.user_id == user.id, shown())
        .options(selectinload(Media.files))
        .order_by(Favorite.created_at.desc(), Media.id)
        .limit(limit + 1)
    )
    if before is not None:
        query = query.where(Favorite.created_at < before)
    rows = (await session.execute(query)).all()
    page = rows[:limit]
    return FavoritePage(
        media=[row[0] for row in page],
        next_before=page[-1][1] if len(rows) > limit and page else None,
    )


async def favorite_album_ids(session: AsyncSession, user: User) -> list[uuid.UUID]:
    """Walhall's albums, the most recently kept first."""
    rows = await session.scalars(
        select(Favorite.album_id)
        .where(Favorite.user_id == user.id, Favorite.album_id.is_not(None))
        .order_by(Favorite.created_at.desc())
    )
    return [album_id for album_id in rows if album_id is not None]


# --- the news: what everybody has been doing -------------------------------------------------


@dataclass(frozen=True, slots=True)
class Happening:
    """One line of the news: a comment, a like, or new media in an album."""

    key: str
    kind: str
    actor_id: uuid.UUID | None
    media_id: uuid.UUID | None
    album_id: uuid.UUID | None
    at: datetime
    count: int = 1
    excerpt: str | None = None
    #: For a like on a medium: which reaction.
    reaction: str | None = None


async def happenings(
    session: AsyncSession, *, before: datetime | None = None, limit: int = 20
) -> list[Happening]:
    """The newest comments, likes and arrivals of new media, newest first.

    New media are gathered per album and hour: an import of 700 pictures is one line, not 700.
    """
    comment_rules: list[ColumnElement[bool]] = [Comment.deleted_at.is_(None)]
    like_rules: list[ColumnElement[bool]] = [Like.comment_id.is_(None)]
    arrival_rules: list[ColumnElement[bool]] = [
        ChangeLogEntry.kind == ChangeKind.MEDIA_ADDED,
        ChangeLogEntry.album_id.is_not(None),
    ]
    if before is not None:
        comment_rules.append(Comment.created_at < before)
        like_rules.append(Like.created_at < before)
        arrival_rules.append(ChangeLogEntry.occurred_at < before)

    found: list[Happening] = []
    for comment in await session.scalars(
        select(Comment).where(*comment_rules).order_by(Comment.created_at.desc()).limit(limit)
    ):
        found.append(
            Happening(
                key=f"comment:{comment.id}",
                kind="comment",
                actor_id=comment.user_id,
                media_id=comment.media_id,
                album_id=comment.album_id,
                at=comment.created_at,
                excerpt=comment.body,
            )
        )
    for like in await session.scalars(
        select(Like).where(*like_rules).order_by(Like.created_at.desc()).limit(limit)
    ):
        found.append(
            Happening(
                key=f"like:{like.id}",
                kind="like",
                actor_id=like.user_id,
                media_id=like.media_id,
                album_id=like.album_id,
                at=like.created_at,
                reaction=like.reaction,
            )
        )

    hour = func.date_trunc("hour", ChangeLogEntry.occurred_at)
    latest = func.max(ChangeLogEntry.occurred_at)
    arrivals = await session.execute(
        select(
            ChangeLogEntry.album_id,
            hour,
            func.count(),
            latest,
            func.array_agg(ChangeLogEntry.media_id),
        )
        .where(*arrival_rules)
        .group_by(ChangeLogEntry.album_id, hour)
        .order_by(latest.desc())
        .limit(limit)
    )
    for album_id, started, count, at, media in arrivals.tuples():
        found.append(
            Happening(
                key=f"new:{album_id}:{started.isoformat()}",
                kind="new_media",
                actor_id=None,
                media_id=next((item for item in media if item is not None), None),
                album_id=album_id,
                at=at,
                count=count,
            )
        )

    return sorted(found, key=lambda happening: happening.at, reverse=True)[:limit]
