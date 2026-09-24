"""The bell: what concerns one person, bundled so it does not flood them.

Several events of the same kind on the same thing within ten minutes are one notification - the
people who did it gathered, the count raised, the time moved on. Nobody is told about what they
did themselves. The caller commits, so a comment and the notifications about it land together.
"""

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta

from sqlalchemy import ColumnElement, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute, selectinload

from muninn.models.album import Album
from muninn.models.media import Media
from muninn.models.notification import (
    DEFAULT_QUIET_END,
    DEFAULT_QUIET_START,
    PUSH_DEFAULTS,
    Notification,
    NotificationKind,
    NotificationSettings,
    PushEvent,
)
from muninn.models.social import Comment, Favorite
from muninn.models.user import User, UserRole, UserStatus

#: Events closer together than this become one notification.
BUNDLE_WINDOW = timedelta(minutes=10)


@dataclass(frozen=True, slots=True)
class About:
    """The thing a notification is about: a medium or an album, and maybe a comment on it."""

    media_id: uuid.UUID | None = None
    album_id: uuid.UUID | None = None
    comment_id: uuid.UUID | None = None


async def notify(
    session: AsyncSession,
    recipients: Iterable[uuid.UUID],
    kind: NotificationKind,
    about: About,
    *,
    actor_id: uuid.UUID | None = None,
    count: int = 1,
    now: datetime | None = None,
) -> list[uuid.UUID]:
    """Tell these people. Returns who was told, for the live channel."""
    now = now or datetime.now(UTC)
    told: list[uuid.UUID] = []
    for user_id in dict.fromkeys(recipients):
        if user_id == actor_id:
            continue
        open_one = await session.scalar(
            select(Notification)
            .where(
                Notification.user_id == user_id,
                Notification.kind == kind.value,
                Notification.read_at.is_(None),
                Notification.updated_at > now - BUNDLE_WINDOW,
                _same(Notification.media_id, about.media_id),
                _same(Notification.album_id, about.album_id),
            )
            .order_by(Notification.updated_at.desc())
            .limit(1)
        )
        if open_one is not None:
            actors = [actor for actor in open_one.actor_ids if actor != actor_id]
            open_one.actor_ids = [*actors, actor_id] if actor_id else actors
            open_one.count += count
            open_one.updated_at = now
            open_one.comment_id = about.comment_id or open_one.comment_id
        else:
            session.add(
                Notification(
                    user_id=user_id,
                    kind=kind.value,
                    actor_ids=[actor_id] if actor_id else [],
                    count=count,
                    media_id=about.media_id,
                    album_id=about.album_id,
                    comment_id=about.comment_id,
                    created_at=now,
                    updated_at=now,
                )
            )
        told.append(user_id)
    await session.flush()
    return told


def _same(
    column: InstrumentedAttribute[uuid.UUID | None], value: uuid.UUID | None
) -> ColumnElement[bool]:
    return column.is_(None) if value is None else column == value


async def followers(
    session: AsyncSession, *, media_id: uuid.UUID | None, album_id: uuid.UUID | None
) -> list[uuid.UUID]:
    """Who cares about a medium or album: they keep it in Walhall, or commented on it."""
    if media_id is not None:
        kept = select(Favorite.user_id).where(Favorite.media_id == media_id)
        talked = select(Comment.user_id).where(Comment.media_id == media_id)
    else:
        kept = select(Favorite.user_id).where(Favorite.album_id == album_id)
        talked = select(Comment.user_id).where(Comment.album_id == album_id)
    rows = await session.scalars(kept.union(talked))
    return list(rows)


async def admins(session: AsyncSession) -> list[uuid.UUID]:
    """Every active admin - for what only somebody with the engine room can act on."""
    rows = await session.scalars(
        select(User.id).where(User.status == UserStatus.ACTIVE, User.role == UserRole.ADMIN)
    )
    return list(rows)


async def stage_failed(
    session: AsyncSession,
    *,
    media_id: uuid.UUID,
    stage: str,
    detail: str,
    now: datetime | None = None,
) -> list[uuid.UUID]:
    """A stage has given up on a medium: tell the admins, with what the machine said.

    Only a real failure gets here - a file nothing can be read from, a model that answered no.
    A machine that is merely away is not the medium's fault and says nothing, or every restart
    of the AI server would ring the bell a thousand times.

    One entry per medium and stage: a medium that fails two stages is two entries, because the
    two are different problems with different answers.
    """
    now = now or datetime.now(UTC)
    told: list[uuid.UUID] = []
    for user_id in await admins(session):
        open_one = await session.scalar(
            select(Notification)
            .where(
                Notification.user_id == user_id,
                Notification.kind == NotificationKind.STAGE_FAILED.value,
                Notification.read_at.is_(None),
                Notification.media_id == media_id,
                Notification.stage == stage,
            )
            .limit(1)
        )
        if open_one is not None:
            # The same stage on the same medium again: the newest words, not a second entry.
            open_one.detail = detail
            open_one.count += 1
            open_one.updated_at = now
        else:
            session.add(
                Notification(
                    user_id=user_id,
                    kind=NotificationKind.STAGE_FAILED.value,
                    actor_ids=[],
                    count=1,
                    media_id=media_id,
                    stage=stage,
                    detail=detail,
                    created_at=now,
                    updated_at=now,
                )
            )
        told.append(user_id)
    await session.flush()
    return told


async def everybody(session: AsyncSession) -> list[uuid.UUID]:
    """Every active account - for news everybody should hear, like new pictures."""
    rows = await session.scalars(select(User.id).where(User.status == UserStatus.ACTIVE))
    return list(rows)


async def unread_count(session: AsyncSession, user: User) -> int:
    count = await session.scalar(
        select(func.count())
        .select_from(Notification)
        .where(Notification.user_id == user.id, Notification.read_at.is_(None))
    )
    return int(count or 0)


@dataclass(frozen=True, slots=True)
class Entry:
    notification: Notification
    #: The people, most recent first.
    actors: list[str]
    media: Media | None
    album: Album | None
    #: The words of the comment it is about, when it is about one.
    excerpt: str | None


async def entries(
    session: AsyncSession, user: User, *, before: datetime | None = None, limit: int = 30
) -> tuple[list[Entry], datetime | None]:
    """The bell's list, newest first, and where the next page starts."""
    query = (
        select(Notification)
        .where(Notification.user_id == user.id)
        .order_by(Notification.updated_at.desc(), Notification.id)
        .limit(limit + 1)
    )
    if before is not None:
        query = query.where(Notification.updated_at < before)
    rows = list(await session.scalars(query))
    page = rows[:limit]

    people = await _names(session, [actor for row in page for actor in row.actor_ids])
    media = {
        item.id: item
        for item in await session.scalars(
            select(Media)
            .where(Media.id.in_([row.media_id for row in page if row.media_id]))
            .options(selectinload(Media.files))
        )
    }
    album_ids = {row.album_id for row in page if row.album_id} | {
        item.album_id for item in media.values()
    }
    albums = {
        item.id: item
        for item in await session.scalars(select(Album).where(Album.id.in_(album_ids)))
    }
    comments = {
        item.id: item
        for item in await session.scalars(
            select(Comment).where(
                Comment.id.in_([row.comment_id for row in page if row.comment_id])
            )
        )
    }

    result = []
    for row in page:
        found = media.get(row.media_id) if row.media_id else None
        album_id = row.album_id or (found.album_id if found else None)
        comment = comments.get(row.comment_id) if row.comment_id else None
        result.append(
            Entry(
                notification=row,
                actors=[people[actor] for actor in reversed(row.actor_ids) if actor in people],
                media=found,
                album=albums.get(album_id) if album_id else None,
                excerpt=comment.body if comment and comment.deleted_at is None else None,
            )
        )
    following = page[-1].updated_at if len(rows) > limit and page else None
    return result, following


async def _names(session: AsyncSession, ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not ids:
        return {}
    rows = await session.execute(select(User.id, User.display_name).where(User.id.in_(set(ids))))
    return {row.id: row.display_name for row in rows}


async def mark_read(
    session: AsyncSession, user: User, ids: Sequence[uuid.UUID] | None = None
) -> None:
    """Read: these, or all of them."""
    statement = update(Notification).where(
        Notification.user_id == user.id, Notification.read_at.is_(None)
    )
    if ids is not None:
        statement = statement.where(Notification.id.in_(ids))
    await session.execute(statement.values(read_at=datetime.now(UTC)))
    await session.commit()


# --- the person's own settings -------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Preferences:
    push: dict[PushEvent, bool]
    quiet_enabled: bool
    quiet_start: time
    quiet_end: time


async def preferences(session: AsyncSession, user: User) -> Preferences:
    """What this person chose, the defaults filling in whatever they never touched."""
    row = await session.get(NotificationSettings, user.id)
    chosen = row.push if row else {}
    return Preferences(
        push={
            event: bool(chosen.get(event.value, default))
            for event, default in PUSH_DEFAULTS.items()
        },
        quiet_enabled=row.quiet_enabled if row else True,
        quiet_start=row.quiet_start if row else DEFAULT_QUIET_START,
        quiet_end=row.quiet_end if row else DEFAULT_QUIET_END,
    )


async def save_preferences(
    session: AsyncSession,
    user: User,
    *,
    push: dict[PushEvent, bool],
    quiet_enabled: bool,
    quiet_start: time,
    quiet_end: time,
) -> Preferences:
    row = await session.get(NotificationSettings, user.id)
    if row is None:
        row = NotificationSettings(user_id=user.id)
        session.add(row)
    row.push = {event.value: on for event, on in push.items()}
    row.quiet_enabled = quiet_enabled
    row.quiet_start = quiet_start
    row.quiet_end = quiet_end
    await session.commit()
    return await preferences(session, user)


def is_quiet(prefs: Preferences, moment: time) -> bool:
    """Whether a push at this local time would fall into the quiet hours - which may run past
    midnight, like the default 22:00 to 07:00."""
    if not prefs.quiet_enabled or prefs.quiet_start == prefs.quiet_end:
        return False
    if prefs.quiet_start < prefs.quiet_end:
        return prefs.quiet_start <= moment < prefs.quiet_end
    return moment >= prefs.quiet_start or moment < prefs.quiet_end
