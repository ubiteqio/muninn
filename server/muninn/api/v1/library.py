"""The published folders of the library (/admin/library, /admin/index).

The library itself - the folder the host mounts - is not chosen here. What is chosen is which
folders below it appear under Albums.
"""

import uuid
from contextlib import suppress
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from muninn.api.schemas.library import (
    ChangeView,
    ExclusionRequest,
    FolderEntry,
    FolderListing,
    IndexStatus,
    PublicationCreate,
    PublicationUpdate,
    PublicationView,
    SyncQueued,
    SyncRequest,
)
from muninn.core.config import Settings
from muninn.core.deps import AdminUser, get_redis, get_session, get_settings_from_state
from muninn.core.problem import ProblemError, problem_type
from muninn.huginn import jobs
from muninn.huginn.app import celery_app
from muninn.huginn.dispatch import WorkerUnreachableError, queue_sync
from muninn.library import service
from muninn.media import service as media_service
from muninn.models.change_log import SyncTrigger
from muninn.models.publication import Publication
from muninn.settings import service as settings_service

router = APIRouter(prefix="/admin", tags=["admin: library"])

SettingsDep = Annotated[Settings, Depends(get_settings_from_state)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]
RedisDep = Annotated[Redis, Depends(get_redis)]


async def _publication_or_404(session: AsyncSession, publication_id: uuid.UUID) -> Publication:
    try:
        return await service.get_publication(session, publication_id)
    except service.PublicationNotFoundError as error:
        raise ProblemError(
            status=status.HTTP_404_NOT_FOUND,
            type=problem_type("publication-not-found"),
            title="Folder not found",
            detail="No published folder with this id.",
        ) from error


def _not_allowed() -> ProblemError:
    return ProblemError(
        status=status.HTTP_400_BAD_REQUEST,
        type=problem_type("path-not-allowed"),
        title="Folder not allowed",
        detail="Choose a folder below the mounted library that exists inside the container.",
    )


@router.get("/library/publications", summary="The published folders")
async def list_publications(
    admin: AdminUser, session: SessionDep, redis: RedisDep
) -> list[PublicationView]:
    return [
        PublicationView.of(
            entry,
            await jobs.read_progress(redis, entry.id),
            await service.waiting_files(session, entry.relative_path),
        )
        for entry in await service.list_publications(session)
    ]


@router.post(
    "/library/publications",
    summary="Publish a folder as an album",
    status_code=status.HTTP_201_CREATED,
)
async def publish(
    payload: PublicationCreate, admin: AdminUser, session: SessionDep, settings: SettingsDep
) -> PublicationView:
    """The folder appears under Albums where the original sits, with everything below it.

    Reading it starts at once rather than at the next turn of the clock: publishing a folder is
    the moment somebody wants to see it.
    """
    try:
        publication = await service.publish(
            session, relative_path=payload.path, library_base=settings.library_path
        )
    except service.PathNotAllowedError as error:
        raise _not_allowed() from error
    except service.AlreadyPublishedError as error:
        raise ProblemError(
            status=status.HTTP_409_CONFLICT,
            type=problem_type("already-published"),
            title="Already published",
            detail="This folder, or a folder above it, is published already.",
        ) from error

    # Nothing is lost when the worker is down: the folder is published, and the clock picks
    # it up on its next turn.
    with suppress(WorkerUnreachableError):
        queue_sync(publication.id, trigger=SyncTrigger.MANUAL)

    return PublicationView.of(publication)


@router.patch("/library/publications/{publication_id}", summary="Pause or resume a folder")
async def update_publication(
    publication_id: uuid.UUID,
    payload: PublicationUpdate,
    admin: AdminUser,
    session: SessionDep,
) -> PublicationView:
    publication = await _publication_or_404(session, publication_id)
    updated = await service.update_publication(
        session, publication=publication, enabled=payload.enabled
    )
    return PublicationView.of(updated)


@router.delete(
    "/library/publications/{publication_id}",
    summary="Take a folder out of the albums",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def unpublish(
    publication_id: uuid.UUID,
    admin: AdminUser,
    session: SessionDep,
    settings: SettingsDep,
    redis: RedisDep,
) -> Response:
    """Removes the albums, the media and their previews, and stops the work on them.

    The stop comes first: a read that is still going would otherwise write albums back that
    were just taken away. The originals on the NAS are not touched.
    """
    publication = await _publication_or_404(session, publication_id)
    await jobs.request_cancel(redis, publication.id)

    forgotten = await service.unpublish(session, publication)

    await jobs.clear_progress(redis, publication.id)
    for task_id in await jobs.forget_media(redis, forgotten):
        celery_app.control.revoke(task_id, terminate=True, signal="SIGTERM")
        await jobs.clear_active(redis, task_id)

    await media_service.remove_derivatives(settings.derived_path, forgotten)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/library/publications/{publication_id}/exclusions",
    summary="Switch a subfolder of a published folder off",
)
async def exclude_folder(
    publication_id: uuid.UUID,
    payload: ExclusionRequest,
    admin: AdminUser,
    session: SessionDep,
    settings: SettingsDep,
    redis: RedisDep,
) -> PublicationView:
    """Its albums, media and previews leave Muninn, and it is not read any more. The rest of
    the published folder keeps everything it has; the NAS is not touched."""
    publication = await _publication_or_404(session, publication_id)
    try:
        forgotten = await service.exclude(session, publication, payload.relative_path)
    except service.NotInsideError as error:
        raise _not_inside() from error

    for task_id in await jobs.forget_media(redis, forgotten):
        celery_app.control.revoke(task_id, terminate=True, signal="SIGTERM")
        await jobs.clear_active(redis, task_id)
    await media_service.remove_derivatives(settings.derived_path, forgotten)
    await session.refresh(publication)
    return PublicationView.of(publication)


@router.delete(
    "/library/publications/{publication_id}/exclusions",
    summary="Switch a subfolder on again",
)
async def include_folder(
    publication_id: uuid.UUID, admin: AdminUser, session: SessionDep, path: str
) -> PublicationView:
    """It is read right away, and its albums come back."""
    publication = await _publication_or_404(session, publication_id)
    try:
        await service.include(session, publication, path)
    except service.NotInsideError as error:
        raise _not_inside() from error
    # Without the worker, the next read of the folder brings it back all the same.
    with suppress(WorkerUnreachableError):
        queue_sync(publication.id, trigger=SyncTrigger.MANUAL)
    await session.refresh(publication)
    return PublicationView.of(publication)


def _not_inside() -> ProblemError:
    return ProblemError(
        status=status.HTTP_422_UNPROCESSABLE_CONTENT,
        type=problem_type("not-inside"),
        title="Not a subfolder",
        detail="Only folders below a published folder can be switched off and on again.",
    )


@router.post(
    "/library/publications/{publication_id}/sync",
    summary="Read a folder now",
    status_code=status.HTTP_202_ACCEPTED,
)
async def sync_publication(
    publication_id: uuid.UUID, payload: SyncRequest, admin: AdminUser, session: SessionDep
) -> SyncQueued:
    """Hands the sync to Huginn and answers at once; the status endpoint shows how it went."""
    publication = await _publication_or_404(session, publication_id)

    try:
        task_id = queue_sync(
            publication.id,
            quick=payload.quick,
            confirm_deletions=payload.confirm_deletions,
            trigger=SyncTrigger.MANUAL,
        )
    except WorkerUnreachableError as error:
        raise ProblemError(
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
            type=problem_type("worker-unreachable"),
            title="Worker unreachable",
            detail="Huginn is not running, or Redis cannot be reached.",
        ) from error

    return SyncQueued(publication_id=publication.id, task_id=task_id)


@router.get("/library/browse", summary="Folders to choose from")
async def browse(
    admin: AdminUser, session: SessionDep, settings: SettingsDep, path: str = ""
) -> FolderListing:
    """Lists what the host has mounted, so a folder can be picked instead of typed."""
    try:
        current, entries = await service.browse(
            session, library_base=settings.library_path, relative_path=path
        )
    except service.PathNotAllowedError as error:
        raise _not_allowed() from error

    return FolderListing(
        relative_path=path.strip("/"),
        library_path=str(settings.library_path),
        current=FolderEntry.model_validate(current),
        items=[FolderEntry.model_validate(entry) for entry in entries],
    )


@router.get("/index/status", summary="How the library is doing")
async def index_status(
    admin: AdminUser, session: SessionDep, settings: SettingsDep, redis: RedisDep
) -> IndexStatus:
    counts = await service.index_counts(session)
    publications = await service.list_publications(session)
    stored = await settings_service.get_settings(session)

    last_quick = await jobs.last_quick_sync(redis)
    next_sync_at = last_quick + timedelta(seconds=stored.quick_sync_seconds) if last_quick else None

    return IndexStatus(
        publications=[
            PublicationView.of(
                entry,
                await jobs.read_progress(redis, entry.id),
                await service.waiting_files(session, entry.relative_path),
            )
            for entry in publications
        ],
        library_path=str(settings.library_path),
        next_sync_at=next_sync_at,
        albums=counts.albums,
        media=counts.media,
        missing=counts.missing,
        pending_metadata=counts.pending_metadata,
        pending_derivatives=counts.pending_derivatives,
    )


@router.get("/index/changes", summary="What the syncs found")
async def read_changes(
    admin: AdminUser,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    album_id: uuid.UUID | None = None,
) -> list[ChangeView]:
    """The newest lines first. The log is kept for 90 days."""
    entries = await service.recent_changes(session, limit=limit, album_id=album_id)
    return [ChangeView.of(entry) for entry in entries]
