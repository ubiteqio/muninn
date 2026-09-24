"""Mímir: searching the library (/search), and pictures like a given one."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from muninn.albums import service as albums_service
from muninn.api.schemas.media import MediaView
from muninn.api.schemas.search import (
    SearchAbilities,
    SearchHitView,
    SearchPage,
    SearchRequest,
    UnderstoodView,
    decode_offset,
    encode_offset,
)
from muninn.core.config import Settings
from muninn.core.deps import ActiveUser, get_redis, get_session, get_settings_from_state
from muninn.core.problem import ProblemError, problem_type
from muninn.media import service as media_service
from muninn.search import engine

router = APIRouter(tags=["search"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings_from_state)]
RedisDep = Annotated[Redis, Depends(get_redis)]


@router.get("/search/abilities", summary="What the search can look into")
async def read_abilities(user: ActiveUser, session: SessionDep, redis: RedisDep) -> SearchAbilities:
    """Without a picture or word model the search still finds names, places and periods; the app
    says so, and offers no "Ähnliche Bilder" where there is nothing to compare.

    ``ready`` is the other half: the models are set up, but is the machine answering? The app
    asks again now and then, so the field changes by itself when the machine comes back.
    """
    found = await engine.abilities(session, redis)
    return SearchAbilities(pictures=found.pictures, meanings=found.meanings, ready=found.ready)


@router.post("/search", summary="Search the library")
async def search(
    request: SearchRequest,
    user: ActiveUser,
    session: SessionDep,
    settings: SettingsDep,
    redis: RedisDep,
) -> SearchPage:
    """Words, periods and filters in, the best matches out - one page at a time.

    Periods and "Fotos"/"Videos" in the words are recognised and applied as filters; the rest
    is looked for in pictures, descriptions, what is said in videos, and names.
    """
    album_path = None
    if request.album_id is not None:
        try:
            album = await albums_service.get_album(session, request.album_id)
        except albums_service.AlbumNotFoundError as error:
            raise _not_found("album-not-found", "Album not found") from error
        album_path = album.album.relative_path

    found = await engine.find(
        session,
        redis,
        request.q,
        filters=engine.Filters(
            date_from=request.date_from,
            date_until=request.date_until,
            kind=request.kind,
            album_path=album_path,
            camera=request.camera,
        ),
        by_date=request.sort == "date",
        offset=_offset(request.cursor),
        limit=request.limit,
    )
    return _page(found, settings)


@router.get("/media/{media_id}/similar", summary="Pictures like this one")
async def similar(
    media_id: uuid.UUID,
    user: ActiveUser,
    session: SessionDep,
    settings: SettingsDep,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 60,
) -> SearchPage:
    """The nearest pictures by the picture model, the medium itself left out."""
    try:
        await media_service.get_media(session, media_id)
    except media_service.MediaNotFoundError as error:
        raise _not_found("media-not-found", "Media not found") from error

    found = await engine.find_similar(session, media_id, offset=_offset(cursor), limit=limit)
    return _page(found, settings)


def _page(found: engine.Found, settings: Settings) -> SearchPage:
    return SearchPage(
        items=[
            SearchHitView(
                media=MediaView.of(
                    found.media[hit.media_id],
                    library_path=str(settings.library_path),
                    secret=settings.jwt_secret,
                ),
                moment=hit.moment,
            )
            for hit in found.hits
            if hit.media_id in found.media
        ],
        next_cursor=encode_offset(found.next_offset) if found.next_offset is not None else None,
        understood=UnderstoodView(
            text=found.understood.text,
            date_from=found.understood.date_from,
            date_until=found.understood.date_until,
            kind=found.understood.kind,
            places=list(found.understood.places),
            persons=list(found.understood.persons),
        ),
        degraded=found.degraded,
    )


def _offset(cursor: str | None) -> int:
    if cursor is None:
        return 0
    try:
        return decode_offset(cursor)
    except ValueError as error:
        raise ProblemError(
            status=status.HTTP_400_BAD_REQUEST,
            type=problem_type("invalid-cursor"),
            title="Invalid cursor",
            detail="Pass the cursor exactly as the last page returned it.",
        ) from error


def _not_found(slug: str, title: str) -> ProblemError:
    return ProblemError(status=status.HTTP_404_NOT_FOUND, type=problem_type(slug), title=title)
