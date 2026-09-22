"""Comments: on media and albums, one level of answers, @mentions, likes.

Everybody signed in reads every comment. The author may change or delete their own; an admin
may delete any (moderation). A comment that was answered keeps its place when deleted - its text
goes, the answers stay readable. Mentions are kept beside the comment for the notifications.
"""

import re
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import ColumnElement, delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from muninn.models.notification import NotificationKind
from muninn.models.social import Comment, CommentMention, Like
from muninn.models.user import User, UserRole, UserStatus
from muninn.notify import service as notify
from muninn.social.service import Target, TargetKind, ensure_exists

#: Long enough for a story, short enough to stay a comment.
MAX_BODY = 2000

#: @anna, @boris.azar - a username as the login knows it.
_MENTION = re.compile(r"(?<![\w@])@([\w.-]{2,40})")


class CommentNotFoundError(Exception):
    pass


class NotAllowedError(Exception):
    """Somebody else's comment, and no admin."""


class InvalidCommentError(Exception):
    """Empty, too long, or answering something that is not a comment here."""


@dataclass(slots=True)
class Author:
    id: uuid.UUID
    display_name: str
    username: str


@dataclass(slots=True)
class CommentNode:
    comment: Comment
    author: Author
    likes: int = 0
    liked: bool = False
    replies: list["CommentNode"] = field(default_factory=list)


def _on(target: Target) -> ColumnElement[bool]:
    column = Comment.media_id if target.kind is TargetKind.MEDIA else Comment.album_id
    return column == target.id


def _clean(body: str) -> str:
    text = body.strip()
    if not text:
        raise InvalidCommentError("A comment needs a few words.")
    if len(text) > MAX_BODY:
        raise InvalidCommentError(f"At most {MAX_BODY} characters.")
    return text


async def _mentioned(session: AsyncSession, body: str, author: User) -> list[uuid.UUID]:
    """The active people a text names with @username - the author aside."""
    names = {match.lower() for match in _MENTION.findall(body)}
    if not names:
        return []
    rows = await session.scalars(
        select(User.id).where(
            func.lower(User.username).in_(names),
            User.status == UserStatus.ACTIVE,
            User.id != author.id,
        )
    )
    return list(rows)


async def _remember_mentions(
    session: AsyncSession, comment: Comment, author: User
) -> list[uuid.UUID]:
    """Keep who the comment names; returns the ones it did not name before."""
    before = set(
        await session.scalars(
            select(CommentMention.user_id).where(CommentMention.comment_id == comment.id)
        )
    )
    await session.execute(delete(CommentMention).where(CommentMention.comment_id == comment.id))
    named = await _mentioned(session, comment.body, author)
    for user_id in named:
        await session.execute(
            insert(CommentMention)
            .values(comment_id=comment.id, user_id=user_id)
            .on_conflict_do_nothing()
        )
    return [user_id for user_id in named if user_id not in before]


async def comments_of(session: AsyncSession, user: User, target: Target) -> list[CommentNode]:
    """Every comment on a medium or album, oldest first, answers under what they answer."""
    rows = (
        await session.execute(
            select(Comment, User)
            .join(User, User.id == Comment.user_id)
            .where(_on(target))
            .order_by(Comment.created_at, Comment.id)
        )
    ).all()
    if not rows:
        return []

    ids = [comment.id for comment, _ in rows]
    counted: dict[uuid.UUID, int] = {}
    for comment_id, count in (
        await session.execute(
            select(Like.comment_id, func.count())
            .where(Like.comment_id.in_(ids))
            .group_by(Like.comment_id)
        )
    ).all():
        if comment_id is not None:
            counted[comment_id] = int(count)
    mine = set(
        await session.scalars(
            select(Like.comment_id).where(Like.comment_id.in_(ids), Like.user_id == user.id)
        )
    )

    nodes: dict[uuid.UUID, CommentNode] = {}
    answers: dict[uuid.UUID, list[CommentNode]] = defaultdict(list)
    top: list[CommentNode] = []
    for comment, person in rows:
        node = CommentNode(
            comment=comment,
            author=Author(id=person.id, display_name=person.display_name, username=person.username),
            likes=counted.get(comment.id, 0),
            liked=comment.id in mine,
        )
        nodes[comment.id] = node
        if comment.parent_id is None:
            top.append(node)
        else:
            answers[comment.parent_id].append(node)

    for parent_id, replies in answers.items():
        if parent_id in nodes:
            nodes[parent_id].replies = replies
    return top


async def count_of(session: AsyncSession, target: Target) -> int:
    """How many comments are there to read - the deleted ones not."""
    count = await session.scalar(
        select(func.count()).select_from(Comment).where(_on(target), Comment.deleted_at.is_(None))
    )
    return int(count or 0)


async def add(
    session: AsyncSession,
    user: User,
    target: Target,
    body: str,
    *,
    parent_id: uuid.UUID | None = None,
) -> "Added":
    """Write a comment, or an answer. An answer to an answer joins the same conversation."""
    await ensure_exists(session, target)
    text = _clean(body)

    if parent_id is not None:
        parent = await session.get(Comment, parent_id)
        same_place = parent is not None and (
            parent.media_id == target.id
            if target.kind is TargetKind.MEDIA
            else parent.album_id == target.id
        )
        if parent is None or not same_place:
            raise InvalidCommentError("That comment is not here to answer.")
        # One level only: answering an answer answers what it answered.
        parent_id = parent.parent_id or parent.id

    comment = Comment(
        user_id=user.id,
        media_id=target.id if target.kind is TargetKind.MEDIA else None,
        album_id=target.id if target.kind is TargetKind.ALBUM else None,
        parent_id=parent_id,
        body=text,
    )
    session.add(comment)
    await session.flush()
    named = await _remember_mentions(session, comment, user)
    told = await _tell_about(session, comment, user, named)
    await session.commit()
    await session.refresh(comment)
    return Added(comment=comment, notified=told)


@dataclass(frozen=True, slots=True)
class Added:
    comment: Comment
    #: Who got a notification about it, for the live channel.
    notified: list[uuid.UUID]


async def _tell_about(
    session: AsyncSession, comment: Comment, author: User, named: list[uuid.UUID]
) -> list[uuid.UUID]:
    """An answer tells whom it answers, a mention whom it names, and a new comment everybody
    who keeps the thing in Walhall or talked about it before - each only once, the most
    personal reason first."""
    about = notify.About(
        media_id=comment.media_id, album_id=comment.album_id, comment_id=comment.id
    )
    told: list[uuid.UUID] = []
    if comment.parent_id is not None:
        parent = await session.get(Comment, comment.parent_id)
        if parent is not None and parent.user_id != author.id:
            told += await notify.notify(
                session, [parent.user_id], NotificationKind.REPLY, about, actor_id=author.id
            )
    told += await notify.notify(
        session,
        [user_id for user_id in named if user_id not in told],
        NotificationKind.MENTION,
        about,
        actor_id=author.id,
    )
    followers = await notify.followers(
        session, media_id=comment.media_id, album_id=comment.album_id
    )
    told += await notify.notify(
        session,
        [user_id for user_id in followers if user_id not in told],
        NotificationKind.COMMENT,
        about,
        actor_id=author.id,
    )
    return told


async def _own(session: AsyncSession, user: User, comment_id: uuid.UUID) -> Comment:
    comment = await session.get(Comment, comment_id)
    if comment is None or comment.deleted_at is not None:
        raise CommentNotFoundError
    return comment


async def edit(session: AsyncSession, user: User, comment_id: uuid.UUID, body: str) -> Comment:
    """Change one's own comment. Nobody changes somebody else's words, not even an admin."""
    comment = await _own(session, user, comment_id)
    if comment.user_id != user.id:
        raise NotAllowedError
    comment.body = _clean(body)
    comment.edited_at = datetime.now(UTC)
    named = await _remember_mentions(session, comment, user)
    # Somebody named only now hears of it; those named before already did.
    await notify.notify(
        session,
        named,
        NotificationKind.MENTION,
        notify.About(media_id=comment.media_id, album_id=comment.album_id, comment_id=comment.id),
        actor_id=user.id,
    )
    await session.commit()
    await session.refresh(comment)
    return comment


async def remove(session: AsyncSession, user: User, comment_id: uuid.UUID) -> Target:
    """Delete one's own comment - or, as an admin, anybody's. Returns where it was."""
    comment = await _own(session, user, comment_id)
    if comment.user_id != user.id and user.role is not UserRole.ADMIN:
        raise NotAllowedError
    target = target_of(comment)

    answered = await session.scalar(
        select(func.count()).select_from(Comment).where(Comment.parent_id == comment.id)
    )
    if answered:
        comment.body = ""
        comment.deleted_at = datetime.now(UTC)
        await session.execute(delete(CommentMention).where(CommentMention.comment_id == comment.id))
    else:
        parent_id = comment.parent_id
        await session.delete(comment)
        await session.flush()
        # A deleted comment kept only for its answers goes when its last answer goes.
        if parent_id is not None:
            parent = await session.get(Comment, parent_id)
            left = await session.scalar(
                select(func.count()).select_from(Comment).where(Comment.parent_id == parent_id)
            )
            if parent is not None and parent.deleted_at is not None and not left:
                await session.delete(parent)
    await session.commit()
    return target


async def like(session: AsyncSession, user: User, comment_id: uuid.UUID, *, on: bool) -> Comment:
    comment = await _own(session, user, comment_id)
    if on:
        added = await session.execute(
            insert(Like)
            .values(id=uuid.uuid4(), user_id=user.id, comment_id=comment.id)
            .on_conflict_do_nothing()
            .returning(Like.id)
        )
        if added.first() is not None:
            await notify.notify(
                session,
                [comment.user_id],
                NotificationKind.COMMENT_LIKE,
                notify.About(
                    media_id=comment.media_id, album_id=comment.album_id, comment_id=comment.id
                ),
                actor_id=user.id,
            )
    else:
        await session.execute(
            delete(Like).where(Like.user_id == user.id, Like.comment_id == comment.id)
        )
    await session.commit()
    return comment


async def likes_of(session: AsyncSession, user: User, comment_id: uuid.UUID) -> tuple[int, bool]:
    count = await session.scalar(
        select(func.count()).select_from(Like).where(Like.comment_id == comment_id)
    )
    mine = await session.scalar(
        select(func.count())
        .select_from(Like)
        .where(Like.comment_id == comment_id, Like.user_id == user.id)
    )
    return int(count or 0), bool(mine)


async def author_of(session: AsyncSession, comment: Comment) -> Author:
    person = await session.get(User, comment.user_id)
    assert person is not None  # noqa: S101 - the foreign key keeps it
    return Author(id=person.id, display_name=person.display_name, username=person.username)


def target_of(comment: Comment) -> Target:
    """The medium or album a comment belongs to."""
    if comment.media_id is not None:
        return Target(TargetKind.MEDIA, comment.media_id)
    assert comment.album_id is not None  # noqa: S101 - the check constraint keeps it
    return Target(TargetKind.ALBUM, comment.album_id)


async def mentionable(session: AsyncSession) -> list[Author]:
    """Everybody who can be named with @: the active accounts, by name."""
    rows = await session.scalars(
        select(User).where(User.status == UserStatus.ACTIVE).order_by(User.display_name)
    )
    return [
        Author(id=person.id, display_name=person.display_name, username=person.username)
        for person in rows
    ]
