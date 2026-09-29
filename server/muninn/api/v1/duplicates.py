"""Doppelgänger: groups of copies, and hiding all but one (/admin/duplicates)."""

import csv
import io
import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from muninn.api.schemas.duplicates import (
    DuplicateGroupView,
    DuplicateMediaView,
    DuplicatePage,
    KeepRequest,
)
from muninn.api.schemas.media import MediaView
from muninn.api.schemas.search import decode_offset, encode_offset
from muninn.core.config import Settings
from muninn.core.deps import AdminUser, get_session, get_settings_from_state
from muninn.core.problem import ProblemError, problem_type
from muninn.duplicates import service

router = APIRouter(prefix="/admin/duplicates", tags=["admin: duplicates"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings_from_state)]


@router.get("", summary="Groups of copies, newest or heaviest first")
async def list_duplicates(
    admin: AdminUser,
    session: SessionDep,
    settings: SettingsDep,
    state: Literal["open", "all"] = "open",
    sort: Literal["newest", "size"] = "newest",
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
) -> DuplicatePage:
    """ "open" leaves out the groups of which only one medium is still shown.

    ``sort=size`` puts the groups that hold the most disk first: somebody working through
    copies to win back room wants the two 4K videos before forty photographs of a birthday.
    """
    try:
        offset = decode_offset(cursor) if cursor else 0
    except ValueError as error:
        raise ProblemError(
            status=status.HTTP_400_BAD_REQUEST,
            type=problem_type("invalid-cursor"),
            title="Invalid cursor",
        ) from error
    groups, more = await service.list_groups(
        session,
        open_only=state == "open",
        offset=offset,
        limit=limit,
        by_size=sort == "size",
    )
    return DuplicatePage(
        items=[
            DuplicateGroupView(
                id=group.id,
                kind=group.kind,  # type: ignore[arg-type]
                members=[
                    DuplicateMediaView(
                        media=MediaView.of(
                            medium,
                            library_path=str(settings.library_path),
                            secret=settings.jwt_secret,
                        ),
                        best=position == 0,
                        hidden=medium.duplicate_of is not None,
                    )
                    for position, medium in enumerate(group.media)
                ],
            )
            for group in groups
        ],
        next_cursor=encode_offset(offset + limit) if more else None,
        open_count=await service.count_open(session),
    )


@router.post(
    "/{group_id}/keep",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Keep some media of a group and hide the others",
)
async def keep(
    group_id: int, payload: KeepRequest, admin: AdminUser, session: SessionDep
) -> Response:
    """The hidden ones leave albums, timeline, search and map. The NAS is not touched."""
    try:
        await service.keep(session, group_id, payload.media_ids)
    except service.NotInGroupError as error:
        raise ProblemError(
            status=status.HTTP_404_NOT_FOUND,
            type=problem_type("not-in-group"),
            title="Not in this group",
            detail="The groups are found again every quarter of an hour; reload the list.",
        ) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/hidden/{media_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Show a hidden copy again",
)
async def show_again(media_id: uuid.UUID, admin: AdminUser, session: SessionDep) -> Response:
    await service.show_again(session, media_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/hidden.csv", summary="The paths of every hidden copy, to delete on the NAS")
async def hidden_csv(admin: AdminUser, session: SessionDep) -> Response:
    """One row per hidden copy, beside the medium it is a copy of. Muninn deletes nothing."""
    out = io.StringIO()
    writer = csv.writer(out, delimiter=";")
    writer.writerow(["path", "copy_of"])
    for hidden, kept in await service.hidden_media(session):
        writer.writerow(
            [hidden.primary_file.relative_path, kept.primary_file.relative_path if kept else ""]
        )
    return Response(
        content=out.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="muninn-duplikate.csv"'},
    )
