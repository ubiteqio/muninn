"""Rückblicke: "Heute vor X Jahren" (/memories)."""

from datetime import date, datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from muninn.api.schemas.media import MediaView
from muninn.api.schemas.memories import MemoryList, MemoryView
from muninn.core.config import Settings
from muninn.core.deps import ActiveUser, get_session, get_settings_from_state
from muninn.memories import service

router = APIRouter(prefix="/memories", tags=["memories"])


@router.get("", summary="Today's memories")
async def read_memories(
    user: ActiveUser,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings_from_state)],
    day: date | None = None,
) -> MemoryList:
    """One card per earlier year with photos from this calendar day, the most recent first.

    ``day`` defaults to today where the family lives. The choice is made once per day and kept.
    """
    zone = ZoneInfo(service.local_zone())
    wanted = day or datetime.now(zone).date()
    found = await service.of_day(session, wanted)
    return MemoryList(
        day=wanted,
        items=[
            MemoryView(
                id=entry.memory.id,
                year=entry.memory.year,
                years_ago=wanted.year - entry.memory.year,
                taken_on=(
                    entry.media[0].taken_at.astimezone(zone).date()
                    if entry.media[0].taken_at
                    else wanted.replace(year=entry.memory.year)
                ),
                from_week=entry.memory.from_week,
                album_id=entry.memory.album_id,
                title=entry.album.display_title if entry.album else None,
                media=[
                    MediaView.of(
                        medium,
                        library_path=str(settings.library_path),
                        secret=settings.jwt_secret,
                    )
                    for medium in entry.media
                ],
            )
            for entry in found
        ],
    )
