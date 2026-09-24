"""The contract of the search."""

import base64
import binascii
from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from muninn.api.schemas.media import MediaView
from muninn.models.media import MediaKind


class SearchRequest(BaseModel):
    """What was typed, and the filters chosen beside it. Each filter narrows; none is needed."""

    q: str = Field(default="", max_length=300)
    date_from: date | None = None
    #: The first day that no longer counts.
    date_until: date | None = None
    kind: MediaKind | None = None
    #: An album and everything below it.
    album_id: UUID | None = None
    camera: str | None = Field(default=None, max_length=120)
    #: A town, as the overview names it. Looked up the same way a town in the words would be,
    #: so only places the library actually has photos from count.
    place: str | None = Field(default=None, max_length=120)
    sort: Literal["relevance", "date"] = "relevance"
    cursor: str | None = None
    limit: int = Field(default=60, ge=1, le=200)


class UnderstoodView(BaseModel):
    """How the words were taken apart, so the app can show the period it found as a chip."""

    text: str
    date_from: date | None
    date_until: date | None
    kind: MediaKind | None
    #: The places taken out of the words, as typed.
    places: list[str] = []
    #: The persons taken out of the words, as typed.
    persons: list[str] = []


class SearchHitView(BaseModel):
    media: MediaView
    #: For a video, the second the search matched - a frame or something said - to start at.
    moment: float | None = None


class FacetView(BaseModel):
    """One thing the found media can be narrowed to, and how many of them carry it."""

    value: str
    label: str
    count: int


class FacetsView(BaseModel):
    """What the found media are made of - of them, not of the library, so no choice is empty."""

    years: list[FacetView] = []
    towns: list[FacetView] = []
    cameras: list[FacetView] = []
    albums: list[FacetView] = []


class SearchPage(BaseModel):
    items: list[SearchHitView]
    next_cursor: str | None = None
    understood: UnderstoodView
    #: True when the AI server did not answer: only words and names were searched this time.
    degraded: bool = False
    #: The same on every page of one search: it describes the whole find, not the page.
    facets: FacetsView = FacetsView()


def encode_offset(offset: int) -> str:
    return base64.urlsafe_b64encode(f"o{offset}".encode()).decode("ascii").rstrip("=")


def decode_offset(cursor: str) -> int:
    """Raise ValueError for anything we did not hand out."""
    padded = cursor + "=" * (-len(cursor) % 4)
    try:
        raw = base64.urlsafe_b64decode(padded.encode("ascii")).decode("ascii")
    except (binascii.Error, UnicodeDecodeError) as error:
        raise ValueError("malformed cursor") from error
    if not raw.startswith("o") or not raw[1:].isdigit():
        raise ValueError("malformed cursor")
    return int(raw[1:])


class SearchAbilities(BaseModel):
    """What the search can look into, by the AI models in use."""

    #: Words find what pictures show, and "Ähnliche Bilder" has something to compare.
    pictures: bool
    #: Descriptions are found by what they mean, not only by their words.
    meanings: bool
    #: Whether the machine behind them answers at this moment. False while it rests after not
    #: answering: the app then offers the plain search instead of promising more.
    ready: bool = False
