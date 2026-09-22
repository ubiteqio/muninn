"""What is said in a video: its sound, sent to the speech model, kept with the times.

The sound comes from the 720p version on the SSD, turned into 16 kHz mono by ffmpeg and held in
memory. A video without a sound track, or in which nobody speaks, gets an empty transcript: that
is an answer too, and stops the clock from asking again.

Whisper has a habit on silence and music of writing the closing credits of the subtitles it was
trained on. Those sentences are known, and dropped here whatever the speech server did already.
"""

import asyncio
import re
import uuid
from pathlib import Path

from sqlalchemy import ColumnElement, Select, and_, func, literal, select, type_coerce
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.ext.asyncio import AsyncSession

from muninn.ai.base import SpokenPart, Transcriber, Transcript
from muninn.models.analysis import MediaAnalysis, MediaTranscript
from muninn.models.media import Media, MediaKind, MediaStatus

#: Raise it when the way sound is prepared or cleaned changes.
TRANSCRIPT_VERSION = 1

#: How long ffmpeg may take to pull the sound out of one video.
EXTRACT_TIMEOUT_SECONDS = 600

#: What Whisper writes when there is nothing to write: subtitle credits and sign-offs from its
#: training data. Compared without case, punctuation and spaces.
PHANTOM_SENTENCES = (
    "untertitel der amara.org-community",
    "untertitel im auftrag des zdf",
    "untertitel im auftrag des zdf für funk",
    "untertitelung des zdf",
    "untertitel von stephanie geiges",
    "vielen dank fürs zuschauen",
    "vielen dank für's zuschauen",
    "danke fürs zuschauen",
    "bis zum nächsten mal",
    "copyright wdr",
    "swr",
    "thanks for watching",
    "thank you for watching",
    "subtitles by the amara.org community",
    "please subscribe",
)
_PHANTOM_PATTERN = re.compile(r"amara\.org|untertitel(ung)? (im auftrag|des|von)", re.IGNORECASE)


def _plain(text: str) -> str:
    return re.sub(r"[^\w.'-]+", " ", text.lower()).strip(" .!")


def is_phantom(text: str) -> bool:
    """Whether a spoken part is one of Whisper's invented sign-offs."""
    plain = _plain(text)
    return (
        not plain
        or plain in {_plain(s) for s in PHANTOM_SENTENCES}
        or bool(_PHANTOM_PATTERN.search(text))
    )


def cleaned(transcript: Transcript) -> Transcript:
    """Without invented sentences, and without a part that only repeats the one before it."""
    parts: list[SpokenPart] = []
    for part in transcript.parts:
        if is_phantom(part.text):
            continue
        if parts and _plain(parts[-1].text) == _plain(part.text):
            continue
        parts.append(part)
    return Transcript(language=transcript.language if parts else "", parts=parts)


class SoundError(Exception):
    """ffmpeg could not read the video at all."""


async def sound_of(video: Path) -> bytes | None:
    """The video's sound as a 16 kHz mono WAV, or nothing when it has no sound track."""
    process = await asyncio.create_subprocess_exec(
        "ffmpeg",
        "-nostdin",
        "-v",
        "error",
        "-i",
        str(video),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "pcm_s16le",
        "-f",
        "wav",
        "-",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        async with asyncio.timeout(EXTRACT_TIMEOUT_SECONDS):
            wav, problem = await process.communicate()
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()

    if process.returncode != 0:
        message = problem.decode(errors="replace")
        if "does not contain any stream" in message or "matches no streams" in message:
            return None
        raise SoundError(f"ffmpeg could not read the sound of {video.name}: {message[:200]}")
    # A WAV header and nothing after it: the track exists, but is empty.
    return wav if len(wav) > 44 else None


def _missing(model: str, version: int) -> Select[tuple[uuid.UUID]]:
    heard = (
        select(literal(1))
        .where(
            MediaTranscript.media_id == Media.id,
            MediaTranscript.model == model,
            MediaTranscript.version >= version,
        )
        .exists()
    )
    return select(Media.id).where(
        Media.status == MediaStatus.ACTIVE,
        Media.kind == MediaKind.VIDEO,
        Media.video_path.is_not(None),
        ~heard,
    )


async def media_without(
    session: AsyncSession, *, model: str, version: int = TRANSCRIPT_VERSION, limit: int = 200
) -> list[uuid.UUID]:
    """Videos not yet listened to by this speech model, newest first."""
    rows = await session.scalars(
        _missing(model, version)
        .order_by(func.coalesce(Media.taken_at, Media.created_at).desc(), Media.id)
        .limit(limit)
    )
    return list(rows)


async def count_without(
    session: AsyncSession, *, model: str, version: int = TRANSCRIPT_VERSION
) -> int:
    query = select(func.count()).select_from(_missing(model, version).subquery())
    return int(await session.scalar(query) or 0)


def heard_by(model: str) -> ColumnElement[bool]:
    """A condition for other stages: this video's transcript from this model is there."""
    return (
        select(literal(1))
        .where(and_(MediaTranscript.media_id == Media.id, MediaTranscript.model == model))
        .exists()
    )


async def get_transcript(session: AsyncSession, media_id: uuid.UUID) -> MediaTranscript | None:
    return await session.get(MediaTranscript, media_id)


async def apply_transcription(
    session: AsyncSession,
    media_id: uuid.UUID,
    *,
    transcriber: Transcriber,
    model: str,
    derived_root: Path,
) -> bool:
    """Listen to one video. Returns whether a transcript was stored."""
    media = await session.get(Media, media_id)
    if (
        media is None
        or media.status is not MediaStatus.ACTIVE
        or media.kind is not MediaKind.VIDEO
        or media.video_path is None
    ):
        return False

    stored = await session.get(MediaTranscript, media_id)
    if stored is not None and stored.model == model and stored.version >= TRANSCRIPT_VERSION:
        return False

    video = derived_root / media.video_path
    if not await asyncio.to_thread(video.is_file):
        return False

    wav = await sound_of(video)
    transcript = cleaned(await transcriber.transcribe(wav)) if wav else Transcript()
    await store(session, media_id, model=model, transcript=transcript)
    await session.commit()
    return True


async def store(
    session: AsyncSession, media_id: uuid.UUID, *, model: str, transcript: Transcript
) -> MediaTranscript:
    """Keep the transcript, replacing an older one. The caller commits.

    The video's description was summed up with the old words in mind, so it goes and stage 5
    describes the video again.
    """
    row = await session.get(MediaTranscript, media_id)
    replacing = row is not None
    if row is None:
        row = MediaTranscript(media_id=media_id)
        session.add(row)

    row.model = model
    row.version = TRANSCRIPT_VERSION
    row.language = transcript.language
    row.text = transcript.text
    row.segments = [
        {"start": round(part.start, 2), "end": round(part.end, 2), "text": part.text}
        for part in transcript.parts
    ]
    row.search_tsv = _search_text(transcript)
    row.transcribed_at = func.now()

    if replacing:
        analysis = await session.get(MediaAnalysis, media_id)
        if analysis is not None:
            await session.delete(analysis)
    return row


def _search_text(transcript: Transcript) -> ColumnElement[str]:
    """German stems for German speech; any other language word for word."""
    config = "german" if transcript.language in ("", "de") else "simple"
    return type_coerce(func.to_tsvector(config, transcript.text), TSVECTOR)
