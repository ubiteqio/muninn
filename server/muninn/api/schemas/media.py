"""Contract for media: what a medium is, where its original lies, and how the timeline runs."""

from datetime import date, datetime
from typing import Self
from uuid import UUID

from pydantic import BaseModel

from muninn.api.schemas.places import PlaceView
from muninn.api.schemas.social import SocialView
from muninn.core.signing import sign_media
from muninn.media.service import Granularity
from muninn.models.analysis import MediaAnalysis, MediaTranscript, VideoFrame
from muninn.models.media import DateSource, Media, MediaFileRole, MediaKind, MediaStatus
from muninn.models.place import Place


class MediaFileView(BaseModel):
    """One file of the medium: the picture itself, a RAW beside it, or a Live Photo's clip."""

    role: MediaFileRole
    filename: str
    relative_path: str
    byte_size: int
    content_hash: str


class MediaOrigin(BaseModel):
    """Where the original lies. The app shows this and offers the download."""

    #: Where the host mounts the library inside the container.
    library_path: str
    #: Path of the original below that, exactly as it is on the NAS.
    relative_path: str
    filename: str
    byte_size: int


class MediaUrls(BaseModel):
    """Signed addresses, good for an hour, so the browser may cache the pictures."""

    thumb: str | None
    preview: str | None
    video: str | None
    poster: str | None
    original: str


def signed_urls(media: Media, *, secret: str) -> MediaUrls:
    def address(variant: str) -> str:
        token = sign_media(media.id, variant, secret=secret)
        return f"/api/v1/media/{media.id}/{variant}?token={token}"

    return MediaUrls(
        thumb=address("thumb") if media.thumbnail_path else None,
        preview=address("preview") if media.preview_path else None,
        video=address("video") if media.video_path else None,
        poster=address("poster") if media.poster_path else None,
        original=address("original"),
    )


class MomentView(BaseModel):
    """What was seen at one second of a video."""

    second: int
    caption: str


class AnalysisView(BaseModel):
    """What the describing model saw. Shown in the info panel, read-only."""

    caption: str
    tags: list[str]
    scene: str
    ocr_text: str
    model: str
    analyzed_at: datetime
    #: For a video, every second that was looked at, in order; empty for a photo.
    moments: list[MomentView] = []

    @classmethod
    def of(cls, analysis: MediaAnalysis, frames: list[VideoFrame] | None = None) -> Self:
        return cls(
            caption=analysis.caption,
            tags=analysis.tags,
            scene=analysis.scene,
            ocr_text=analysis.ocr_text,
            model=analysis.model,
            analyzed_at=analysis.analyzed_at,
            moments=[
                MomentView(second=frame.second, caption=frame.caption) for frame in frames or []
            ],
        )


class SpokenView(BaseModel):
    start: float
    end: float
    text: str


class TranscriptView(BaseModel):
    """What is said in a video. No parts means it was listened to and nobody spoke."""

    language: str
    parts: list[SpokenView]
    model: str

    @classmethod
    def of(cls, transcript: MediaTranscript) -> Self:
        return cls(
            language=transcript.language,
            parts=[SpokenView.model_validate(part) for part in transcript.segments],
            model=transcript.model,
        )


class MediaView(BaseModel):
    """A medium as lists and the detail view show it."""

    id: UUID
    album_id: UUID
    kind: MediaKind
    status: MediaStatus
    taken_at: datetime | None
    taken_at_source: DateSource | None
    #: True when the date comes from a folder name or the file's own time: shown as approximate.
    date_is_estimated: bool
    width: int | None
    height: int | None
    duration_seconds: float | None
    camera_make: str | None
    camera_model: str | None
    lens: str | None
    latitude: float | None
    longitude: float | None
    content_hash: str
    #: True once the previews exist; until then the app shows a placeholder.
    has_previews: bool
    origin: MediaOrigin
    urls: MediaUrls
    files: list[MediaFileView]
    #: Only in the detail view, and only once stage 5 has described the medium.
    analysis: AnalysisView | None = None
    #: Only in the detail view of a video that was listened to.
    transcript: TranscriptView | None = None
    #: Only in the detail view: likes, who, and whether it is in the asker's Walhall.
    social: SocialView | None = None
    #: Only in the detail view, once the coordinates have been named.
    place: PlaceView | None = None

    @classmethod
    def of(
        cls,
        media: Media,
        *,
        library_path: str,
        secret: str,
        analysis: MediaAnalysis | None = None,
        frames: list[VideoFrame] | None = None,
        transcript: MediaTranscript | None = None,
        social: SocialView | None = None,
        place: Place | None = None,
    ) -> Self:
        primary = media.primary_file
        return cls(
            id=media.id,
            album_id=media.album_id,
            kind=media.kind,
            status=media.status,
            taken_at=media.taken_at,
            taken_at_source=media.taken_at_source,
            date_is_estimated=media.date_is_estimated,
            width=media.width,
            height=media.height,
            duration_seconds=media.duration_seconds,
            camera_make=media.camera_make,
            camera_model=media.camera_model,
            lens=media.lens,
            latitude=media.latitude,
            longitude=media.longitude,
            content_hash=media.content_hash,
            has_previews=media.thumbnail_path is not None,
            urls=signed_urls(media, secret=secret),
            origin=MediaOrigin(
                library_path=library_path,
                relative_path=primary.relative_path,
                filename=primary.filename,
                byte_size=primary.byte_size,
            ),
            files=[
                MediaFileView(
                    role=file.role,
                    filename=file.filename,
                    relative_path=file.relative_path,
                    byte_size=file.byte_size,
                    content_hash=file.content_hash,
                )
                for file in sorted(media.files, key=lambda file: file.relative_path)
            ],
            analysis=AnalysisView.of(analysis, frames) if analysis else None,
            transcript=TranscriptView.of(transcript) if transcript else None,
            social=social,
            place=PlaceView.of(place, estimated=media.place_estimated) if place else None,
        )


class MarkView(BaseModel):
    """One slice of the timeline: the day it begins on and how much it holds."""

    start: date
    count: int


class TimelineShapeView(BaseModel):
    """The shape of a level of the timeline: how much there is and how it is spread out.

    A few hundred rows, whatever the library holds. The app builds its rail from them and knows
    how tall a level is before it has loaded a single picture.
    """

    by: Granularity
    total: int
    #: Newest first, the same direction the timeline itself runs in.
    marks: list[MarkView]


class PeriodCoverView(BaseModel):
    """One of the few pictures that stand for a year or a month."""

    id: UUID
    thumb: str


class PeriodView(BaseModel):
    """One card of the overview: a year or a month, with what it holds and what it looks like."""

    start: date
    count: int
    covers: list[PeriodCoverView]


class MediaStageView(BaseModel):
    """One step of the pipeline as it stands for one medium, for the admin in front of it."""

    stage: str
    #: done, open, given-up, or not-for-this - a photo has nothing to transcribe.
    state: str
    #: How often it failed for this medium's own sake; three is where the clock gives up.
    attempts: int = 0
    last_error: str | None = None


class MediaStagesView(BaseModel):
    """Everything the pipeline can do to one medium, in the order it does it."""

    media_id: UUID
    stages: list[MediaStageView]
