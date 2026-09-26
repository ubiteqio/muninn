"""Stage 5: asking the describing model about each medium, and keeping its answer.

The model gets the 2048-pixel preview scaled down to 1280, as the concept asks: enough to read a
sign, small enough that a request stays cheap. Album and date go along as a hint.
"""

import asyncio
import base64
import uuid
from collections import Counter
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import pyvips
from sqlalchemy import (
    ColumnElement,
    Select,
    and_,
    delete,
    func,
    literal,
    literal_column,
    or_,
    select,
    true,
    type_coerce,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from muninn.ai.analysis import Analysis, frame_context
from muninn.ai.base import Analyzer
from muninn.analysis import transcripts
from muninn.analysis.frames import (
    DESCRIBE_EVERY_SECONDS,
    ChangeFilter,
    FrameError,
    frames_of,
)
from muninn.huginn import attempts, jobs
from muninn.models.analysis import MediaAnalysis, MediaTranscript, VideoFrame
from muninn.models.media import Media, MediaKind, MediaStatus
from muninn.search import service as search_service

#: Raise it when the prompt or the form changes; every medium is then described again, and the
#: old answer keeps serving searches until the new one is there.
ANALYSIS_VERSION = 1

#: The longest edge the model gets to see.
ANALYSIS_EDGE = 1280

#: A video's tags are those of its frames; this many of the most frequent ones are kept.
MAX_VIDEO_TAGS = 15

#: How many frame captions go into one summary request. A long video is summed up in stages:
#: sections of this many first, then the sections, so no request outgrows the model's context.
SUMMARY_SECTION = 100

#: Called after every frame of a video, so a long one can say that it is still being worked on.
Heartbeat = Callable[[], Awaitable[None]]


def _missing(
    model: str, version: int, transcriber_model: str | None = None
) -> Select[tuple[uuid.UUID]]:
    """Media with something to look at and no answer from this model at this stage version.

    A photo needs its preview, a video its 720p version: that is where the frames come from.
    With a speech model in use, a video also waits for its transcript, so its summary can say
    what is said in it - but not for ever: one that will never be transcribed, because the
    pipeline has given up on it, is described from its pictures alone. Otherwise a handful of
    videos would sit in "ohne Beschreibung" with nobody left to take them.
    """
    answered = (
        select(literal(1))
        .where(
            MediaAnalysis.media_id == Media.id,
            MediaAnalysis.model == model,
            MediaAnalysis.version >= version,
        )
        .exists()
    )
    viewable = or_(
        and_(Media.kind == MediaKind.IMAGE, Media.preview_path.is_not(None)),
        and_(
            Media.kind == MediaKind.VIDEO,
            Media.video_path.is_not(None),
            or_(
                transcripts.heard_by(transcriber_model),
                ~attempts.still_open(jobs.TRANSCRIPTION_STAGE, Media.id),
            )
            if transcriber_model
            else true(),
        ),
    )
    return select(Media.id).where(
        Media.status == MediaStatus.ACTIVE,
        viewable,
        ~answered,
        attempts.still_open(jobs.ANALYSIS_STAGE, Media.id),
    )


async def media_without(
    session: AsyncSession,
    *,
    model: str,
    version: int = ANALYSIS_VERSION,
    limit: int = 200,
    transcriber_model: str | None = None,
) -> list[uuid.UUID]:
    """What still needs describing, newest first - the second wave of the concept."""
    rows = await session.scalars(
        _missing(model, version, transcriber_model)
        .order_by(func.coalesce(Media.taken_at, Media.created_at).desc(), Media.id)
        .limit(limit)
    )
    return list(rows)


async def count_without(
    session: AsyncSession,
    *,
    model: str,
    version: int = ANALYSIS_VERSION,
    transcriber_model: str | None = None,
) -> int:
    query = select(func.count()).select_from(_missing(model, version, transcriber_model).subquery())
    return int(await session.scalar(query) or 0)


async def get_analysis(session: AsyncSession, media_id: uuid.UUID) -> MediaAnalysis | None:
    return await session.get(MediaAnalysis, media_id)


async def apply_analysis(
    session: AsyncSession,
    media_id: uuid.UUID,
    *,
    analyzer: Analyzer,
    model: str,
    derived_root: Path,
    heartbeat: Heartbeat | None = None,
) -> bool:
    """Stage 5 for one medium. Returns whether an answer was stored.

    Idempotent: a medium that already has an answer from this model and version is skipped.
    """
    media = await session.scalar(
        select(Media).where(Media.id == media_id).options(selectinload(Media.album))
    )
    if media is None or media.status is not MediaStatus.ACTIVE:
        return False

    stored = await session.get(MediaAnalysis, media_id)
    if stored is not None and stored.model == model and stored.version >= ANALYSIS_VERSION:
        return False

    if media.kind is MediaKind.VIDEO:
        return await _describe_video(
            session,
            media,
            analyzer=analyzer,
            model=model,
            derived_root=derived_root,
            heartbeat=heartbeat,
        )

    if media.preview_path is None:
        return False
    try:
        picture = await asyncio.to_thread(_scaled, derived_root / media.preview_path)
    except FileNotFoundError:
        # Stage 3 makes it again; until then there is nothing to look at.
        return False

    answer = await analyzer.analyze([picture], context=_context(media))
    await store(session, media_id, model=model, analysis=answer)
    await session.commit()
    return True


async def _describe_video(
    session: AsyncSession,
    media: Media,
    *,
    analyzer: Analyzer,
    model: str,
    derived_root: Path,
    heartbeat: Heartbeat | None = None,
) -> bool:
    """A video second by second: every frame that shows something new gets its own question.

    The answers are joined into one for the whole video - the tags of all frames, the text seen
    anywhere, the most people at once - and one short question without a picture turns the frame
    captions into a caption for the video. The frames keep their own answers with their second.
    """
    if media.video_path is None:
        return False
    video = derived_root / media.video_path
    if not video.is_file():
        return False

    context = _context(media)
    changes = ChangeFilter()
    seen: list[tuple[int, Analysis]] = []
    try:
        async for frame in frames_of(video, every=DESCRIBE_EVERY_SECONDS):
            if not await asyncio.to_thread(changes.wants, frame):
                continue
            answer = await analyzer.analyze(
                [frame.data_url()],
                context=frame_context(context, frame.second, media.duration_seconds),
            )
            seen.append((frame.second, answer))
            if heartbeat is not None:
                await heartbeat()
    except FrameError as error:
        # No frame can be read from this one, and that will not change by asking again. Counted
        # like faces counts it, so the clock leaves the video alone instead of chewing it for
        # ever - and an admin reads the sentence in the engine room.
        await attempts.note_failure(session, media.id, jobs.ANALYSIS_STAGE, str(error))
        return False

    if not seen:
        return False

    heard = await session.get(MediaTranscript, media.id)
    spoken = [(float(part["start"]), str(part["text"])) for part in heard.segments] if heard else []
    caption = await summarize(
        analyzer,
        [(second, answer.caption) for second, answer in seen],
        context=context,
        spoken=spoken,
    )

    await store_frames(session, media.id, seen)
    await store(session, media.id, model=model, analysis=combine(caption, [a for _, a in seen]))
    await session.commit()
    return True


async def summarize(
    analyzer: Analyzer,
    moments: list[tuple[int, str]],
    *,
    context: str,
    spoken: list[tuple[float, str]] | None = None,
) -> str:
    """One caption for the whole video, in stages when there are too many frames for one go.

    What is said goes into the last request, the one that writes the caption for the whole
    video. A single frame with nothing said needs no summary at all.
    """
    if len(moments) == 1 and not spoken:
        return moments[0][1]
    while len(moments) > SUMMARY_SECTION:
        # Each section speaks for the second it starts at.
        moments = [
            (
                moments[start][0],
                await analyzer.summarize(moments[start : start + SUMMARY_SECTION], context=context),
            )
            for start in range(0, len(moments), SUMMARY_SECTION)
        ]
    if len(moments) == 1 and not spoken:
        return moments[0][1]
    return await analyzer.summarize(moments, context=context, spoken=spoken or [])


def combine(caption: str, answers: list[Analysis]) -> Analysis:
    """One answer for a whole video from the answers about its frames."""
    counted = Counter(tag for answer in answers for tag in answer.tags)
    # The words that come up most, in the order they first came up among equals.
    order = {tag: index for index, tag in enumerate(dict.fromkeys(counted.elements()))}
    tags = sorted(counted, key=lambda tag: (-counted[tag], order[tag]))[:MAX_VIDEO_TAGS]

    texts = list(dict.fromkeys(answer.ocr_text for answer in answers if answer.ocr_text))
    half = len(answers) / 2

    def most_common(values: list[str], *, besides: str = "") -> str:
        known = [value for value in values if value and value != besides] or values
        return Counter(known).most_common(1)[0][0] if known else ""

    return Analysis.model_validate(
        {
            "caption": caption[:600],
            "tags": tags,
            "scene": most_common([answer.scene for answer in answers]),
            "ocr_text": " · ".join(texts)[:2000],
            "people_count": max(answer.people_count for answer in answers),
            "time_of_day": most_common(
                [answer.time_of_day for answer in answers], besides="unbekannt"
            ),
            "is_screenshot": sum(answer.is_screenshot for answer in answers) > half,
            "is_document": sum(answer.is_document for answer in answers) > half,
            "quality": most_common([answer.quality for answer in answers]),
        }
    )


async def store_frames(
    session: AsyncSession, media_id: uuid.UUID, seen: list[tuple[int, Analysis]]
) -> None:
    """Replace what was kept about the frames of this video. The caller commits."""
    await session.execute(delete(VideoFrame).where(VideoFrame.media_id == media_id))
    for second, answer in seen:
        session.add(
            VideoFrame(
                media_id=media_id,
                second=second,
                caption=answer.caption,
                tags=answer.tags,
                ocr_text=answer.ocr_text,
                people_count=answer.people_count,
                search_tsv=_search_text(answer),
            )
        )


async def frames_of_video(session: AsyncSession, media_id: uuid.UUID) -> list[VideoFrame]:
    rows = await session.scalars(
        select(VideoFrame).where(VideoFrame.media_id == media_id).order_by(VideoFrame.second)
    )
    return list(rows)


async def store(
    session: AsyncSession, media_id: uuid.UUID, *, model: str, analysis: Analysis
) -> MediaAnalysis:
    """Keep the answer, replacing an older one. The caller commits.

    The caption vector of stage 6 belonged to the old caption, so it goes; the clock will ask
    for a new one.
    """
    row = await session.get(MediaAnalysis, media_id)
    if row is None:
        row = MediaAnalysis(media_id=media_id)
        session.add(row)

    row.model = model
    row.version = ANALYSIS_VERSION
    row.caption = analysis.caption
    row.tags = analysis.tags
    row.scene = analysis.scene
    row.ocr_text = analysis.ocr_text
    row.people_count = analysis.people_count
    row.time_of_day = analysis.time_of_day
    row.is_screenshot = analysis.is_screenshot
    row.is_document = analysis.is_document
    row.quality = analysis.quality
    row.analyzed_at = func.now()
    row.search_tsv = _search_text(analysis)

    await search_service.forget(session, search_service.VectorKind.CAPTION, media_id)
    return row


def _search_text(analysis: Analysis) -> ColumnElement[Any]:
    """German full text: the caption counts most, then tags and scene, then text in the picture
    and the time of day. Migration 0016 writes the same for answers stored before."""

    def weighted(text: str, weight: str) -> ColumnElement[Any]:
        # The weight is one of three fixed letters, and PostgreSQL wants it as its own "char".
        return func.setweight(func.to_tsvector("german", text), literal_column(f"'{weight}'"))

    combined = (
        weighted(analysis.caption, "A")
        .op("||")(weighted(" ".join([*analysis.tags, analysis.scene]), "B"))
        .op("||")(weighted(f"{analysis.ocr_text} {analysis.time_of_day}", "C"))
    )
    return type_coerce(combined, TSVECTOR)


def _context(media: Media) -> str:
    """What is known about the picture without looking at it."""
    parts = []
    if media.album.relative_path:
        parts.append(f"Album „{media.album.relative_path}“")
    if media.taken_at is not None and not media.date_is_estimated:
        parts.append(f"aufgenommen am {media.taken_at:%d.%m.%Y}")
    elif media.taken_at is not None:
        parts.append(f"ungefähr aus dem Jahr {media.taken_at:%Y}")
    return ", ".join(parts)


def _scaled(path: Path) -> str:
    """The preview at no more than 1280 pixels, as a data URL."""
    if not path.is_file():
        raise FileNotFoundError(path)
    image = pyvips.Image.thumbnail(str(path), ANALYSIS_EDGE, height=ANALYSIS_EDGE)
    data: bytes = image.webpsave_buffer(Q=85)
    return f"data:image/webp;base64,{base64.b64encode(data).decode('ascii')}"
