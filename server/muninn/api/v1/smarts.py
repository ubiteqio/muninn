"""Smarts: browsing a heap of media by what is in it (/smarts)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from muninn.api.schemas.media import MediaView
from muninn.api.schemas.people import FaceView
from muninn.api.schemas.smarts import (
    BuildRequest,
    BuildResult,
    ChapterList,
    ChapterMediaList,
    ChapterView,
    FaceStripView,
    ShelfMediaList,
    ShelfView,
    SmartsState,
    SmartsView,
)
from muninn.core.config import Settings
from muninn.core.deps import ActiveUser, AdminUser, get_session, get_settings_from_state
from muninn.core.problem import ProblemError, problem_type
from muninn.faces import listing
from muninn.models.album import Album
from muninn.models.media import Media, MediaStatus
from muninn.models.smart import SmartChapter, SmartChapterMedium
from muninn.smarts import service

router = APIRouter(prefix="/smarts", tags=["smarts"])

#: How many pictures a chapter card shows before it is opened.
COVER_SIZE = 6

#: How many faces the strip offers. More than this and nobody looks at the end of it.
FACES_SHOWN = 12


def _not_found() -> ProblemError:
    return ProblemError(
        status=status.HTTP_404_NOT_FOUND,
        type=problem_type("chapter-not-found"),
        title="Chapter not found",
        detail="No chapter with this id. They are built anew when an album changes.",
    )


async def _covers(
    session: AsyncSession, chapters: list[SmartChapter]
) -> dict[uuid.UUID, list[Media]]:
    """The first few media of every chapter, in one question rather than one per card."""
    if not chapters:
        return {}
    rows = await session.execute(
        select(SmartChapterMedium.chapter_id, Media)
        .join(Media, Media.id == SmartChapterMedium.media_id)
        .where(
            SmartChapterMedium.chapter_id.in_([chapter.id for chapter in chapters]),
            SmartChapterMedium.position < COVER_SIZE,
            Media.status == MediaStatus.ACTIVE,
        )
        .order_by(SmartChapterMedium.chapter_id, SmartChapterMedium.position)
        .options(selectinload(Media.files))
    )
    found: dict[uuid.UUID, list[Media]] = {}
    for chapter_id, medium in rows.tuples():
        found.setdefault(chapter_id, []).append(medium)
    return found


async def _titles(session: AsyncSession, chapters: list[SmartChapter]) -> dict[uuid.UUID, str]:
    if not chapters:
        return {}
    rows = await session.scalars(
        select(Album).where(Album.id.in_([chapter.album_id for chapter in chapters]))
    )
    return {album.id: album.display_title for album in rows}


def _view(
    chapter: SmartChapter,
    cover: list[Media],
    album_title: str,
    settings: Settings,
) -> ChapterView:
    return ChapterView(
        id=chapter.id,
        album_id=chapter.album_id,
        album_title=album_title,
        title=chapter.title,
        tags=list(chapter.tags),
        size=chapter.size,
        from_at=chapter.from_at,
        until_at=chapter.until_at,
        cover=[
            MediaView.of(
                medium, library_path=str(settings.library_path), secret=settings.jwt_secret
            )
            for medium in cover
        ],
    )


@router.get("", summary="What the library falls into")
async def read_smarts(
    user: ActiveUser,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings_from_state)],
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=60)] = 24,
) -> SmartsView:
    """Chapters, shelves and faces - everything the app needs before anything is chosen.

    Nothing here asks a machine: the groups were found by a worker from the vectors that are in
    the database anyway, so the Smarts work while the AI machine is switched off.
    """
    chapters = await service.chapters_of(session, limit=limit + 1, offset=offset)
    following = offset + limit if len(chapters) > limit else None
    chapters = chapters[:limit]
    covers = await _covers(session, chapters)
    titles = await _titles(session, chapters)
    people = await listing.persons(session)
    counted = await session.scalar(
        select(func.count())
        .select_from(Media)
        .where(Media.status == MediaStatus.ACTIVE, Media.duplicate_of.is_(None))
    )

    return SmartsView(
        media=int(counted or 0),
        chapters=[
            _view(chapter, covers.get(chapter.id, []), titles.get(chapter.album_id, ""), settings)
            for chapter in chapters
        ],
        shelves=[
            ShelfView(key=shelf.key, count=shelf.count) for shelf in await service.shelves(session)
        ],
        faces=[
            FaceStripView(
                person_id=summary.person.id,
                name=summary.person.name,
                count=summary.media,
                face=(
                    FaceView.of(summary.cover.face, secret=settings.jwt_secret)
                    if summary.cover
                    else None
                ),
            )
            for summary in people[:FACES_SHOWN]
            if summary.media > 0
        ],
        next_offset=following,
    )


@router.get("/chapters", summary="More chapters")
async def read_chapters(
    user: ActiveUser,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings_from_state)],
    album_id: uuid.UUID | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=60)] = 24,
) -> ChapterList:
    chapters = await service.chapters_of(session, album_id, limit=limit + 1, offset=offset)
    following = offset + limit if len(chapters) > limit else None
    chapters = chapters[:limit]
    covers = await _covers(session, chapters)
    titles = await _titles(session, chapters)
    return ChapterList(
        items=[
            _view(chapter, covers.get(chapter.id, []), titles.get(chapter.album_id, ""), settings)
            for chapter in chapters
        ],
        next_offset=following,
    )


@router.get("/chapters/{chapter_id}", summary="One chapter and its media")
async def read_chapter(
    chapter_id: uuid.UUID,
    user: ActiveUser,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings_from_state)],
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 60,
) -> ChapterMediaList:
    found = await service.chapter(session, chapter_id)
    if found is None:
        raise _not_found()
    media = await service.media_of(session, chapter_id, offset=offset, limit=limit + 1)
    following = offset + limit if len(media) > limit else None
    media = media[:limit]
    album = await service.album_of(session, found.album_id)
    return ChapterMediaList(
        chapter=_view(found, media[:COVER_SIZE], album.display_title if album else "", settings),
        items=[
            MediaView.of(
                medium, library_path=str(settings.library_path), secret=settings.jwt_secret
            )
            for medium in media
        ],
        next_offset=following,
    )


@router.get("/shelves/{key}", summary="What stands on one shelf")
async def read_shelf(
    key: str,
    user: ActiveUser,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings_from_state)],
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 60,
) -> ShelfMediaList:
    """Videos, documents, screenshots: everything with one trait, newest first."""
    try:
        media = await service.media_on_shelf(session, key, offset=offset, limit=limit + 1)
    except service.UnknownShelfError as error:
        raise ProblemError(
            status=status.HTTP_404_NOT_FOUND,
            type=problem_type("shelf-not-found"),
            title="Shelf not found",
            detail=f"Muninn has the shelves {', '.join(service.SHELVES)}.",
        ) from error
    following = offset + limit if len(media) > limit else None
    return ShelfMediaList(
        key=key,
        items=[
            MediaView.of(
                medium, library_path=str(settings.library_path), secret=settings.jwt_secret
            )
            for medium in media[:limit]
        ],
        next_offset=following,
    )


@router.get("/state", summary="What the Smarts hold")
async def read_state(
    admin: AdminUser,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SmartsState:
    """The figures beside the button in the engine room."""
    found = await service.state(session)
    return SmartsState(
        chapters=found.chapters,
        albums=found.albums,
        media=found.media,
        outstanding=found.outstanding,
        built_at=found.built_at,
        wanted=found.wanted,
    )


@router.post("/build", summary="Find chapters now", status_code=status.HTTP_200_OK)
async def build(
    request: BuildRequest,
    admin: AdminUser,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> BuildResult:
    """Build one album's chapters, or albums in turn until enough chapters have come out of it.

    Synchronous on purpose: an admin who presses it wants to see the result, and an album of a
    few thousand takes seconds. The albums without chapters come first, then the ones whose
    chapters are oldest, so pressing again carries on rather than repeating.
    """
    distance = request.distance or service.LOOK_DISTANCE
    if request.album_id is not None:
        built = await service.build_album(session, request.album_id, distance=distance)
        return BuildResult(
            albums=1,
            chapters=built.chapters,
            outstanding=len(await service.albums_to_build(session)),
        )

    done = await service.build_some(session, wanted=request.chapters, distance=distance)
    return BuildResult(albums=done.albums, chapters=done.chapters, outstanding=done.outstanding)
