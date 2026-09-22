"""Likes on media and albums, and Walhall - everybody's own favourites."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from muninn.albums import service as albums_service
from muninn.api.schemas.albums import AlbumView
from muninn.api.schemas.media import MediaView
from muninn.api.schemas.pagination import Page
from muninn.api.schemas.social import (
    CommentEdit,
    CommentLikes,
    CommentList,
    CommentView,
    FavoriteTarget,
    LikeRequest,
    NewComment,
    PersonView,
    SocialView,
)
from muninn.core.config import Settings
from muninn.core.deps import ActiveUser, get_redis, get_session, get_settings_from_state
from muninn.core.problem import ProblemError, problem_type
from muninn.models.social import Reaction
from muninn.models.user import User
from muninn.notify import events
from muninn.social import comments, service
from muninn.social.service import Target, TargetKind

router = APIRouter(tags=["social"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
RedisDep = Annotated[Redis, Depends(get_redis)]
SettingsDep = Annotated[Settings, Depends(get_settings_from_state)]


def _not_found() -> ProblemError:
    return ProblemError(
        status=status.HTTP_404_NOT_FOUND,
        type=problem_type("not-found"),
        title="Not found",
        detail="No medium or album with this id.",
    )


async def _changed(
    session: AsyncSession, redis: Redis, user: User, target: Target, *, likes: bool
) -> SocialView:
    """The new state for whoever changed it, and a word to everybody else looking at it."""
    if likes:
        # Likes are for everybody to see, so every open page may ask again. Favourites are
        # private and change nothing anybody else sees.
        await events.publish(
            redis, events.SOCIAL_TOPIC, kind="likes", target=target.kind.value, id=str(target.id)
        )
    return SocialView.of(await service.summary(session, user, target))


async def _like(
    session: AsyncSession,
    redis: Redis,
    user: User,
    target: Target,
    *,
    on: bool,
    reaction: Reaction = Reaction.HEART,
) -> SocialView:
    try:
        if on:
            await service.like(session, user, target, reaction)
        else:
            await service.unlike(session, user, target)
    except service.TargetNotFoundError as error:
        raise _not_found() from error
    return await _changed(session, redis, user, target, likes=True)


@router.post("/media/{media_id}/like", summary="React to a medium")
async def like_media(
    media_id: uuid.UUID,
    user: ActiveUser,
    session: SessionDep,
    redis: RedisDep,
    body: LikeRequest | None = None,
) -> SocialView:
    """A heart unless another reaction is given. One per person: a new one replaces the old."""
    return await _like(
        session,
        redis,
        user,
        Target(TargetKind.MEDIA, media_id),
        on=True,
        reaction=body.reaction if body else Reaction.HEART,
    )


@router.delete("/media/{media_id}/like", summary="Take back a like on a medium")
async def unlike_media(
    media_id: uuid.UUID, user: ActiveUser, session: SessionDep, redis: RedisDep
) -> SocialView:
    return await _like(session, redis, user, Target(TargetKind.MEDIA, media_id), on=False)


@router.post("/albums/{album_id}/like", summary="Like an album")
async def like_album(
    album_id: uuid.UUID, user: ActiveUser, session: SessionDep, redis: RedisDep
) -> SocialView:
    return await _like(session, redis, user, Target(TargetKind.ALBUM, album_id), on=True)


@router.delete("/albums/{album_id}/like", summary="Take back a like on an album")
async def unlike_album(
    album_id: uuid.UUID, user: ActiveUser, session: SessionDep, redis: RedisDep
) -> SocialView:
    return await _like(session, redis, user, Target(TargetKind.ALBUM, album_id), on=False)


@router.get("/media/{media_id}/social", summary="Likes and favourite of a medium")
async def media_social(media_id: uuid.UUID, user: ActiveUser, session: SessionDep) -> SocialView:
    return SocialView.of(await service.summary(session, user, Target(TargetKind.MEDIA, media_id)))


@router.get("/albums/{album_id}/social", summary="Likes and favourite of an album")
async def album_social(album_id: uuid.UUID, user: ActiveUser, session: SessionDep) -> SocialView:
    return SocialView.of(await service.summary(session, user, Target(TargetKind.ALBUM, album_id)))


@router.post("/favorites", summary="Keep a medium or album in Walhall")
async def add_favorite(
    body: FavoriteTarget, user: ActiveUser, session: SessionDep, redis: RedisDep
) -> SocialView:
    try:
        await service.favorite(session, user, body.target())
    except service.TargetNotFoundError as error:
        raise _not_found() from error
    return await _changed(session, redis, user, body.target(), likes=False)


@router.delete("/favorites", summary="Take a medium or album out of Walhall")
async def remove_favorite(
    body: FavoriteTarget, user: ActiveUser, session: SessionDep, redis: RedisDep
) -> SocialView:
    await service.unfavorite(session, user, body.target())
    return await _changed(session, redis, user, body.target(), likes=False)


@router.get("/favorites/media", summary="Walhall's pictures and videos")
async def favorite_media(
    user: ActiveUser,
    session: SessionDep,
    settings: SettingsDep,
    before: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 60,
) -> Page[MediaView]:
    """The media this person keeps, the most recently kept first. ``before`` goes on from the
    ``next_cursor`` of the page before."""
    page = await service.favorite_media(session, user, before=before, limit=limit)
    return Page[MediaView](
        items=[
            MediaView.of(media, library_path=str(settings.library_path), secret=settings.jwt_secret)
            for media in page.media
        ],
        next_cursor=page.next_before.isoformat() if page.next_before else None,
    )


@router.get("/favorites/albums", summary="Walhall's albums")
async def favorite_albums(
    user: ActiveUser, session: SessionDep, settings: SettingsDep
) -> list[AlbumView]:
    kept = await service.favorite_album_ids(session, user)
    nodes = {node.album.id: node for node in await albums_service.list_tree(session)}
    return [
        AlbumView.of(nodes[album_id], secret=settings.jwt_secret)
        for album_id in kept
        if album_id in nodes
    ]


# --- comments -------------------------------------------------------------------------------


def _comment_not_found() -> ProblemError:
    return ProblemError(
        status=status.HTTP_404_NOT_FOUND,
        type=problem_type("comment-not-found"),
        title="Comment not found",
        detail="No comment with this id, or it was deleted.",
    )


def _not_allowed() -> ProblemError:
    return ProblemError(
        status=status.HTTP_403_FORBIDDEN,
        type=problem_type("not-your-comment"),
        title="Not your comment",
        detail="Only its author changes a comment; only its author or an admin deletes it.",
    )


def _invalid(error: comments.InvalidCommentError) -> ProblemError:
    return ProblemError(
        status=status.HTTP_422_UNPROCESSABLE_CONTENT,
        type=problem_type("invalid-comment"),
        title="Invalid comment",
        detail=str(error),
    )


async def _comments_changed(redis: Redis, target: Target) -> None:
    await events.publish(
        redis, events.SOCIAL_TOPIC, kind="comments", target=target.kind.value, id=str(target.id)
    )


async def _list(session: AsyncSession, user: User, target: Target) -> CommentList:
    nodes = await comments.comments_of(session, user, target)
    return CommentList(
        items=[CommentView.of(node, user) for node in nodes],
        count=await comments.count_of(session, target),
    )


async def _add(
    session: AsyncSession, redis: Redis, user: User, target: Target, body: NewComment
) -> CommentView:
    try:
        added = await comments.add(session, user, target, body.body, parent_id=body.parent_id)
    except service.TargetNotFoundError as error:
        raise _not_found() from error
    except comments.InvalidCommentError as error:
        raise _invalid(error) from error
    comment = added.comment
    await _comments_changed(redis, target)
    await events.announce_notifications(redis, added.notified)
    author = await comments.author_of(session, comment)
    return CommentView.of(comments.CommentNode(comment=comment, author=author), user)


@router.get("/media/{media_id}/comments", summary="The comments of a medium")
async def media_comments(media_id: uuid.UUID, user: ActiveUser, session: SessionDep) -> CommentList:
    return await _list(session, user, Target(TargetKind.MEDIA, media_id))


@router.get("/albums/{album_id}/comments", summary="The comments of an album")
async def album_comments(album_id: uuid.UUID, user: ActiveUser, session: SessionDep) -> CommentList:
    return await _list(session, user, Target(TargetKind.ALBUM, album_id))


@router.post(
    "/media/{media_id}/comments",
    status_code=status.HTTP_201_CREATED,
    summary="Comment on a medium, or answer a comment",
)
async def comment_media(
    media_id: uuid.UUID, body: NewComment, user: ActiveUser, session: SessionDep, redis: RedisDep
) -> CommentView:
    return await _add(session, redis, user, Target(TargetKind.MEDIA, media_id), body)


@router.post(
    "/albums/{album_id}/comments",
    status_code=status.HTTP_201_CREATED,
    summary="Comment on an album, or answer a comment",
)
async def comment_album(
    album_id: uuid.UUID, body: NewComment, user: ActiveUser, session: SessionDep, redis: RedisDep
) -> CommentView:
    return await _add(session, redis, user, Target(TargetKind.ALBUM, album_id), body)


@router.patch("/comments/{comment_id}", summary="Change your own comment")
async def edit_comment(
    comment_id: uuid.UUID,
    body: CommentEdit,
    user: ActiveUser,
    session: SessionDep,
    redis: RedisDep,
) -> CommentView:
    try:
        comment = await comments.edit(session, user, comment_id, body.body)
    except comments.CommentNotFoundError as error:
        raise _comment_not_found() from error
    except comments.NotAllowedError as error:
        raise _not_allowed() from error
    except comments.InvalidCommentError as error:
        raise _invalid(error) from error
    await _comments_changed(redis, comments.target_of(comment))
    likes, liked = await comments.likes_of(session, user, comment.id)
    author = await comments.author_of(session, comment)
    return CommentView.of(
        comments.CommentNode(comment=comment, author=author, likes=likes, liked=liked), user
    )


@router.delete(
    "/comments/{comment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete your own comment - or, as an admin, any",
)
async def delete_comment(
    comment_id: uuid.UUID, user: ActiveUser, session: SessionDep, redis: RedisDep
) -> Response:
    try:
        target = await comments.remove(session, user, comment_id)
    except comments.CommentNotFoundError as error:
        raise _comment_not_found() from error
    except comments.NotAllowedError as error:
        raise _not_allowed() from error
    await _comments_changed(redis, target)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def _like_comment(
    session: AsyncSession, redis: Redis, user: User, comment_id: uuid.UUID, *, on: bool
) -> CommentLikes:
    try:
        comment = await comments.like(session, user, comment_id, on=on)
    except comments.CommentNotFoundError as error:
        raise _comment_not_found() from error
    await _comments_changed(redis, comments.target_of(comment))
    if on and comment.user_id != user.id:
        await events.announce_notifications(redis, [comment.user_id])
    likes, liked = await comments.likes_of(session, user, comment_id)
    return CommentLikes(likes=likes, liked=liked)


@router.post("/comments/{comment_id}/like", summary="Like a comment")
async def like_comment(
    comment_id: uuid.UUID, user: ActiveUser, session: SessionDep, redis: RedisDep
) -> CommentLikes:
    return await _like_comment(session, redis, user, comment_id, on=True)


@router.delete("/comments/{comment_id}/like", summary="Take back a like on a comment")
async def unlike_comment(
    comment_id: uuid.UUID, user: ActiveUser, session: SessionDep, redis: RedisDep
) -> CommentLikes:
    return await _like_comment(session, redis, user, comment_id, on=False)


@router.get("/people/mentionable", summary="Who can be named with @")
async def mentionable(user: ActiveUser, session: SessionDep) -> list[PersonView]:
    return [PersonView.of(person) for person in await comments.mentionable(session)]
