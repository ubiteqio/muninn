"""The album tree and the media inside an album (/albums)."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from muninn.albums import service
from muninn.api.schemas.albums import (
    AlbumSyncJob,
    AlbumSyncQueued,
    AlbumSyncRequest,
    AlbumTree,
    AlbumUpdate,
    AlbumView,
)
from muninn.api.schemas.media import MediaView
from muninn.api.schemas.pagination import Page, decode_cursor, encode_cursor
from muninn.api.schemas.places import AlbumPlaceUpdate
from muninn.core.config import Settings
from muninn.core.deps import (
    ActiveUser,
    get_redis,
    get_session,
    get_settings_from_state,
)
from muninn.core.problem import ProblemError, problem_type
from muninn.huginn import jobs
from muninn.huginn.dispatch import WorkerUnreachableError, queue_sync
from muninn.library import service as library_service
from muninn.models.change_log import SyncTrigger
from muninn.models.media import Media
from muninn.places import service as places_service

router = APIRouter(prefix="/albums", tags=["albums"])


def _not_found() -> ProblemError:
    return ProblemError(
        status=status.HTTP_404_NOT_FOUND,
        type=problem_type("album-not-found"),
        title="Album not found",
        detail="No album with this id.",
    )


@router.get("/tree", summary="The whole album tree")
async def read_tree(
    user: ActiveUser,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings_from_state)],
) -> AlbumTree:
    """Yggdrasil in one response. Folders without media are in it too, as collections."""
    nodes = await service.list_tree(session)
    return AlbumTree(items=[AlbumView.of(node, secret=settings.jwt_secret) for node in nodes])


@router.get("/{album_id}", summary="One album")
async def read_album(
    album_id: uuid.UUID,
    user: ActiveUser,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings_from_state)],
) -> AlbumView:
    try:
        node = await service.get_album(session, album_id)
    except service.AlbumNotFoundError as error:
        raise _not_found() from error
    return await _view(session, album_id, settings, node)


@router.patch("/{album_id}", summary="Change title or description")
async def update_album(
    album_id: uuid.UUID,
    payload: AlbumUpdate,
    user: ActiveUser,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings_from_state)],
) -> AlbumView:
    """Changes stay in Muninn; the folder on the NAS is read-only and stays as it is."""
    try:
        node = await service.get_album(session, album_id)
    except service.AlbumNotFoundError as error:
        raise _not_found() from error

    await service.update_album(
        session, album=node.album, title=payload.title, description=payload.description
    )
    return await _view(session, album_id, settings)


async def _view(
    session: AsyncSession,
    album_id: uuid.UUID,
    settings: Settings,
    node: service.AlbumNode | None = None,
) -> AlbumView:
    """One album with its place; the tree leaves the places out."""
    node = node or await service.get_album(session, album_id)
    place = (
        await places_service.get_place(session, node.album.place_id)
        if node.album.place_id is not None
        else None
    )
    return AlbumView.of(node, secret=settings.jwt_secret, place=place)


@router.put("/{album_id}/place", summary="Set or clear the place an album was taken in")
async def set_album_place(
    album_id: uuid.UUID,
    payload: AlbumPlaceUpdate,
    user: ActiveUser,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings_from_state)],
) -> AlbumView:
    """Its media without coordinates - and those of the albums below it without a place of
    their own - take this place, marked as estimated. Everybody signed in may set it."""
    try:
        node = await service.get_album(session, album_id)
    except service.AlbumNotFoundError as error:
        raise _not_found() from error
    if (
        payload.place_id is not None
        and await places_service.get_place(session, payload.place_id) is None
    ):
        raise ProblemError(
            status=status.HTTP_422_UNPROCESSABLE_CONTENT,
            type=problem_type("place-not-found"),
            title="Place not found",
            detail="Pick the place from /places.",
        )
    await places_service.set_album_place(session, node.album, payload.place_id)
    return await _view(session, album_id, settings)


@router.get("/{album_id}/media", summary="The media of an album")
async def list_album_media(
    album_id: uuid.UUID,
    user: ActiveUser,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings_from_state)],
    limit: Annotated[int, Query(ge=1, le=service.MAX_PAGE_SIZE)] = service.DEFAULT_PAGE_SIZE,
    cursor: str | None = None,
    before: str | None = None,
) -> Page[MediaView]:
    """Oldest first, one page at a time. Media whose files are gone are left out.

    ``cursor`` reads forwards from a page's ``next_cursor``, ``before`` backwards from its
    ``prev_cursor``. They are two directions of the same walk, so only one of them at a time.
    """
    try:
        node = await service.get_album(session, album_id)
    except service.AlbumNotFoundError as error:
        raise _not_found() from error

    if cursor is not None and before is not None:
        raise _invalid_cursor("Ask for one direction at a time: either cursor or before.")

    page = await service.list_media(
        session,
        album=node.album,
        limit=limit,
        cursor=_decoded(cursor),
        before=_decoded(before),
    )

    items = [
        MediaView.of(item, library_path=str(settings.library_path), secret=settings.jwt_secret)
        for item in page.items
    ]

    return Page[MediaView](
        items=items,
        next_cursor=_cursor_for(page.items[-1]) if page.has_next and page.items else None,
        prev_cursor=_cursor_for(page.items[0]) if page.has_previous and page.items else None,
    )


def _decoded(cursor: str | None) -> tuple[datetime, uuid.UUID] | None:
    if cursor is None:
        return None
    try:
        return decode_cursor(cursor)
    except ValueError as error:
        raise _invalid_cursor("Use a cursor this endpoint handed out.") from error


def _cursor_for(media: Media) -> str:
    return encode_cursor(service.cursor_value(media), media.id)


def _invalid_cursor(detail: str) -> ProblemError:
    return ProblemError(
        status=status.HTTP_400_BAD_REQUEST,
        type=problem_type("invalid-cursor"),
        title="Invalid cursor",
        detail=detail,
    )


@router.post(
    "/{album_id}/sync", summary="Sync this album with the NAS", status_code=status.HTTP_202_ACCEPTED
)
async def sync_album(
    album_id: uuid.UUID,
    payload: AlbumSyncRequest,
    user: ActiveUser,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AlbumSyncQueued:
    """Open to everybody signed in: it reads the folder and never writes to the NAS.

    Because this sync reads its folder completely, it is responsible for it and may also decide
    that something is gone - within the thresholds of the safety net, which then count for this
    album rather than the whole root.
    """
    try:
        node = await service.get_album(session, album_id)
    except service.AlbumNotFoundError as error:
        raise _not_found() from error

    publication = await library_service.covering_publication(session, node.album.relative_path)
    if publication is None:
        raise ProblemError(
            status=status.HTTP_409_CONFLICT,
            type=problem_type("album-not-published"),
            title="Album not published",
            detail="This album only leads to published folders; sync those instead.",
        )

    job_id = uuid.uuid4().hex
    try:
        task_id = queue_sync(
            publication.id,
            trigger=SyncTrigger.MANUAL,
            scope_path=node.album.relative_path,
            with_children=payload.with_children,
            job_id=job_id,
        )
    except WorkerUnreachableError as error:
        raise ProblemError(
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
            type=problem_type("worker-unreachable"),
            title="Worker unreachable",
            detail="Huginn is not running, or Redis cannot be reached.",
        ) from error

    return AlbumSyncQueued(album_id=album_id, job_id=job_id, task_id=task_id)


@router.get("/{album_id}/sync/{job_id}", summary="How the requested sync is going")
async def read_sync_job(
    album_id: uuid.UUID,
    job_id: str,
    user: ActiveUser,
    redis: Annotated[Redis, Depends(get_redis)],
) -> AlbumSyncJob:
    """Until the WebSocket of milestone 5 exists, the app asks now and then."""
    stored = await jobs.read_job(redis, job_id)
    if stored is None:
        raise ProblemError(
            status=status.HTTP_404_NOT_FOUND,
            type=problem_type("sync-job-not-found"),
            title="Sync job not found",
            detail="This job is unknown or older than an hour.",
        )

    return AlbumSyncJob(
        job_id=job_id,
        state=str(stored.get("state", "running")),
        updated_at=stored.get("updated_at"),
        result=stored.get("result"),
    )
