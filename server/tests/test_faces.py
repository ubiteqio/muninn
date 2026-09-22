"""Stage 7: the faces in a medium, found by the face model and kept with their vectors."""

import json
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from muninn.ai.base import Check, DetectedFace
from muninn.ai.openai_compatible import OpenAiFaceDetector
from muninn.faces import service
from muninn.models.face import Face
from muninn.models.media import Media, MediaKind
from tests.test_timeline import JULY, a_medium, an_album

pytestmark = pytest.mark.usefixtures("api_client")

has_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg")


def a_face(x: float, *, pixels: int = 120, score: float = 0.9, vector: int = 0) -> DetectedFace:
    embedding = [0.0] * 8
    embedding[vector] = 1.0
    return DetectedFace(box=(x, 0.1, x + 0.2, 0.4), score=score, embedding=embedding, pixels=pixels)


class FakeDetector:
    def __init__(self, faces: list[list[DetectedFace]]) -> None:
        self.faces = faces
        self.asked: list[int] = []

    async def detect(self, images: Sequence[str]) -> list[list[DetectedFace]]:
        self.asked.append(len(images))
        return [self.faces[index % len(self.faces)] for index in range(len(images))]

    async def check(self) -> Check:
        return Check(ok=True, detail="", milliseconds=0)


async def a_photo(session: AsyncSession, derived: Path) -> Media:
    medium = await a_medium(session, await an_album(session, "Fest"), taken_at=JULY, name="a.jpg")
    medium.thumbnail_path = "p/thumb.webp"
    medium.preview_path = "p/preview.webp"
    (derived / "p").mkdir(parents=True, exist_ok=True)
    (derived / "p" / "preview.webp").write_bytes(b"RIFF-a-preview")
    await session.commit()
    return medium


async def test_faces_too_small_or_unsure_are_left_out(
    session: AsyncSession, tmp_path: Path
) -> None:
    medium = await a_photo(session, tmp_path)
    detector = FakeDetector(
        [[a_face(0.1), a_face(0.5, pixels=30), a_face(0.7, score=0.4), a_face(0.3, vector=1)]]
    )

    assert await service.apply_faces(
        session, medium.id, detector=detector, model="buffalo_l", derived_root=tmp_path
    )

    faces = list(await session.scalars(select(Face).order_by(Face.box_left)))
    assert [round(face.box_left, 1) for face in faces] == [0.1, 0.3]
    assert {face.model for face in faces} == {"buffalo_l"}
    dimensions = await session.scalar(text("SELECT DISTINCT dimensions FROM faces"))
    assert dimensions == 8
    await session.refresh(medium)
    assert medium.face_version == service.FACE_VERSION
    # Looked at once is enough; nothing is asked again.
    assert not await service.apply_faces(
        session, medium.id, detector=detector, model="buffalo_l", derived_root=tmp_path
    )
    assert detector.asked == [1]
    assert await service.media_without(session) == []


async def test_a_picture_without_faces_is_done_too(session: AsyncSession, tmp_path: Path) -> None:
    medium = await a_photo(session, tmp_path)

    assert await service.media_without(session) == [medium.id]
    await service.apply_faces(
        session, medium.id, detector=FakeDetector([[]]), model="buffalo_l", derived_root=tmp_path
    )

    assert await service.media_without(session) == []
    assert await service.count_without(session) == 0


def test_a_long_video_is_looked_at_less_often() -> None:
    assert service.video_step(90) == 5
    assert service.video_step(120) == 5
    assert service.video_step(121) == 15
    assert service.video_step(None) == 5


def test_the_same_person_seen_again_in_a_video_counts_once() -> None:
    blurred = a_face(0.1, pixels=50)
    sharp = a_face(0.4, pixels=200)
    other = a_face(0.6, vector=3)

    kept = service.once_each([(0.0, blurred), (10.0, sharp), (10.0, other)])

    assert kept == [(10.0, sharp), (10.0, other)]


def a_blue_clip(path: Path, *, seconds: int) -> None:
    path.parent.mkdir()
    subprocess.run(  # noqa: S603
        [shutil.which("ffmpeg") or "ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
         f"color=c=blue:s=320x240:r=5:d={seconds}", "-c:v", "libx264", "-pix_fmt", "yuv420p",
         str(path)],
        check=True,
    )  # fmt: skip


@has_ffmpeg
async def test_a_short_video_is_looked_at_every_five_seconds(
    session: AsyncSession, tmp_path: Path
) -> None:
    a_blue_clip(tmp_path / "v" / "video.mp4", seconds=25)
    medium = await a_photo(session, tmp_path)
    medium.kind = MediaKind.VIDEO
    medium.video_path = "v/video.mp4"
    await session.commit()
    detector = FakeDetector([[a_face(0.2)]])

    await service.apply_faces(
        session, medium.id, detector=detector, model="buffalo_l", derived_root=tmp_path
    )

    # Every five seconds of a short video - and the same face in all five looks is one face.
    assert detector.asked == [5]
    (face,) = await session.scalars(select(Face))
    assert face.second == 0.0


async def test_the_client_turns_pixels_into_fractions() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "index": 0,
                        "width": 1000,
                        "height": 500,
                        "faces": [
                            {
                                "box": [100, 50, 300, 250],
                                "score": 0.93,
                                "landmarks": [[0, 0]] * 5,
                                "embedding": [0.5] * 4,
                            }
                        ],
                    }
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        detector = OpenAiFaceDetector(
            base_url="http://gpu:8100/v1", model="buffalo_l", client=client
        )
        (faces,) = await detector.detect(["data:image/jpeg;base64,AAAA"])

    assert seen["url"] == "http://gpu:8100/v1/faces"
    assert seen["body"] == {"model": "buffalo_l", "input": ["data:image/jpeg;base64,AAAA"]}
    assert faces == [
        DetectedFace(
            box=(0.1, 0.1, 0.3, 0.5), score=0.93, embedding=[0.5] * 4, pixels=200, aspect=2.0
        )
    ]
