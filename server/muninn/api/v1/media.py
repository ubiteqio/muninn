"""The timeline, a single medium, and its files (/media)."""

import mimetypes
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from muninn.analysis import service as analysis_service
from muninn.analysis import transcripts
from muninn.api.schemas.media import (
    MarkView,
    MediaStagesView,
    MediaStageView,
    MediaView,
    PeriodCoverView,
    PeriodView,
    TimelineShapeView,
)
from muninn.api.schemas.pagination import Page, decode_cursor, encode_cursor
from muninn.api.schemas.social import SocialView
from muninn.core.config import Settings
from muninn.core.deps import (
    ActiveUser,
    AdminUser,
    OptionalUser,
    get_session,
    get_settings_from_state,
)
from muninn.core.problem import ProblemError, problem_type
from muninn.core.signing import sign_media, verify_media
from muninn.huginn import stages
from muninn.media import service
from muninn.models.media import Media, MediaStatus
from muninn.places import service as places_service
from muninn.social import service as social_service
from muninn.social.service import Target, TargetKind

router = APIRouter(prefix="/media", tags=["media"])

SettingsDep = Annotated[Settings, Depends(get_settings_from_state)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]

#: The variants an address can point at.
VARIANTS = ("thumb", "preview", "video", "poster", "original")


def _not_found() -> ProblemError:
    return ProblemError(
        status=status.HTTP_404_NOT_FOUND,
        type=problem_type("media-not-found"),
        title="Medium not found",
        detail="No medium with this id.",
    )


@router.get("", summary="The timeline: every medium, newest first")
async def list_timeline(
    user: ActiveUser,
    session: SessionDep,
    settings: SettingsDep,
    limit: Annotated[int, Query(ge=1, le=service.MAX_PAGE_SIZE)] = service.DEFAULT_PAGE_SIZE,
    cursor: str | None = None,
    before: str | None = None,
    at: datetime | None = None,
    month: Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}$")] = None,
) -> Page[MediaView]:
    """One window of the timeline, across all albums.

    ``month`` ("2014-08") keeps the walk inside that month. ``cursor`` walks on into the past,
    ``before`` back towards today, ``at`` jumps to a moment - three ways into the same walk, so
    only one of them at a time.
    """
    if sum(value is not None for value in (cursor, before, at)) > 1:
        raise _invalid_cursor("Ask for one direction at a time: cursor, before or at.")

    page = await service.list_timeline(
        session,
        limit=limit,
        cursor=_decoded(cursor),
        before=_decoded(before),
        at=at,
        month=None if month is None else date.fromisoformat(f"{month}-01"),
    )

    return Page[MediaView](
        items=[
            MediaView.of(item, library_path=str(settings.library_path), secret=settings.jwt_secret)
            for item in page.items
        ],
        next_cursor=_cursor_for(page.items[-1]) if page.has_next and page.items else None,
        prev_cursor=_cursor_for(page.items[0]) if page.has_previous and page.items else None,
    )


@router.get("/marks", summary="How much every year, month or day holds")
async def read_marks(
    user: ActiveUser,
    session: SessionDep,
    by: service.Granularity = service.Granularity.MONTH,
    year: Annotated[int | None, Query(ge=1800, le=2400)] = None,
) -> TimelineShapeView:
    """What a level of the timeline is built from. One aggregate, no paging.

    Ask for days one year at a time: a library of 26 years has some nine thousand of them.
    """
    shape = await service.timeline_shape(session, by=by, year=year)
    return TimelineShapeView(
        by=shape.by,
        total=shape.total,
        marks=[MarkView(start=mark.start, count=mark.count) for mark in shape.marks],
    )


@router.get("/periods", summary="The years or months of the overview, with their covers")
async def read_periods(
    user: ActiveUser,
    session: SessionDep,
    settings: SettingsDep,
    by: service.Granularity = service.Granularity.YEAR,
    year: Annotated[int | None, Query(ge=1800, le=2400)] = None,
    covers: Annotated[int, Query(ge=1, le=9)] = 4,
) -> list[PeriodView]:
    """What the overview shows: a card per year or month with a few pictures out of it."""
    periods = await service.list_periods(session, by=by, year=year, covers=covers)

    return [
        PeriodView(
            start=period.start,
            count=period.count,
            covers=[
                PeriodCoverView(
                    id=media_id,
                    thumb=f"/api/v1/media/{media_id}/thumb"
                    f"?token={sign_media(media_id, 'thumb', secret=settings.jwt_secret)}",
                )
                for media_id in period.covers
            ],
        )
        for period in periods
    ]


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


@router.get("/{media_id}", summary="One medium")
async def read_media(
    media_id: uuid.UUID,
    user: ActiveUser,
    session: SessionDep,
    settings: SettingsDep,
) -> MediaView:
    """Everything the index knows, including where the original lies and how to load the files."""
    try:
        media = await service.get_media(session, media_id)
    except service.MediaNotFoundError as error:
        raise _not_found() from error

    return MediaView.of(
        media,
        library_path=str(settings.library_path),
        secret=settings.jwt_secret,
        analysis=await analysis_service.get_analysis(session, media_id),
        frames=await analysis_service.frames_of_video(session, media_id),
        transcript=await transcripts.get_transcript(session, media_id),
        social=SocialView.of(
            await social_service.summary(session, user, Target(TargetKind.MEDIA, media_id))
        ),
        place=await places_service.place_of(session, media),
    )


@router.get("/{media_id}/stages", summary="What the pipeline did to this medium")
async def read_stages(
    media_id: uuid.UUID, admin: AdminUser, session: SessionDep
) -> MediaStagesView:
    """Every step and where this medium stands in it: done, still open, or given up on."""
    try:
        media = await service.get_media(session, media_id)
    except service.MediaNotFoundError as error:
        raise _not_found() from error

    return MediaStagesView(
        media_id=media_id,
        stages=[MediaStageView(**vars(state)) for state in await stages.of_medium(session, media)],
    )


@router.post(
    "/{media_id}/stages/{stage}",
    summary="Do one step again",
    status_code=status.HTTP_202_ACCEPTED,
)
async def run_stage(
    media_id: uuid.UUID, stage: str, admin: AdminUser, session: SessionDep
) -> MediaStagesView:
    """What the step wrote is dropped and the worker gets the medium now.

    Failed attempts are forgotten with it: whoever asks has usually just changed something -
    a better model, a file that was still being copied - and old failures should not stand in
    the way.
    """
    try:
        media = await service.get_media(session, media_id)
    except service.MediaNotFoundError as error:
        raise _not_found() from error

    try:
        await stages.run(session, media, stage)
    except stages.UnknownStageError as error:
        raise ProblemError(
            status=status.HTTP_404_NOT_FOUND,
            type=problem_type("stage-not-found"),
            title="Stage not found",
            detail=f"The pipeline has no step called {stage!r}.",
        ) from error

    return MediaStagesView(
        media_id=media_id,
        stages=[MediaStageView(**vars(state)) for state in await stages.of_medium(session, media)],
    )


@router.get("/{media_id}/{variant}", summary="Thumbnail, preview, video or original")
async def read_file(
    media_id: uuid.UUID,
    variant: str,
    user: OptionalUser,
    session: SessionDep,
    settings: SettingsDep,
    token: Annotated[str | None, Query()] = None,
    download: Annotated[bool, Query()] = False,
) -> FileResponse:
    """Signed addresses let the browser cache; the native app sends its token in the header.

    Videos and originals are streamed with range requests, so seeking works. With ``download``
    the file arrives as a download under the name it carries on the NAS, instead of being shown
    in the tab.
    """
    if variant not in VARIANTS:
        raise _not_found()

    signed = token is not None and verify_media(
        token, media_id, variant, secret=settings.jwt_secret
    )
    if not signed and user is None:
        raise ProblemError(
            status=status.HTTP_401_UNAUTHORIZED,
            type=problem_type("not-authenticated"),
            title="Not authenticated",
            detail="Use a signed address or a bearer access token.",
        )

    media = await session.get(Media, media_id)
    if media is None or media.status is not MediaStatus.ACTIVE:
        raise _not_found()

    path = _path_of(media, variant, settings)
    if path is None or not path.exists():
        raise ProblemError(
            status=status.HTTP_404_NOT_FOUND,
            type=problem_type("variant-not-ready"),
            title="Not ready",
            detail="This version of the medium does not exist (yet).",
        )

    media_type, _ = mimetypes.guess_type(path.name)
    filename = _download_name(media, variant, path) if download else None
    # The file is sent after this returns - a video for minutes. The database connection goes
    # back to the pool now, or a page full of thumbnails would take every connection there is.
    await session.close()
    return FileResponse(
        path,
        media_type=media_type or "application/octet-stream",
        # Signed addresses are meant to be cached; that is what they are for.
        headers={"Cache-Control": "private, max-age=3600"},
        filename=filename,
    )


def _download_name(media: Media, variant: str, path: Path) -> str:
    """What the file is called once it lies in somebody's downloads folder.

    The original keeps its name from the NAS. A derived file is named after it as well, because
    the name on the SSD is a hash and says nothing to anybody.
    """
    original = media.primary_file.filename
    if variant == "original":
        return original

    return f"{Path(original).stem}-{variant}{path.suffix}"


def _path_of(media: Media, variant: str, settings: Settings) -> Path | None:
    if variant == "original":
        return Path(settings.library_path, media.primary_file.relative_path)

    relative = {
        "thumb": media.thumbnail_path,
        "preview": media.preview_path,
        "video": media.video_path,
        "poster": media.poster_path,
    }[variant]
    return Path(settings.derived_path, relative) if relative else None
