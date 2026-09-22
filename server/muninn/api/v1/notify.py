"""The bell (/notifications) and the news of the start page (/activity)."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from muninn.api.schemas.notify import (
    ActivityView,
    AlbumRef,
    MarkRead,
    MediaRef,
    NotificationSettingsView,
    NotificationView,
    UnreadCount,
)
from muninn.api.schemas.pagination import Page
from muninn.core.config import Settings
from muninn.core.deps import ActiveUser, get_session, get_settings_from_state
from muninn.models.album import Album
from muninn.models.media import Media, shown
from muninn.models.notification import PushEvent
from muninn.models.user import User, UserRole
from muninn.notify import service
from muninn.social import service as social

router = APIRouter(tags=["notifications"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings_from_state)]


@router.get("/notifications", summary="What concerns you, newest first")
async def list_notifications(
    user: ActiveUser,
    session: SessionDep,
    settings: SettingsDep,
    before: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
) -> Page[NotificationView]:
    """``before`` goes on from the ``next_cursor`` of the page before."""
    found, following = await service.entries(session, user, before=before, limit=limit)
    return Page[NotificationView](
        items=[
            NotificationView(
                id=entry.notification.id,
                kind=entry.notification.kind,
                actors=entry.actors,
                count=entry.notification.count,
                created_at=entry.notification.created_at,
                updated_at=entry.notification.updated_at,
                read=entry.notification.read_at is not None,
                media=MediaRef.of(entry.media, secret=settings.jwt_secret) if entry.media else None,
                album=AlbumRef.of(entry.album) if entry.album else None,
                excerpt=entry.excerpt,
            )
            for entry in found
        ],
        next_cursor=following.isoformat() if following else None,
    )


@router.get("/notifications/unread", summary="How many notifications are unread")
async def unread(user: ActiveUser, session: SessionDep) -> UnreadCount:
    return UnreadCount(count=await service.unread_count(session, user))


@router.post(
    "/notifications/read",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Mark notifications as read",
)
async def mark_read(body: MarkRead, user: ActiveUser, session: SessionDep) -> Response:
    await service.mark_read(session, user, body.ids)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _visible(settings: service.Preferences, user: User) -> NotificationSettingsView:
    push = {
        event: on
        for event, on in settings.push.items()
        if event is not PushEvent.ADMIN_ALERTS or user.role is UserRole.ADMIN
    }
    return NotificationSettingsView(
        push=push,
        quiet_enabled=settings.quiet_enabled,
        quiet_start=settings.quiet_start,
        quiet_end=settings.quiet_end,
    )


@router.get("/me/notification-settings", summary="Which events come as push, and quiet hours")
async def read_settings(user: ActiveUser, session: SessionDep) -> NotificationSettingsView:
    return _visible(await service.preferences(session, user), user)


@router.put("/me/notification-settings", summary="Change what comes as push, and quiet hours")
async def write_settings(
    body: NotificationSettingsView, user: ActiveUser, session: SessionDep
) -> NotificationSettingsView:
    """An event left out keeps what it was. Admin alerts are for admins only."""
    current = await service.preferences(session, user)
    push = dict(current.push)
    for event, on in body.push.items():
        if event is PushEvent.ADMIN_ALERTS and user.role is not UserRole.ADMIN:
            continue
        push[event] = on
    saved = await service.save_preferences(
        session,
        user,
        push=push,
        quiet_enabled=body.quiet_enabled,
        quiet_start=body.quiet_start.replace(second=0, microsecond=0),
        quiet_end=body.quiet_end.replace(second=0, microsecond=0),
    )
    return _visible(saved, user)


@router.get("/activity", summary="What everybody has been doing, newest first")
async def activity(
    user: ActiveUser,
    session: SessionDep,
    settings: SettingsDep,
    before: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[ActivityView]:
    found = await social.happenings(session, before=before, limit=limit)
    names = await _names(session, [item.actor_id for item in found if item.actor_id])
    media = await _media(session, [item.media_id for item in found if item.media_id])
    albums = await _albums(
        session,
        [item.album_id for item in found if item.album_id]
        + [item.album_id for item in media.values()],
    )

    items = []
    for item in found:
        medium = media.get(item.media_id) if item.media_id else None
        if item.media_id and medium is None:
            continue  # gone from the NAS: nothing to show or lead to
        album_id = item.album_id or (medium.album_id if medium else None)
        album = albums.get(album_id) if album_id else None
        items.append(
            ActivityView(
                key=item.key,
                kind=item.kind,
                actor=names.get(item.actor_id) if item.actor_id else None,
                count=item.count,
                at=item.at,
                media=MediaRef.of(medium, secret=settings.jwt_secret) if medium else None,
                album=AlbumRef.of(album) if album else None,
                excerpt=item.excerpt,
                reaction=item.reaction,
            )
        )
    return Page[ActivityView](
        items=items,
        next_cursor=found[-1].at.isoformat() if len(found) == limit else None,
    )


async def _names(session: AsyncSession, ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not ids:
        return {}
    rows = await session.execute(select(User.id, User.display_name).where(User.id.in_(set(ids))))
    return {row.id: row.display_name for row in rows}


async def _media(session: AsyncSession, ids: list[uuid.UUID]) -> dict[uuid.UUID, Media]:
    if not ids:
        return {}
    rows = await session.scalars(select(Media).where(Media.id.in_(set(ids)), shown()))
    return {item.id: item for item in rows}


async def _albums(session: AsyncSession, ids: list[uuid.UUID]) -> dict[uuid.UUID, Album]:
    if not ids:
        return {}
    rows = await session.scalars(select(Album).where(Album.id.in_(set(ids))))
    return {item.id: item for item in rows}
