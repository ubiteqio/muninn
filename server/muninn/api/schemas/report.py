"""The contract of the Überblick: the library at a glance."""

from uuid import UUID

from pydantic import BaseModel


class Totals(BaseModel):
    media: int
    photos: int
    videos: int
    bytes: int
    #: What the thumbnails, previews and playable videos of these media take on the server.
    derived_bytes: int = 0
    video_seconds: float
    albums: int
    first_taken: str | None
    last_taken: str | None


class YearCount(BaseModel):
    year: int
    photos: int
    videos: int


class Step(BaseModel):
    """One stage of the pipeline: how many are through, of how many."""

    step: str
    done: int
    of: int


class Share(BaseModel):
    name: str
    count: int


class TownShare(BaseModel):
    name: str
    country: str | None
    count: int


class PersonShare(BaseModel):
    id: UUID
    name: str
    media: int
    crop: str | None


class Content(BaseModel):
    frames: int
    videos_with_speech: int
    spoken_seconds: float
    screenshots: int
    documents: int
    with_text: int


class People(BaseModel):
    faces: int
    named: int
    suggested: int
    unnamed: int
    groups: int
    persons: int
    media_with_faces: int


class Places(BaseModel):
    with_gps: int
    estimated: int
    towns: int
    countries: int


class Duplicates(BaseModel):
    groups: int
    exact: int
    near: int
    burst: int
    hidden: int


class Social(BaseModel):
    reactions: int
    comments: int
    favorites: int
    users: int


class ReportView(BaseModel):
    totals: Totals
    years: list[YearCount]
    #: How far each stage of the pipeline is.
    pipeline: list[Step]
    content: Content
    tags: list[Share]
    scenes: list[Share]
    times_of_day: list[Share]
    people: People
    persons: list[PersonShare]
    places: Places
    countries: list[Share]
    towns: list[TownShare]
    #: Where the dates come from.
    date_sources: list[Share]
    cameras: list[Share]
    #: Groups of copies and what is hidden.
    duplicates: Duplicates
    social: Social
