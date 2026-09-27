"""Fotobücher: an album to read rather than to browse (/photobooks)."""

import uuid
from contextlib import suppress
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from redis.asyncio import Redis
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from muninn.api.schemas.photobooks import (
    NewPhotobook,
    PhotobookList,
    PhotobookQueued,
    PhotobookRead,
    signed_pages,
    view_of,
)
from muninn.core.config import Settings
from muninn.core.deps import ActiveUser, AdminUser, get_redis, get_session, get_settings_from_state
from muninn.core.problem import ProblemError, problem_type
from muninn.huginn.app import celery_app
from muninn.models.album import Album
from muninn.models.photobook import SIZES, STATE_READY, STYLES, Photobook
from muninn.notify import events
from muninn.photobooks import service

router = APIRouter(prefix="/photobooks", tags=["photobooks"])

NO_BOOK = problem_type("photobook-not-found")
NO_ALBUM = problem_type("album-not-found")
UNKNOWN_SHAPE = problem_type("photobook-shape-unknown")


@router.get("", summary="Every photo book")
async def list_books(
    user: ActiveUser,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings_from_state)],
    album_id: uuid.UUID | None = None,
) -> PhotobookList:
    """The shelf, newest first.

    Everybody signed in reads the books; only an admin makes and removes them. A book that is
    still being built is listed with its state, so nobody wonders where it went.
    """
    books = await service.listed(session, album_id=album_id)
    titles = await service.album_titles(session, [book.album_id for book in books])
    return PhotobookList(
        items=[
            view_of(book, album=titles.get(book.album_id, ""), secret=settings.jwt_secret)
            for book in books
        ]
    )


@router.get("/{book_id}", summary="One photo book, with its pages")
async def read_book(
    book_id: uuid.UUID,
    user: ActiveUser,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings_from_state)],
) -> PhotobookRead:
    """The whole book. Every picture on every page carries an address signed for this hour."""
    book = await _found(session, book_id)
    titles = await service.album_titles(session, [book.album_id])
    return PhotobookRead(
        **view_of(
            book, album=titles.get(book.album_id, ""), secret=settings.jwt_secret
        ).model_dump(),
        leaves=signed_pages(book, secret=settings.jwt_secret) if book.state == STATE_READY else [],
    )


@router.post("", summary="Make books of an album", status_code=status.HTTP_202_ACCEPTED)
async def create_books(
    wanted: NewPhotobook,
    admin: AdminUser,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings_from_state)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> PhotobookQueued:
    """Puts the books on the shelf and hands the building to the worker.

    Answered at once, because building a book of a large album takes longer than a request may:
    the pictures are chosen and laid out, and then the machine is asked for the prose, page by
    page. Until that is done the books are listed as "wird gebaut".
    """
    if wanted.size not in SIZES or wanted.style not in STYLES:
        raise ProblemError(
            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            title="Diesen Umfang oder diesen Stil gibt es nicht.",
            type=UNKNOWN_SHAPE,
        )

    album = await session.get(Album, wanted.album_id)
    if album is None:
        raise ProblemError(
            status=status.HTTP_404_NOT_FOUND,
            title="Dieses Album gibt es nicht.",
            type=NO_ALBUM,
        )

    books = await service.create(
        session,
        album=album,
        size=wanted.size,
        style=wanted.style,
        max_media=wanted.max_media,
        title=wanted.title.strip(),
        count=wanted.count,
    )
    await session.commit()

    job_id = _hand_over([book.id for book in books])
    await events.publish(redis, events.PHOTOBOOKS_TOPIC, kind="queued", books=len(books))
    return PhotobookQueued(
        items=[
            view_of(book, album=album.display_title, secret=settings.jwt_secret) for book in books
        ],
        job_id=job_id,
    )


@router.post(
    "/{book_id}/rebuild", summary="Build a book anew", status_code=status.HTTP_202_ACCEPTED
)
async def rebuild_book(
    book_id: uuid.UUID,
    admin: AdminUser,
    session: Annotated[AsyncSession, Depends(get_session)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> PhotobookQueued:
    """The same book, built again - for when the album has grown, or the machine was away while
    it was made and its pages still speak in dates rather than in sentences."""
    book = await _found(session, book_id)
    job_id = _hand_over([book.id])
    await events.publish(redis, events.PHOTOBOOKS_TOPIC, kind="queued", books=1)
    return PhotobookQueued(items=[], job_id=job_id)


@router.delete("/{book_id}", summary="Remove a photo book", status_code=status.HTTP_204_NO_CONTENT)
async def delete_book(
    book_id: uuid.UUID,
    admin: AdminUser,
    session: Annotated[AsyncSession, Depends(get_session)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> Response:
    """Removes the book and nothing else: not one picture is touched by this."""
    book = await _found(session, book_id)
    await service.remove(session, book)
    await session.commit()
    await events.publish(redis, events.PHOTOBOOKS_TOPIC, kind="removed", book_id=str(book_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def _found(session: AsyncSession, book_id: uuid.UUID) -> Photobook:
    book = await service.get(session, book_id)
    if book is None:
        raise ProblemError(
            status=status.HTTP_404_NOT_FOUND,
            title="Dieses Fotobuch gibt es nicht.",
            type=NO_BOOK,
        )
    return book


def _hand_over(book_ids: list[uuid.UUID]) -> str | None:
    """Asks the worker to build these books. Without a worker they stay as they are."""
    with suppress(OperationalError):
        queued = celery_app.send_task(
            "muninn.build_photobooks", args=[[str(one) for one in book_ids]], retry=False
        )
        return str(queued.id)
    return None
