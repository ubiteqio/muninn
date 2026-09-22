"""Contract for the album tree."""

from datetime import datetime
from typing import Annotated, Any, Self
from uuid import UUID

from pydantic import BaseModel, Field

from muninn.albums.service import AlbumNode
from muninn.api.schemas.places import PlaceView
from muninn.core.signing import sign_media
from muninn.models.place import Place
from muninn.models.publication import ScanStatus


class AlbumView(BaseModel):
    """One album. Yggdrasil is built from a list of these."""

    id: UUID
    parent_id: UUID | None
    #: Path of the folder below the mounted library.
    relative_path: str
    #: Whether this folder is read. False means it only carries the way to a published folder
    #: further down, and holds no media of its own.
    is_source: bool
    #: The folder's name on the NAS.
    name: str
    #: What to show: the title set in Muninn, or the folder name.
    title: str
    #: Only set when somebody gave the album a title of its own.
    custom_title: str | None
    description: str | None
    media_count: int
    child_count: int
    #: Signed addresses for the tile: one thumbnail for an album with pictures of its own, up to
    #: four from the albums below it for one that only holds folders, empty while there are none.
    cover_urls: list[str]
    created_at: datetime

    #: How the last sync of this folder went. "unavailable" means the folder could not be read -
    #: which is never the same as empty.
    last_sync_at: datetime | None
    last_sync_status: ScanStatus
    last_sync_message: str | None
    #: Where it was taken, for its media without coordinates. Only in the view of one album.
    place: PlaceView | None = None

    @classmethod
    def of(cls, node: AlbumNode, *, secret: str, place: Place | None = None) -> Self:
        album = node.album
        return cls(
            id=album.id,
            parent_id=album.parent_id,
            relative_path=album.relative_path,
            is_source=album.is_source,
            name=album.name,
            title=album.display_title,
            custom_title=album.title,
            description=album.description,
            media_count=node.media_count,
            child_count=node.child_count,
            cover_urls=[
                f"/api/v1/media/{cover}/thumb?token={sign_media(cover, 'thumb', secret=secret)}"
                for cover in node.cover_media_ids
            ],
            created_at=album.created_at,
            last_sync_at=album.last_sync_at,
            last_sync_status=album.last_sync_status,
            last_sync_message=album.last_sync_message,
            place=PlaceView.of(place) if place else None,
        )


class AlbumTree(BaseModel):
    """Every album at once; the app builds the tree from parent_id."""

    items: list[AlbumView]


class AlbumUpdate(BaseModel):
    """What may be changed about an album. An empty string clears the field."""

    title: Annotated[str, Field(max_length=255)] | None = None
    description: Annotated[str, Field(max_length=4000)] | None = None


class AlbumSyncRequest(BaseModel):
    """Everybody signed in may ask for this: it reads the NAS and changes nothing on it."""

    with_children: bool = False


class AlbumSyncQueued(BaseModel):
    album_id: UUID
    job_id: str
    task_id: str


class AlbumSyncJob(BaseModel):
    """Where a requested sync stands. Milestone 5 replaces the asking with a live update."""

    job_id: str
    #: "running", "done", or "coalesced" when it was folded into a sync that was already going.
    state: str
    updated_at: datetime | None = None
    #: The balance once it is done: how much was added, changed, moved or is missing.
    result: dict[str, Any] | None = None
