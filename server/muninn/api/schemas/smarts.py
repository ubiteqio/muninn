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


class ShelfMediaList(BaseModel):
    key: str
    items: list[MediaView]
    next_offset: int | None = None


class BuildRequest(BaseModel):
    """Build chapters now: one album, or albums in turn until enough have come out of it."""

    album_id: uuid.UUID | None = None
    #: How many chapters this run should produce before it stops. Ignored for a single album.
    chapters: int = Field(default=21, ge=1, le=500)
    distance: float | None = Field(default=None, gt=0.0, lt=1.0)


class BuildResult(BaseModel):
    """What the run did."""

    albums: int
    chapters: int
    #: Albums that still have no chapters of this version.
    outstanding: int


class SmartsState(BaseModel):
    """What the Smarts hold, for the engine room."""

    chapters: int
    albums: int
    media: int
    outstanding: int
    built_at: datetime | None
    #: What the field beside the button starts with.
    wanted: int
