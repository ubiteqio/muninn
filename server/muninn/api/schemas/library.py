"""Contract for the library: which folders are published, and how their syncs went."""

from datetime import datetime
from typing import Annotated, Any, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from muninn.models.change_log import ChangeKind, ChangeLogEntry, SyncTrigger
from muninn.models.publication import Publication, ScanStatus

#: A path below the mounted library. Empty means the library folder itself.
LibraryPath = Annotated[str, Field(max_length=1024)]


class SyncProgressView(BaseModel):
    """Where a running read stands, counted in files rather than folders."""

    files_total: int
    files_done: int
    #: The folder being read right now, as context.
    current: str


class PublicationView(BaseModel):
    """A folder that appears under Albums, with everything below it."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    #: Path below the mounted library; "" is the library folder itself.
    relative_path: str
    #: The folder's own name, which is also what the album is called.
    name: str
    enabled: bool
    last_sync_at: datetime | None
    last_sync_status: ScanStatus
    last_sync_message: str | None
    #: Files a paused sync would have marked as missing; above zero it waits for a confirmation.
    pending_deletions: int
    created_at: datetime
    #: Set while a read is running.
    progress: SyncProgressView | None = None
    #: Files seen once that wait for the second look, because they may still be copying.
    waiting_files: int = 0
    #: Subfolders switched off again.
    excluded_paths: list[str] = []

    @classmethod
    def of(
        cls,
        publication: Publication,
        progress: dict[str, Any] | None = None,
        waiting_files: int = 0,
    ) -> Self:
        view = cls.model_validate(publication)
        return view.model_copy(
            update={
                "progress": SyncProgressView.model_validate(progress) if progress else None,
                "waiting_files": waiting_files,
            }
        )


class PublicationCreate(BaseModel):
    """Publishing a folder. Its name in Muninn is the folder's own."""

    path: LibraryPath = ""


class ExclusionRequest(BaseModel):
    """A subfolder of the published folder, relative to the library."""

    relative_path: LibraryPath


class PublicationUpdate(BaseModel):
    enabled: bool | None = None


class SyncRequest(BaseModel):
    """A quick sync reads only what changed; a full one reads everything."""

    quick: bool = False
    #: Set after a sync paused, to confirm that the missing files are really gone.
    confirm_deletions: bool = False


class SyncQueued(BaseModel):
    publication_id: UUID
    task_id: str


class FolderEntry(BaseModel):
    """A folder an admin can publish."""

    name: str
    path: str
    relative_path: str
    #: Whether the folder is a mount of its own - usually exactly the share one is looking for.
    is_mount: bool
    #: Whether it is published already, itself or through a folder above it.
    published: bool
    #: Inside a published folder, but switched off again.
    excluded: bool = False
    #: The published folder it lies in, if any.
    publication_id: UUID | None = None
    #: Whether it is that published folder itself.
    is_publication: bool = False
    #: Media lying directly in it, counted only for the folder that was listed.
    media_files: int | None


class FolderListing(BaseModel):
    #: The folder that was listed, relative to the mounted library.
    relative_path: str
    #: Where the host mounts the library inside the container; set in deploy/.env.
    library_path: str
    #: That folder itself - it can be published as well, and often is the one somebody wants.
    current: FolderEntry
    items: list[FolderEntry]


class IndexStatus(BaseModel):
    """What the admin area shows about the library."""

    publications: list[PublicationView]
    library_path: str
    #: When the clock reads everything again by itself; null until it has run once.
    next_sync_at: datetime | None
    albums: int
    media: int
    missing: int
    pending_metadata: int
    #: Media that still have no previews.
    pending_derivatives: int


class ChangeView(BaseModel):
    """One line of the change log."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    occurred_at: datetime
    album_id: UUID | None
    media_id: UUID | None
    kind: ChangeKind
    trigger: SyncTrigger
    #: The path at the time, so the line still says something after the row it points at is gone.
    path: str | None

    @classmethod
    def of(cls, entry: ChangeLogEntry) -> Self:
        return cls.model_validate(entry)
