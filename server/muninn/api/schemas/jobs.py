"""Contract for what Huginn is working on."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from muninn.api.schemas.library import SyncProgressView
from muninn.models.media import MediaKind


class RunningRead(BaseModel):
    """A folder that is being read right now."""

    publication_id: UUID
    #: Path below the mounted library; "" is the library itself.
    relative_path: str
    name: str
    progress: SyncProgressView | None


class TaskMedia(BaseModel):
    """The medium a piece of work is about: what it is, and where it lies."""

    id: UUID
    kind: MediaKind
    album_id: UUID
    album_path: str


class ActiveTask(BaseModel):
    """One piece of work a worker has in its hands right now."""

    #: What to name when stopping this one piece of work.
    task_id: str
    #: "read", "metadata" or "derive".
    stage: str
    #: What it is working on: a file name, or empty for a read of a whole folder.
    label: str
    started_at: datetime
    #: The medium, so the admin area can lead to it and its album.
    media: TaskMedia | None = None


class FinishedTask(BaseModel):
    """One piece of work that was finished a moment ago.

    Metadata takes about 80 ms and a preview about 110, so the admin area asking every couple of
    seconds would almost never catch one in the act. What was just finished says the same thing:
    work is going through.
    """

    #: "metadata" or "derive".
    stage: str
    #: The file it was about, as far as it is still known.
    label: str
    finished_at: datetime
    #: True when the work ended in an error - the AI server away, a file it could not read.
    failed: bool = False
    media: TaskMedia | None = None


class QueueView(BaseModel):
    """One of Huginn's queues."""

    name: str
    #: Tasks waiting in it. What is already running is not part of this.
    waiting: int


class ScheduleView(BaseModel):
    """What the clock will do next."""

    next_quick_sync_at: datetime | None
    next_full_sync_at: datetime | None
    quick_sync_seconds: int
    full_sync_hour: int
    stability_seconds: int


class JobsView(BaseModel):
    """Everything the admin area shows about the work in progress - and what came of it."""

    running: list[RunningRead]
    #: Every piece of work in a worker's hands, reads and single media alike.
    active: list[ActiveTask]
    #: When a read last finished. An idle engine room should still say what just happened.
    last_read_at: datetime | None
    albums: int
    media: int
    #: Of those media, how many are pictures and how many are films.
    photos: int = 0
    videos: int = 0
    queues: list[QueueView]
    #: Media that still need their metadata read.
    pending_metadata: int
    #: Media that still need their previews.
    pending_derivatives: int
    #: Media that still need their picture vector; null while no picture model is set up.
    pending_image_vectors: int | None
    #: Videos not yet listened to; null while no speech model is set up.
    pending_transcripts: int | None
    #: Media that still need their description; null while no describing model is set up.
    pending_analyses: int | None
    #: Descriptions that still need their vector; null while no word model is set up.
    pending_caption_vectors: int | None
    #: Media not yet looked at for faces; null without a face model in use.
    pending_faces: int | None = None
    #: Files seen once, waiting for the listing that confirms them.
    waiting_files: int
    #: Files the reading had to walk past because it could not open them.
    unreadable_files: int = 0
    #: The last few pieces of work that were finished, newest first.
    finished: list[FinishedTask]
    #: How many media each stage finished in the last minute, by stage name.
    done_last_minute: dict[str, int]
    schedule: ScheduleView


class WaitingItem(BaseModel):
    """One medium behind a number in the engine room, and what is known about why."""

    media_id: UUID
    kind: str
    filename: str
    album: str
    #: Where the medium lies, so the list can lead to the picture itself.
    album_id: UUID
    #: How big the file is. One that will not be read is often an unusually big one.
    byte_size: int
    #: How often this stage has tried and failed at this medium; three is where it gives up.
    attempts: int
    #: When it last tried. Nothing where it has not failed at all.
    last_at: datetime | None = None
    #: What the machine said the last time, in its own words. Nothing where it never spoke.
    last_error: str | None


class WaitingFile(BaseModel):
    """One file seen once and waiting for the listing that confirms it."""

    relative_path: str
    first_seen_at: datetime
    byte_size: int = 0
    #: Why it is still here, where anybody knows: what the operating system said.
    reason: str | None = None


class WaitingView(BaseModel):
    """What is behind one of the numbers: the media themselves, or the files still waiting."""

    stage: str
    items: list[WaitingItem]
    files: list[WaitingFile]


class PurgedQueue(BaseModel):
    """What emptying a queue threw away."""

    name: str
    removed: int


class AiServiceView(BaseModel):
    """One AI interface and whether its machine answers."""

    #: analyzer, image_embedder, text_embedder, transcriber or face_detector.
    kind: str
    #: False while no profile is in use for this interface; everything below is then empty.
    configured: bool
    name: str | None
    model: str | None
    #: What the last check found: it answers, or it does not.
    ok: bool | None
    #: The model that answered, or what went wrong.
    detail: str | None
    milliseconds: int | None
    checked_at: datetime | None
    #: While the worker rests this stage because its machine did not answer.
    paused_until: datetime | None


class AiHealthView(BaseModel):
    """The AI services at a glance, each checked at most every half minute."""

    services: list[AiServiceView]
