"""The contract of the Doppelgänger view."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from muninn.api.schemas.media import MediaView


class DuplicateMediaView(BaseModel):
    media: MediaView
    #: The one Muninn suggests keeping.
    best: bool
    #: Hidden as a copy of another member.
    hidden: bool


class DuplicateGroupView(BaseModel):
    id: int
    #: exact: the same file; near: a smaller or recompressed copy; burst: shots of one burst.
    kind: Literal["exact", "near", "burst"]
    #: Best first.
    members: list[DuplicateMediaView]


class DuplicatePage(BaseModel):
    items: list[DuplicateGroupView]
    next_cursor: str | None = None
    #: Groups nobody has decided on yet.
    open_count: int


class KeepRequest(BaseModel):
    """The members that stay - one, or a few good shots of a burst. The others are hidden."""

    media_ids: list[UUID] = Field(min_length=1)
