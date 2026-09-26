"""The contract of the Smarts."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from muninn.api.schemas.media import MediaView
from muninn.api.schemas.people import FaceView


class ChapterView(BaseModel):
    """One group of media that belong together by what they show."""

    id: uuid.UUID
    album_id: uuid.UUID
    #: The album's title, so a chapter says where it comes from.
    album_title: str
    #: What it is called, from the tags of its media. Empty when nothing stood out.
    title: str
    tags: list[str]
    size: int
    from_at: datetime | None
    until_at: datetime | None
    #: The clearest examples, for the card. At most six.
    cover: list[MediaView]


class ChapterList(BaseModel):
    items: list[ChapterView]
    next_offset: int | None = None


class ShelfView(BaseModel):
    """A group that needed no grouping: everything with one trait."""

    key: str
    count: int


class FaceStripView(BaseModel):
    person_id: uuid.UUID
    name: str
    #: In how many photos and videos they turn up.
    count: int
    #: Their clearest face, cut out, for the round picture in the strip.
    face: FaceView | None = None


class SmartsView(BaseModel):
    """What the Smarts screen shows before anything is chosen."""

    media: int
    chapters: list[ChapterView]
    shelves: list[ShelfView]
    faces: list[FaceStripView]
    next_offset: int | None = None


class ChapterMediaList(BaseModel):
    chapter: ChapterView
    items: list[MediaView]
    next_offset: int | None = None


class BuildRequest(BaseModel):
    """Build the chapters of one album now, or of every album that needs it."""

    album_id: uuid.UUID | None = None
    distance: float | None = Field(default=None, gt=0.0, lt=1.0)


class BuildQueued(BaseModel):
    albums: int
