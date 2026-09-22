"""Stage 3: the previews people browse through, and the signatures that deliver them."""

import shutil
import subprocess
import uuid
from pathlib import Path

import pytest
import pyvips

from muninn.core.signing import sign_media, verify_media
from muninn.huginn import derive as stage
from muninn.models.media import MediaKind

MEDIA_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
SECRET = "not-the-real-secret"

has_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is not installed")


def an_image(path: Path, *, width: int = 800, height: int = 600, red: int = 200) -> Path:
    """A real picture on disk, not a fixture pretending to be one."""
    path.parent.mkdir(parents=True, exist_ok=True)
    canvas = pyvips.Image.black(width, height, bands=3)
    image = canvas.linear([1, 1, 1], [red, 40, 90]).cast("uchar")
    image.copy(interpretation="srgb").write_to_file(str(path))
    return path


def a_video(path: Path, *, seconds: int = 1) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(  # noqa: S603 - a fixed command with a path from the test's own tmp_path
        [
            shutil.which("ffmpeg") or "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"testsrc=duration={seconds}:size=640x480:rate=10",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],
        capture_output=True,
        check=True,
        timeout=120,
    )
    return path


class TestSignedAddresses:
    def test_a_signature_opens_exactly_what_it_was_made_for(self) -> None:
        token = sign_media(MEDIA_ID, "thumb", secret=SECRET)

        assert verify_media(token, MEDIA_ID, "thumb", secret=SECRET) is True
        assert verify_media(token, MEDIA_ID, "original", secret=SECRET) is False
        assert verify_media(token, uuid.uuid4(), "thumb", secret=SECRET) is False

    def test_it_is_good_for_one_to_two_hours_and_then_worthless(self) -> None:
        token = sign_media(MEDIA_ID, "thumb", secret=SECRET, ttl_seconds=3600, now=1000)

        assert verify_media(token, MEDIA_ID, "thumb", secret=SECRET, now=7100) is True
        assert verify_media(token, MEDIA_ID, "thumb", secret=SECRET, now=7300) is False

    def test_within_one_hour_the_address_stays_the_same(self) -> None:
        """Otherwise the browser's cache never hits: every reload brings new addresses."""

        def at(now: int) -> str:
            return sign_media(MEDIA_ID, "thumb", secret=SECRET, ttl_seconds=3600, now=now)

        assert at(3600) == at(7199)
        assert at(7199) != at(7200)

    def test_another_secret_does_not_open_anything(self) -> None:
        token = sign_media(MEDIA_ID, "thumb", secret=SECRET)

        assert verify_media(token, MEDIA_ID, "thumb", secret="something-else") is False

    @pytest.mark.parametrize("token", ["", "nonsense", "1000.", "abc.def"])
    def test_nonsense_is_refused_rather_than_crashing(self, token: str) -> None:
        assert verify_media(token, MEDIA_ID, "thumb", secret=SECRET) is False


class TestImages:
    def test_a_thumbnail_and_a_preview_are_written(self, tmp_path: Path) -> None:
        source = an_image(tmp_path / "original.jpg")
        target = tmp_path / "derived"

        made = stage.derive(
            source,
            target,
            kind=MediaKind.IMAGE,
            stem="abc123",
            thumbnail_size=400,
            preview_size=2048,
            quality=82,
            video_height=720,
        )

        assert (target / made.thumbnail).exists()
        assert made.preview is not None
        assert (target / made.preview).exists()
        assert pyvips.Image.new_from_file(str(target / made.thumbnail)).width == 400
        assert (made.width, made.height) == (800, 600)

    def test_a_small_picture_is_not_blown_up(self, tmp_path: Path) -> None:
        source = an_image(tmp_path / "klein.jpg", width=120, height=90)

        made = stage.derive(
            source,
            tmp_path / "derived",
            kind=MediaKind.IMAGE,
            stem="abc123",
            thumbnail_size=400,
            preview_size=2048,
            quality=82,
            video_height=720,
        )

        assert pyvips.Image.new_from_file(str(tmp_path / "derived" / made.thumbnail)).width == 120

    def test_the_pixel_hash_follows_the_picture_not_the_file(self, tmp_path: Path) -> None:
        """The same pixels in two files give the same hash; other pixels give another."""
        first = an_image(tmp_path / "eins.png")
        same = an_image(tmp_path / "zwei.png")
        other = an_image(tmp_path / "drei.png", red=10)

        hashes = [
            stage.pixel_hash_of(pyvips.Image.new_from_file(str(path)))
            for path in (first, same, other)
        ]

        assert hashes[0] == hashes[1]
        assert hashes[0] != hashes[2]

    def test_a_file_that_cannot_be_decoded_says_so(self, tmp_path: Path) -> None:
        broken = tmp_path / "kaputt.jpg"
        broken.write_bytes(b"not a picture at all")

        with pytest.raises(stage.DeriveError):
            stage.derive(
                broken,
                tmp_path / "derived",
                kind=MediaKind.IMAGE,
                stem="abc123",
                thumbnail_size=400,
                preview_size=2048,
                quality=82,
                video_height=720,
            )


@has_ffmpeg
class TestVideos:
    def test_a_playable_version_with_a_still_is_made(self, tmp_path: Path) -> None:
        """Browsers play neither AVI nor MTS, so every video gets an H.264 version."""
        source = a_video(tmp_path / "clip.mp4")
        target = tmp_path / "derived"

        made = stage.derive(
            source,
            target,
            kind=MediaKind.VIDEO,
            stem="abc123",
            thumbnail_size=400,
            preview_size=2048,
            quality=82,
            video_height=360,
        )

        assert made.video is not None
        assert made.poster is not None
        assert (target / made.video).exists()
        assert (target / made.poster).exists()
        assert (target / made.thumbnail).exists()
        # The working copy of the still is cleaned up.
        assert not any(item.name.startswith(".poster") for item in target.iterdir())

    def test_the_duration_can_be_read_back(self, tmp_path: Path) -> None:
        source = a_video(tmp_path / "clip.mp4", seconds=2)

        duration = stage.probe_duration(source)

        assert duration is not None
        assert 1.5 < duration < 2.5


class TestTurnedPictures:
    def test_a_turned_photo_keeps_its_shape(self, tmp_path: Path) -> None:
        """The preview is turned upright, so the reported size has to be turned as well -
        otherwise the viewer stretches a portrait photo into a landscape one."""
        source = tmp_path / "hochkant.jpg"
        canvas = pyvips.Image.black(800, 600, bands=3)
        picture = canvas.linear([1, 1, 1], [200, 40, 90]).cast("uchar").copy(interpretation="srgb")
        # 6 is "turn a quarter clockwise", what a phone held upright writes.
        picture = picture.copy()
        picture.set_type(pyvips.GValue.gint_type, "orientation", 6)
        picture.write_to_file(str(source))

        made = stage.derive(
            source,
            tmp_path / "derived",
            kind=MediaKind.IMAGE,
            stem="abc123",
            thumbnail_size=400,
            preview_size=2048,
            quality=82,
            video_height=720,
        )

        preview = pyvips.Image.new_from_file(str(tmp_path / "derived" / (made.preview or "")))
        assert (made.width, made.height) == (600, 800)
        assert preview.width < preview.height
