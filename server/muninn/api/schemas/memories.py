"""The contract of the Rückblicke."""

from datetime import date
from uuid import UUID

from pydantic import BaseModel

from muninn.api.schemas.media import MediaView


class MemoryView(BaseModel):
    """One card: the photos of one earlier year from today's calendar day."""

    id: UUID
    year: int
    years_ago: int
    #: The day in that year the photos are from (the first of them, when a week was taken).
    taken_on: date
    #: True when the day itself had nothing and the week around it was taken.
    from_week: bool
    #: The album most of them are from; its title is the card's.
    album_id: UUID | None
    title: str | None
    #: In the order they were taken, at most twelve.
    media: list[MediaView]


class MemoryList(BaseModel):
    day: date
    items: list[MemoryView]
