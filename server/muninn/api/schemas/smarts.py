"""The contract of the Smarts."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from muninn.api.schemas.media import MediaView
from muninn.api.schemas.people import FaceView


class ChapterView(BaseModel):
    """One chapter: media that belong together by time, place, face or what they show."""

    id: uuid.UUID
    #: Which rule found it: trip, day, motif, place, person, ritual.
    kind: str
    #: The text key the app renders, and what it renders with. The German lives in the app.
    title_key: str
    title_args: dict[str, Any]
    #: The words the name was made of, where tags made it.
    tags: list[str]
    size: int
    #: How many folders it draws from, and the one folder when it is only one.
    albums: int
    album_id: uuid.UUID | None
    from_at: datetime | None
    until_at: datetime | None
    #: The first few of its media, for the card. At most six.
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
    """Find the smart albums anew, across the whole library.

    Both numbers are settings; a run may override them for a try without saving anything.
    """

    #: How many smart albums there are at most. Left out, the setting decides.
    chapters: int | None = Field(default=None, ge=1, le=500)
    #: How many media one of them holds at most. Left out, the setting decides.
    max_media: int | None = Field(default=None, ge=10, le=5000)
    distance: float | None = Field(default=None, gt=0.0, lt=1.0)


class BuildResult(BaseModel):
    """What the run did."""

    chapters: int
    media: int
    #: How many of each kind came out of it.
    by_kind: dict[str, int]


class SmartsState(BaseModel):
    """What the Smarts hold, for the settings."""

    chapters: int
    media: int
    built_at: datetime | None
    by_kind: dict[str, int]
    #: What an admin set: how many there are, and how many media each one holds.
    max_chapters: int
    max_media: int
