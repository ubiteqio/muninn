"""The contract of the map and of places."""

from typing import Self
from uuid import UUID

from pydantic import BaseModel, Field

from muninn.models.place import Place


class PlaceView(BaseModel):
    """A town: "Florenz, Toskana, Italien"."""

    id: int
    name: str
    region: str | None
    country: str | None
    #: True for a medium that has it from its album, not from its own coordinates.
    estimated: bool = False

    @classmethod
    def of(cls, place: Place, *, estimated: bool = False) -> Self:
        return cls(
            id=place.id,
            name=place.name,
            region=place.region,
            country=place.country,
            estimated=estimated,
        )


class PlaceList(BaseModel):
    items: list[PlaceView]


class AlbumPlaceUpdate(BaseModel):
    """The town an album was taken in; null takes it away."""

    place_id: int | None = Field(default=None)


class BoundsView(BaseModel):
    west: float
    south: float
    east: float
    north: float


class ClusterView(BaseModel):
    """A circle on the map: one medium, or several close together at this zoom level."""

    latitude: float
    longitude: float
    count: int
    #: The newest medium in it. Its thumbnail stands for the cluster; with count 1 it is the medium.
    cover_id: UUID
    cover_thumb: str | None
    #: The box around its points: tapping zooms there.
    bounds: BoundsView


class ClusterList(BaseModel):
    items: list[ClusterView]
