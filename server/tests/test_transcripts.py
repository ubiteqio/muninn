"""What is said in a video: the sound, the speech model, and what becomes of its answer."""

import json
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Any

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from muninn.ai import service as ai_service
from muninn.ai.base import AiUnreachableError, SpokenPart, Transcript
from muninn.ai.openai_compatible import OpenAiTranscriber
from muninn.analysis import service, transcripts
from muninn.huginn import attempts, jobs, tasks
from muninn.models.ai import AiKind
from muninn.models.attempt import GIVE_UP_AFTER
from muninn.models.media import Media, MediaKind
from muninn.models.user import UserRole
from tests.helpers import auth_header, create_user, login
from tests.test_image_vectors import (  # noqa: F401 - both are fixtures
    fake_redis_client,
    worker_database,
)
from tests.test_timeline import JULY, a_medium, an_album
from tests.test_video_frames import FakeAnalyzer, has_ffmpeg

GUCK_MAL = [SpokenPart(start=1.0, end=2.5, text="Guck mal, Papa!")]


def a_clip(path: Path, *, sound: bool) -> Path:
    """Three seconds of red, with a tone underneath or without any sound track."""
    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
    inputs = ["-f", "lavfi", "-i", "color=c=red:s=320x240:r=10:d=3"]
    if sound:
        inputs += ["-f", "lavfi", "-i", "sine=frequency=440:duration=3"]
    subprocess.run(  # noqa: S603
        [ffmpeg, "-v", "error", "-y", *inputs, "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)],
        check=True,
    )
    return path


class FakeListener:
    def __init__(self, parts: list[SpokenPart] | None = None) -> None:
        self.parts = GUCK_MAL if parts is None else parts
        self.heard: list[bytes] = []

    async def transcribe(self, wav: bytes) -> Transcript:
        self.heard.append(wav)
        return Transcript(language="de", parts=self.parts)


async def a_video(session: AsyncSession, derived: Path, *, sound: bool = True) -> Media:
    album = await an_album(session, "Filme")
    medium = await a_medium(session, album, taken_at=JULY, name="MOV_1.mov")
    medium.kind = MediaKind.VIDEO
    medium.duration_seconds = 3.0
    medium.video_path = f"{medium.id.hex[:2]}/{medium.id.hex}/video-1.mp4"
    target = derived / medium.video_path
    target.parent.mkdir(parents=True)
    a_clip(target, sound=sound)
    await session.commit()
    return medium


class TestPhantoms:
    @pytest.mark.parametrize(
        "text",
        [
            "Untertitel der Amara.org-Community",
            "Untertitel im Auftrag des ZDF, 2021",
            "Vielen Dank fürs Zuschauen!",
            "  ...  ",
        ],
    )
    def test_whispers_invented_sign_offs_are_recognised(self, text: str) -> None:
        assert transcripts.is_phantom(text)

    def test_what_somebody_says_is_kept(self) -> None:
        assert not transcripts.is_phantom("Vielen Dank, Oma, für den Kuchen!")

    def test_a_part_that_only_repeats_the_one_before_goes(self) -> None:
        heard = Transcript(
            language="de",
            parts=[
                SpokenPart(0, 1, "Hallo!"),
                SpokenPart(1, 2, "hallo"),
                SpokenPart(2, 3, "Untertitel der Amara.org-Community"),
                SpokenPart(3, 4, "Tschüss!"),
            ],
        )

        assert [part.text for part in transcripts.cleaned(heard).parts] == ["Hallo!", "Tschüss!"]

    def test_nothing_left_means_no_language_either(self) -> None:
        heard = Transcript(language="de", parts=[SpokenPart(0, 1, "Vielen Dank fürs Zuschauen")])

        assert transcripts.cleaned(heard) == Transcript()


class TestTheQuestion:
    async def test_the_sound_goes_up_as_a_file_and_comes_back_with_times(self) -> None:
        seen: dict[str, Any] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            seen["body"] = request.content
            return httpx.Response(
                200,
                json={
                    "language": "de",
                    "text": "Guck mal, Papa!",
                    "segments": [{"id": 0, "start": 1.0, "end": 2.5, "text": " Guck mal, Papa! "}],
                },
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            listener = OpenAiTranscriber(
                base_url="http://gpu:8100/v1", model="whisper", client=client
            )
            heard = await listener.transcribe(b"RIFF....WAVE")

        assert seen["url"] == "http://gpu:8100/v1/audio/transcriptions"
        assert b'name="response_format"' in seen["body"]
        assert b"verbose_json" in seen["body"]
        assert heard == Transcript(language="de", parts=GUCK_MAL)

    async def test_the_connection_test_sends_a_second_of_silence(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"text": "", "segments": [], "language": ""})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            listener = OpenAiTranscriber(
                base_url="http://gpu:8100/v1", model="whisper", client=client
            )
            check = await listener.check()

        assert check.ok
        assert "whisper" in check.detail


@has_ffmpeg
async def test_the_sound_of_a_video_is_16_khz_mono(tmp_path: Path) -> None:
    wav = await transcripts.sound_of(a_clip(tmp_path / "clip.mp4", sound=True))

    assert wav is not None
    assert wav[:4] == b"RIFF"
    # 16-bit mono at 16 kHz: 32,000 bytes a second, three seconds and a header.
    assert 90_000 < len(wav) < 100_000


@has_ffmpeg
async def test_a_video_without_a_sound_track_has_no_sound(tmp_path: Path) -> None:
    assert await transcripts.sound_of(a_clip(tmp_path / "clip.mp4", sound=False)) is None


@has_ffmpeg
@pytest.mark.usefixtures("api_client")
async def test_a_video_is_listened_to_once(session: AsyncSession, tmp_path: Path) -> None:
    medium = await a_video(session, tmp_path)
    listener = FakeListener()
    assert await transcripts.media_without(session, model="whisper") == [medium.id]

    heard = await transcripts.apply_transcription(
        session, medium.id, transcriber=listener, model="whisper", derived_root=tmp_path
    )
    again = await transcripts.apply_transcription(
        session, medium.id, transcriber=listener, model="whisper", derived_root=tmp_path
    )

    assert (heard, again) == (True, False)
    assert len(listener.heard) == 1
    stored = await transcripts.get_transcript(session, medium.id)
    assert stored is not None
    assert stored.segments == [{"start": 1.0, "end": 2.5, "text": "Guck mal, Papa!"}]
    assert await transcripts.media_without(session, model="whisper") == []


@has_ffmpeg
@pytest.mark.usefixtures("api_client")
async def test_a_silent_video_gets_an_empty_transcript_without_asking(
    session: AsyncSession, tmp_path: Path
) -> None:
    medium = await a_video(session, tmp_path, sound=False)
    listener = FakeListener()

    assert await transcripts.apply_transcription(
        session, medium.id, transcriber=listener, model="whisper", derived_root=tmp_path
    )

    assert listener.heard == []
    stored = await transcripts.get_transcript(session, medium.id)
    assert stored is not None
    assert (stored.text, stored.segments) == ("", [])


@has_ffmpeg
@pytest.mark.usefixtures("api_client")
async def test_with_a_speech_model_a_video_waits_for_its_transcript_and_its_summary_hears_it(
    session: AsyncSession, tmp_path: Path
) -> None:
    medium = await a_video(session, tmp_path)
    assert await service.media_without(session, model="qwen", transcriber_model="whisper") == []

    await transcripts.apply_transcription(
        session, medium.id, transcriber=FakeListener(), model="whisper", derived_root=tmp_path
    )
    assert await service.media_without(session, model="qwen", transcriber_model="whisper") == [
        medium.id
    ]

    analyzer = FakeAnalyzer()
    await service.apply_analysis(
        session, medium.id, analyzer=analyzer, model="qwen", derived_root=tmp_path
    )

    # One frame, but something is said: the summary is asked for all the same.
    assert analyzer.heard == [[(1.0, "Guck mal, Papa!")]]


@has_ffmpeg
@pytest.mark.usefixtures("api_client")
async def test_a_new_transcript_asks_for_a_new_description(
    session: AsyncSession, tmp_path: Path
) -> None:
    medium = await a_video(session, tmp_path)
    await transcripts.apply_transcription(
        session, medium.id, transcriber=FakeListener(), model="whisper", derived_root=tmp_path
    )
    await service.apply_analysis(
        session, medium.id, analyzer=FakeAnalyzer(), model="qwen", derived_root=tmp_path
    )

    await transcripts.apply_transcription(
        session, medium.id, transcriber=FakeListener(), model="whisper-2", derived_root=tmp_path
    )

    assert await service.get_analysis(session, medium.id) is None


@has_ffmpeg
async def test_the_detail_view_carries_the_moments_and_what_is_said(
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
    api_client: AsyncClient,
    tmp_path: Path,
) -> None:
    medium = await a_video(session, tmp_path)
    await transcripts.apply_transcription(
        session, medium.id, transcriber=FakeListener(), model="whisper", derived_root=tmp_path
    )
    await service.apply_analysis(
        session, medium.id, analyzer=FakeAnalyzer(), model="qwen", derived_root=tmp_path
    )
    await create_user(session_factory, username="anna", display_name="Anna", role=UserRole.USER)
    headers = auth_header(await login(api_client, username="anna"))

    body = (await api_client.get(f"/media/{medium.id}", headers=headers)).json()

    assert body["analysis"]["moments"] == [{"second": 0, "caption": "Bild 1"}]
    assert body["transcript"] == {
        "language": "de",
        "parts": [{"start": 1.0, "end": 2.5, "text": "Guck mal, Papa!"}],
        "model": "whisper",
    }
    assert json.dumps(body)


async def test_a_speech_machine_that_does_not_answer_pauses_its_stage(
    monkeypatch: pytest.MonkeyPatch,
    session: AsyncSession,
    worker_database: list[str],  # noqa: F811
    fake_redis_client: object,  # noqa: F811
) -> None:
    """Like every other AI stage - instead of pulling the sound out of every video again, a
    minute later, for as long as the machine is off."""
    await ai_service.create_profile(
        session,
        kind=AiKind.TRANSCRIBER,
        name="GPU",
        base_url="http://gpu.invalid/v1",
        model="whisper-large-v3-turbo",
    )

    asked: list[uuid.UUID] = []

    async def away(_session: Any, media_id: uuid.UUID, **_kwargs: Any) -> bool:
        asked.append(media_id)
        raise AiUnreachableError("http://gpu.invalid/v1 ist nicht erreichbar.")

    monkeypatch.setattr(transcripts, "apply_transcription", away)
    first, queued = uuid.uuid4(), uuid.uuid4()
    await jobs.claim(fake_redis_client, jobs.TRANSCRIPTION_STAGE, queued)  # type: ignore[arg-type]

    await tasks._transcribe_media(first, task_id=str(uuid.uuid4()))
    # Already in the queue when the machine went away: lets go without touching the video.
    await tasks._transcribe_media(queued, task_id=str(uuid.uuid4()))

    paused = await fake_redis_client.exists(jobs.pause_key(jobs.TRANSCRIPTION_STAGE))  # type: ignore[attr-defined]
    assert paused == 1
    assert asked == [first]
    # Its claim is free, so the clock hands it out again once the pause is over.
    assert await jobs.claim(fake_redis_client, jobs.TRANSCRIPTION_STAGE, queued)  # type: ignore[arg-type]


@has_ffmpeg
@pytest.mark.usefixtures("api_client")
async def test_a_video_nobody_can_listen_to_is_described_from_its_pictures(
    session: AsyncSession, tmp_path: Path
) -> None:
    """Waiting for a transcript is right until there will never be one: a video the pipeline
    has given up listening to would otherwise sit in "ohne Beschreibung" for ever."""
    medium = await a_video(session, tmp_path)
    assert await service.media_without(session, model="qwen", transcriber_model="whisper") == []

    for _ in range(GIVE_UP_AFTER):
        await attempts.note_failure(session, medium.id, jobs.TRANSCRIPTION_STAGE, "no sound")

    assert await service.media_without(session, model="qwen", transcriber_model="whisper") == [
        medium.id
    ]
