"""Faces: finding them in the media, and who they are.

Stage 7 of the pipeline sends a medium's large preview to the face model - not the thumbnail:
a face below 40 pixels says too little about who it is, and a thumbnail has few above that. A
video is looked at every five seconds, every fifteen when it is longer than two minutes, and the
same face seen again in it counts once.

The vectors of the faces are kept and searched by muninn.search, like every vector.
"""

import asyncio
import base64
import math
import uuid
from pathlib import Path

import pyvips
from sqlalchemy import Select, and_, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from muninn.ai.base import DetectedFace, FaceDetector
from muninn.analysis.frames import FrameError, frames_of
from muninn.faces import people
from muninn.huginn import attempts, jobs
from muninn.media.service import relative_of
from muninn.models.face import Face
from muninn.models.media import Media, MediaKind, MediaStatus
from muninn.search import service as search_service

#: Raised when faces are found differently; every medium is then looked at again.
FACE_VERSION = 1

#: Smaller faces are dropped: the concept's 40 pixels, of the preview that was looked at.
MIN_PIXELS = 40
#: How sure the detector must be. Below this lie ears, dogs and posters.
MIN_SCORE = 0.6

#: A video: one look every this many seconds - less often in a long one, where the same people
#: turn up again and again.
VIDEO_STEP_SECONDS = 5
LONG_VIDEO_STEP_SECONDS = 15
#: From this length on a video counts as long.
LONG_VIDEO_SECONDS = 120


def video_step(duration: float | None) -> int:
    """How often a video is looked at for faces."""
    if duration is not None and duration > LONG_VIDEO_SECONDS:
        return LONG_VIDEO_STEP_SECONDS
    return VIDEO_STEP_SECONDS


#: Two faces in one video this alike (cosine similarity) are the same person seen again.
SAME_IN_VIDEO = 0.6

_MIME_TYPES = {".webp": "image/webp", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}


def _kept(face: DetectedFace) -> bool:
    return face.pixels >= MIN_PIXELS and face.score >= MIN_SCORE


def _similarity(first: list[float], second: list[float]) -> float:
    dot = sum(a * b for a, b in zip(first, second, strict=True))
    norm = math.sqrt(sum(a * a for a in first)) * math.sqrt(sum(b * b for b in second))
    return dot / norm if norm else 0.0


def once_each(
    seen: list[tuple[float | None, DetectedFace]],
) -> list[tuple[float | None, DetectedFace]]:
    """The faces of a video, each person once: the clearest look at them stays."""
    kept: list[tuple[float | None, DetectedFace]] = []
    for second, face in sorted(seen, key=lambda item: -item[1].pixels * item[1].score):
        if all(_similarity(face.embedding, other.embedding) < SAME_IN_VIDEO for _, other in kept):
            kept.append((second, face))
    return sorted(kept, key=lambda item: (item[0] or 0.0, item[1].box[0]))


#: The side of the square picture kept of every face, for the Personen screen.
CROP_PIXELS = 160
#: How much around the face the square shows: forehead, chin, a little hair.
CROP_MARGIN = 1.6


def crop_name(face_id: uuid.UUID) -> str:
    return f"face-{face_id.hex[:16]}.webp"


def crop(picture: bytes, face: DetectedFace) -> bytes:
    """A square around the face, cut from the picture it was found in."""
    image = pyvips.Image.new_from_buffer(picture, "")
    width, height = image.width, image.height
    left, top, right, bottom = face.box
    side = max((right - left) * width, (bottom - top) * height) * CROP_MARGIN
    side = min(side, width, height)
    center_x = (left + right) / 2 * width
    center_y = (top + bottom) / 2 * height
    x = int(min(max(0.0, center_x - side / 2), width - side))
    y = int(min(max(0.0, center_y - side / 2), height - side))
    square = image.crop(x, y, max(1, int(side)), max(1, int(side)))
    small = square.thumbnail_image(CROP_PIXELS, height=CROP_PIXELS, size="force")
    if small.hasalpha():
        small = small.flatten()
    return bytes(small.write_to_buffer(".webp[Q=82]"))


async def _looks_at_video(video: Path, step: int) -> list[tuple[int, bytes]]:
    return [(frame.second, frame.jpeg) async for frame in frames_of(video, every=step)]


def _data_url(picture: bytes, mime: str) -> str:
    return f"data:{mime};base64,{base64.b64encode(picture).decode('ascii')}"


async def apply_faces(
    session: AsyncSession,
    media_id: uuid.UUID,
    *,
    detector: FaceDetector,
    model: str,
    derived_root: Path,
) -> bool:
    """Stage 7 for one medium. Returns whether it was looked at; one that was already, or has
    nothing to look at yet, is skipped. No faces at all is an answer too, and is kept."""
    media = await session.get(Media, media_id)
    if (
        media is None
        or media.status is not MediaStatus.ACTIVE
        or media.face_version >= FACE_VERSION
    ):
        return False

    seen: list[tuple[float | None, DetectedFace]] = []
    pictures: dict[float | None, bytes] = {}
    if media.kind is MediaKind.VIDEO:
        if media.video_path is None:
            return False
        try:
            looks = await _looks_at_video(
                derived_root / media.video_path, video_step(media.duration_seconds)
            )
        except (FrameError, FileNotFoundError) as error:
            # No frame can be read from this one. Counted, so it is not tried for ever.
            await attempts.note_failure(session, media_id, jobs.FACES_STAGE, str(error))
            return False
        answers = await detector.detect([_data_url(jpeg, "image/jpeg") for _, jpeg in looks])
        for (second, jpeg), faces in zip(looks, answers, strict=True):
            pictures[float(second)] = jpeg
            seen.extend((float(second), face) for face in faces if _kept(face))
        seen = once_each(seen)
    else:
        path = media.preview_path or media.thumbnail_path
        if path is None:
            return False
        try:
            picture = await asyncio.to_thread((derived_root / path).read_bytes)
        except FileNotFoundError as error:
            await attempts.note_failure(session, media_id, jobs.FACES_STAGE, str(error))
            return False
        mime = _MIME_TYPES.get(Path(path).suffix.lower(), "image/webp")
        (faces,) = await detector.detect([_data_url(picture, mime)])
        pictures[None] = picture
        seen = [(None, face) for face in faces if _kept(face)]

    folder = derived_root / relative_of(media_id, "")
    old = list(await session.scalars(select(Face.id).where(Face.media_id == media_id)))

    stored = await search_service.store_faces(
        session,
        media_id,
        model=model,
        faces=[
            search_service.FaceToStore(
                box=face.box,
                score=face.score,
                pixels=face.pixels,
                second=second,
                embedding=face.embedding,
                aspect=face.aspect,
            )
            for second, face in seen
        ],
    )
    await session.execute(
        update(Media).where(Media.id == media_id).values(face_version=FACE_VERSION)
    )
    await attempts.forget(session, media_id, jobs.FACES_STAGE)

    def write_crops() -> None:
        folder.mkdir(parents=True, exist_ok=True)
        for face_id in old:
            (folder / crop_name(face_id)).unlink(missing_ok=True)
        for face_id, (second, face) in zip(stored, seen, strict=True):
            try:
                (folder / crop_name(face_id)).write_bytes(crop(pictures[second], face))
            except pyvips.Error:
                continue

    await asyncio.to_thread(write_crops)
    await session.commit()
    # Who they are, right away: a person if one is close enough, else a group.
    await people.sort_faces(session, stored)
    # A video shows the same people frame after frame, and a collage or a picture of a picture
    # shows them more than once too. One face per person is enough either way.
    await collapse_media_faces(session, media_id, derived_root)
    return True


async def collapse_media_faces(
    session: AsyncSession, media_id: uuid.UUID, derived_root: Path
) -> int:
    """One medium's repeated sightings, and the square pictures that belonged to them."""
    removed = await people.collapse_duplicates(session, media_id)
    if not removed:
        return 0

    def remove_crops() -> None:
        for face_id in removed:
            (derived_root / relative_of(media_id, crop_name(face_id))).unlink(missing_ok=True)

    await asyncio.to_thread(remove_crops)
    return len(removed)


async def collapse_all_videos(session: AsyncSession, derived_root: Path) -> int:
    """Every video that shows one person more than once. Returns how many faces went.

    For after a reassessment: a name given today can put a person on a medium they were already
    on, which is a duplicate the moment it happens.
    """
    twice = (
        select(Face.media_id)
        .where(Face.person_id.is_not(None))
        .group_by(Face.media_id, Face.person_id)
        .having(func.count() > 1)
    )
    answered = aliased(Face)
    guessed = (
        select(Face.media_id)
        .join(
            answered,
            (answered.media_id == Face.media_id) & (answered.person_id == Face.suggested_person_id),
        )
        .where(Face.person_id.is_(None))
    )
    media_ids = set(await session.scalars(twice)) | set(await session.scalars(guessed))
    return sum(
        [await collapse_media_faces(session, media_id, derived_root) for media_id in media_ids]
    )


def _missing() -> Select[tuple[uuid.UUID]]:
    """Media this stage could look at now.

    What it looks at has to be there: a picture is read from its preview, a video from its 720p
    version. A video that has only a poster - because its transcode failed, or has not run yet -
    was counted as outstanding here, handed out every minute, and skipped every time without a
    word, so one film sat in "Medien ohne Gesichtersuche" for ever. It belongs to stage 2 until
    that stage has made what this one reads, and stage 2 counts its own failures.
    """
    ready = or_(
        and_(Media.kind == MediaKind.VIDEO, Media.video_path.is_not(None)),
        and_(Media.kind == MediaKind.IMAGE, Media.thumbnail_path.is_not(None)),
    )
    return select(Media.id).where(
        Media.status == MediaStatus.ACTIVE,
        Media.duplicate_of.is_(None),
        ready,
        Media.face_version < FACE_VERSION,
        attempts.still_open(jobs.FACES_STAGE, Media.id),
    )


async def media_without(session: AsyncSession, *, limit: int = 200) -> list[uuid.UUID]:
    """Media not looked at for faces yet, newest first."""
    rows = await session.scalars(
        _missing()
        .order_by(func.coalesce(Media.taken_at, Media.created_at).desc(), Media.id)
        .limit(limit)
    )
    return list(rows)


async def count_without(session: AsyncSession) -> int:
    return int(await session.scalar(select(func.count()).select_from(_missing().subquery())) or 0)


async def enabled(session: AsyncSession) -> bool:
    """Whether the admin has faces switched on."""
    from muninn.settings import service as settings_service

    return (await settings_service.get_settings(session)).faces_enabled


async def forget_all(session: AsyncSession, derived_root: Path) -> tuple[int, int]:
    """Every face, every person, every square picture - gone. Returns how many faces and persons.

    Media are marked as not looked at, so switching faces on again finds them anew.
    """
    from muninn.models.face import FaceRejection, Person

    faces = list(await session.execute(select(Face.id, Face.media_id)))
    persons = int(await session.scalar(select(func.count()).select_from(Person)) or 0)

    def remove_crops() -> None:
        for face_id, media_id in faces:
            (derived_root / relative_of(media_id, crop_name(face_id))).unlink(missing_ok=True)

    await asyncio.to_thread(remove_crops)
    await session.execute(delete(FaceRejection))
    await session.execute(delete(Face))
    await session.execute(delete(Person))
    await session.execute(update(Media).where(Media.face_version > 0).values(face_version=0))
    await session.commit()
    return len(faces), persons
