"""Videos in stage 5: a frame per second, only the ones that show something new, one answer."""

import asyncio
import os
import shutil
import subprocess
import uuid
from collections.abc import Sequence
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from muninn.ai.analysis import Analysis
from muninn.analysis import service
from muninn.analysis.frames import ChangeFilter, Frame, frames_of, split_jpegs
from muninn.models.media import Media, MediaKind
from tests.test_timeline import JULY, a_medium, an_album

has_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is not installed")


def a_video(path: Path, colours: Sequence[tuple[str, int]]) -> Path:
    """A video made of plain colours, each lasting so many seconds."""
    inputs: list[str] = []
    for colour, seconds in colours:
        inputs += ["-f", "lavfi", "-i", f"color=c={colour}:s=320x240:r=10:d={seconds}"]
    joined = "".join(f"[{index}:v]" for index in range(len(colours)))
    subprocess.run(  # noqa: S603
        [
            shutil.which("ffmpeg") or "ffmpeg",
            "-v",
            "error",
            "-y",
            *inputs,
            "-filter_complex",
            f"{joined}concat=n={len(colours)}:v=1[out]",
            "-map",
            "[out]",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],
        check=True,
    )
    return path


def answer(caption: str, **fields: object) -> Analysis:
    base: dict[str, object] = {
        "caption": caption,
        "tags": [],
        "scene": "",
        "ocr_text": "",
        "people_count": 0,
        "time_of_day": "tag",
        "is_screenshot": False,
        "is_document": False,
        "quality": "gut",
    }
    return Analysis.model_validate(base | fields)


class TestCuttingTheStream:
    def test_complete_pictures_come_out_and_the_rest_waits(self) -> None:
        first = b"\xff\xd8one\xff\xd9"
        second = b"\xff\xd8two\xff\xd9"

        pictures, rest = split_jpegs(first + second + b"\xff\xd8thr")

        assert pictures == [first, second]
        assert rest == b"\xff\xd8thr"

    def test_a_picture_split_across_reads_is_put_back_together(self) -> None:
        picture = b"\xff\xd8" + b"x" * 50 + b"\xff\xd9"

        start, rest = split_jpegs(picture[:20])
        end, rest = split_jpegs(rest + picture[20:])

        assert (start, end, rest) == ([], [picture], b"")


@has_ffmpeg
async def test_one_frame_per_second_goes_through_memory(tmp_path: Path) -> None:
    video = a_video(tmp_path / "clip.mp4", [("red", 3), ("blue", 2)])

    seconds = [frame.second async for frame in frames_of(video)]

    assert seconds == [0, 1, 2, 3, 4]
    # Nothing was written beside the video.
    assert await asyncio.to_thread(os.listdir, tmp_path) == ["clip.mp4"]


@has_ffmpeg
async def test_only_the_seconds_that_change_are_looked_at(tmp_path: Path) -> None:
    video = a_video(tmp_path / "clip.mp4", [("red", 3), ("blue", 3), ("blue", 2)])
    changes = ChangeFilter()

    wanted = [frame.second async for frame in frames_of(video) if changes.wants(frame)]

    assert wanted == [0, 3]


@has_ffmpeg
async def test_a_picture_that_stands_still_is_described_once(tmp_path: Path) -> None:
    """A stadium from the stands for a minute: one caption, not twelve."""
    video = a_video(tmp_path / "clip.mp4", [("gray", 7)])
    changes = ChangeFilter()

    wanted = [frame.second async for frame in frames_of(video) if changes.wants(frame)]

    assert wanted == [0]


@has_ffmpeg
async def test_the_description_looks_every_five_seconds(tmp_path: Path) -> None:
    video = a_video(tmp_path / "clip.mp4", [("red", 6), ("blue", 6)])
    changes = ChangeFilter()

    seen = [frame.second async for frame in frames_of(video, every=5)]
    wanted = [frame.second async for frame in frames_of(video, every=5) if changes.wants(frame)]

    assert seen == [0, 5, 10]
    assert wanted == [0, 10]


def test_a_video_s_answer_is_made_from_its_frames() -> None:
    frames = [
        answer("Ein Kind am Strand.", tags=["strand", "kind"], people_count=1, scene="strand"),
        answer("Zwei Kinder im Wasser.", tags=["meer", "kind"], people_count=2, scene="strand"),
        answer(
            "Ein Schild.", tags=["schild"], ocr_text="Lido", scene="straße", time_of_day="unbekannt"
        ),
    ]

    combined = service.combine("Kinder spielen am Strand.", frames)

    assert combined.caption == "Kinder spielen am Strand."
    # The word that came up most first, the rest in the order they came up.
    assert combined.tags == ["kind", "strand", "meer", "schild"]
    assert combined.people_count == 2
    assert combined.scene == "strand"
    assert combined.ocr_text == "Lido"
    assert combined.time_of_day == "tag"


class FakeAnalyzer:
    def __init__(self) -> None:
        self.contexts: list[str] = []
        self.summarized: list[list[tuple[int, str]]] = []
        self.heard: list[list[tuple[float, str]]] = []

    async def analyze(self, images: Sequence[str], *, context: str = "") -> Analysis:
        self.contexts.append(context)
        return answer(f"Bild {len(self.contexts)}", tags=["farbe"])

    async def summarize(
        self,
        moments: Sequence[tuple[int, str]],
        *,
        context: str = "",
        spoken: Sequence[tuple[float, str]] = (),
    ) -> str:
        self.summarized.append(list(moments))
        self.heard.append(list(spoken))
        return "Eine Fläche wechselt von Rot zu Blau."


async def a_video_medium(session: AsyncSession, derived: Path) -> Media:
    album = await an_album(session, "Filme")
    medium = await a_medium(session, album, taken_at=JULY, name="MOV_1.mov")
    medium.kind = MediaKind.VIDEO
    medium.duration_seconds = 10.0
    medium.video_path = f"{medium.id.hex[:2]}/{medium.id.hex}/video-1.mp4"
    target = derived / medium.video_path
    target.parent.mkdir(parents=True)
    a_video(target, [("red", 5), ("blue", 5)])
    await session.commit()
    return medium


@has_ffmpeg
@pytest.mark.usefixtures("api_client")
async def test_a_video_is_described_frame_by_frame_and_summed_up(
    session: AsyncSession, tmp_path: Path
) -> None:
    medium = await a_video_medium(session, tmp_path)
    analyzer = FakeAnalyzer()
    assert await service.media_without(session, model="qwen") == [medium.id]

    described = await service.apply_analysis(
        session, medium.id, analyzer=analyzer, model="qwen", derived_root=tmp_path
    )

    assert described is True
    assert len(analyzer.contexts) == 2
    assert analyzer.contexts[1].endswith("Standbild aus einem Video bei Sekunde 5 von 10")
    assert analyzer.summarized == [[(0, "Bild 1"), (5, "Bild 2")]]

    stored = await service.get_analysis(session, medium.id)
    assert stored is not None
    assert stored.caption == "Eine Fläche wechselt von Rot zu Blau."
    frames = await service.frames_of_video(session, medium.id)
    assert [(frame.second, frame.caption) for frame in frames] == [(0, "Bild 1"), (5, "Bild 2")]
    assert await service.media_without(session, model="qwen") == []


def test_a_frame_is_handed_over_as_a_jpeg() -> None:
    assert (
        Frame(second=0, jpeg=b"\xff\xd8\xff\xd9").data_url().startswith("data:image/jpeg;base64,")
    )


async def test_a_long_video_is_summed_up_in_stages() -> None:
    """1,700 frame captions do not fit one request; sections of them are summed up first."""
    analyzer = FakeAnalyzer()
    moments = [(second, f"Bild {second}") for second in range(250)]

    caption = await service.summarize(analyzer, moments, context="")

    assert caption == "Eine Fläche wechselt von Rot zu Blau."
    assert [len(section) for section in analyzer.summarized] == [100, 100, 50, 3]
    # A section speaks for the second it starts at.
    assert [second for second, _ in analyzer.summarized[-1]] == [0, 100, 200]


async def test_a_single_frame_needs_no_summary() -> None:
    analyzer = FakeAnalyzer()

    assert await service.summarize(analyzer, [(0, "Ein Kind.")], context="") == "Ein Kind."
    assert analyzer.summarized == []


async def test_a_long_task_keeps_its_claim_and_its_place_in_the_engine_room() -> None:
    from fakeredis import FakeAsyncRedis

    from muninn.huginn import jobs

    redis = FakeAsyncRedis(decode_responses=True)
    media_id = uuid.uuid4()
    await jobs.claim(redis, jobs.ANALYSIS_STAGE, media_id)
    await jobs.mark_active(redis, "task-1", jobs.ANALYSIS_STAGE, media_id)
    await redis.expire(jobs.claim_key(jobs.ANALYSIS_STAGE, media_id), 5)

    await jobs.keep_alive(redis, "task-1", jobs.ANALYSIS_STAGE, media_id)

    assert await redis.ttl(jobs.claim_key(jobs.ANALYSIS_STAGE, media_id)) > 3000
    assert [entry["task_id"] for entry in await jobs.active_tasks(redis)] == ["task-1"]
