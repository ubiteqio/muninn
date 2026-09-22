"""Midgard: the map of where the media were taken (/map)."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from muninn.albums.service import cursor_value
from muninn.api.schemas.media import MediaView
from muninn.api.schemas.pagination import Page, decode_cursor, encode_cursor
from muninn.api.schemas.places import BoundsView, ClusterList, ClusterView, PlaceList, PlaceView
from muninn.core.config import Settings
from muninn.core.deps import ActiveUser, get_session, get_settings_from_state
from muninn.core.problem import ProblemError, problem_type
from muninn.core.signing import sign_media
from muninn.places import service

router = APIRouter(prefix="/map", tags=["map"])
places_router = APIRouter(prefix="/places", tags=["map"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings_from_state)]
West = Annotated[float, Query(ge=-180, le=180)]
East = Annotated[float, Query(ge=-180, le=180)]
South = Annotated[float, Query(ge=-90, le=90)]
North = Annotated[float, Query(ge=-90, le=90)]


@router.get("/clusters", summary="The media of a part of the map, as clusters")
async def read_clusters(
    user: ActiveUser,
    session: SessionDep,
    settings: SettingsDep,
    west: West,
    south: South,
    east: East,
    north: North,
    zoom: Annotated[float, Query(ge=0, le=22)],
) -> ClusterList:
    """Points close together at this zoom level come as one cluster with a count.

    The app sends the visible part of the map; a map wrapped around the date line is asked for
    in two parts.
    """
    found = await service.clusters(session, _area(west, south, east, north), zoom=zoom)
    return ClusterList(
        items=[
            ClusterView(
                latitude=cluster.latitude,
                longitude=cluster.longitude,
                count=cluster.count,
                cover_id=cluster.cover_id,
                cover_thumb=_thumb(cluster.cover_id, settings)
                if cluster.cover_has_thumbnail
                else None,
                bounds=BoundsView(
                    west=cluster.bounds.west,
                    south=cluster.bounds.south,
                    east=cluster.bounds.east,
                    north=cluster.bounds.north,
                ),
            )
            for cluster in found
        ]
    )


@router.get("/media", summary="The media taken in a part of the map")
async def read_media(
    user: ActiveUser,
    session: SessionDep,
    settings: SettingsDep,
    west: West,
    south: South,
    east: East,
    north: North,
    limit: Annotated[int, Query(ge=1, le=service.MAX_PAGE_SIZE)] = 60,
    cursor: str | None = None,
) -> Page[MediaView]:
    """Newest first, one page at a time: what a tapped cluster holds."""
    page = await service.media_in(
        session, _area(west, south, east, north), limit=limit, cursor=_decoded(cursor)
    )
    return Page[MediaView](
        items=[
            MediaView.of(item, library_path=str(settings.library_path), secret=settings.jwt_secret)
            for item in page.items
        ],
        next_cursor=encode_cursor(cursor_value(page.items[-1]), page.items[-1].id)
        if page.has_next and page.items
        else None,
    )


def _area(west: float, south: float, east: float, north: float) -> service.Area:
    if west > east or south > north:
        raise ProblemError(
            status=status.HTTP_422_UNPROCESSABLE_CONTENT,
            type=problem_type("invalid-area"),
            title="Invalid area",
            detail="West must not lie east of east, nor south north of north.",
        )
    return service.Area(west=west, south=south, east=east, north=north)


def _thumb(media_id: uuid.UUID, settings: Settings) -> str:
    token = sign_media(media_id, "thumb", secret=settings.jwt_secret)
    return f"/api/v1/media/{media_id}/thumb?token={token}"


def _decoded(cursor: str | None) -> tuple[datetime, uuid.UUID] | None:
    if cursor is None:
        return None
    try:
        return decode_cursor(cursor)
    except ValueError as error:
        raise ProblemError(
            status=status.HTTP_400_BAD_REQUEST,
            type=problem_type("invalid-cursor"),
            title="Invalid cursor",
            detail="Use a cursor this endpoint handed out.",
        ) from error


@places_router.get("", summary="Towns by name, for giving an album its place")
async def suggest_places(
    user: ActiveUser,
    session: SessionDep,
    q: Annotated[str, Query(max_length=100)] = "",
    limit: Annotated[int, Query(ge=1, le=20)] = 10,
) -> PlaceList:
    """Towns whose German name begins like this, or that are called exactly this in any
    language; the larger first."""
    return PlaceList(
        items=[PlaceView.of(place) for place in await service.suggest(session, q, limit=limit)]
    )
