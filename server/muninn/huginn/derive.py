"""Stage 3: the pictures people actually browse through.

Originals on the NAS are read and never written. What comes out of this stage lies on the local
SSD: a thumbnail for the grid, a larger preview for full screen, and for videos a version the
browser can play at all. The pixel hash is taken here, because this is where the image is decoded
anyway - it later tells an edited picture from one whose metadata were merely rewritten.
"""

import json
import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pyvips
from blake3 import blake3

from muninn.models.media import MediaKind

#: Raise this when the stage learns to make better derivatives; media below it are done again.
DERIVE_VERSION = 1

# libvips narrates every shrink and every mask at info level. That is useful when a picture will
# not decode and noise the rest of the time, so it only speaks up about warnings.
logging.getLogger("pyvips").setLevel(logging.WARNING)

#: Long enough for a big video, short enough that one broken file cannot block a queue forever.
TRANSCODE_TIMEOUT_SECONDS = 3600
TOOL_TIMEOUT_SECONDS = 120

#: The pixel hash is taken from a small, normalised rendering: the same picture gives the same
#: hash whatever its metadata say, and a crop or a re-compression gives a different one.
PIXEL_HASH_SIZE = 256


class DeriveError(Exception):
    """The file could not be decoded - a broken original, or a format nothing here can read."""


@dataclass(frozen=True, slots=True)
class Derivatives:
    """What stage 3 produced, as file names inside the medium's own folder."""

    thumbnail: str
    pixel_hash: str
    preview: str | None = None
    video: str | None = None
    poster: str | None = None
    width: int | None = None
    height: int | None = None


def derive(
    source: Path,
    target: Path,
    *,
    kind: MediaKind,
    stem: str,
    thumbnail_size: int,
    preview_size: int,
    quality: int,
    video_height: int,
) -> Derivatives:
    """Make every derivative of one medium. Runs in a worker, never in the API.

    libvips decodes lazily: a picture it cannot read fails while it is being written, not while
    it is opened. Everything therefore happens inside one guard, and a file nothing here can read
    becomes a DeriveError rather than a failed task.
    """
    target.mkdir(parents=True, exist_ok=True)

    try:
        if kind is MediaKind.VIDEO:
            return _derive_video(
                source,
                target,
                stem=stem,
                thumbnail_size=thumbnail_size,
                preview_size=preview_size,
                quality=quality,
                video_height=video_height,
            )

        return _derive_image(
            source,
            target,
            stem=stem,
            thumbnail_size=thumbnail_size,
            preview_size=preview_size,
            quality=quality,
        )
    except pyvips.Error as error:
        raise DeriveError(f"{source}: {error}") from error


def _derive_image(
    source: Path,
    target: Path,
    *,
    stem: str,
    thumbnail_size: int,
    preview_size: int,
    quality: int,
) -> Derivatives:
    preview_name = f"preview-{stem}.webp"
    thumbnail_name = f"thumb-{stem}.webp"

    # libvips shrinks while decoding, so asking for each size separately is cheaper than
    # decoding the full picture once and scaling it twice.
    preview = _load(source, preview_size).copy_memory()
    _write(preview, target / preview_name, quality=quality)
    _write(_load(source, thumbnail_size), target / thumbnail_name, quality=quality)

    width, height = _dimensions(source)
    return Derivatives(
        thumbnail=thumbnail_name,
        preview=preview_name,
        pixel_hash=pixel_hash_of(preview),
        width=width,
        height=height,
    )


def _derive_video(
    source: Path,
    target: Path,
    *,
    stem: str,
    thumbnail_size: int,
    preview_size: int,
    quality: int,
    video_height: int,
) -> Derivatives:
    """A 720p H.264 version, because browsers play neither AVI nor MTS nor WMV."""
    poster_source = target / f".poster-{stem}.png"
    _run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(source),
            "-frames:v",
            "1",
            # A frame from a little way in: the very first one is often black.
            "-ss",
            "1",
            str(poster_source),
        ],
        timeout=TOOL_TIMEOUT_SECONDS,
        allow_failure=True,
    )
    if not poster_source.exists():
        # Very short clips have nothing at one second; take the first frame then.
        _run(
            ["ffmpeg", "-y", "-i", str(source), "-frames:v", "1", str(poster_source)],
            timeout=TOOL_TIMEOUT_SECONDS,
        )

    poster = _load(poster_source, preview_size).copy_memory()
    poster_name = f"poster-{stem}.webp"
    thumbnail_name = f"thumb-{stem}.webp"
    _write(poster, target / poster_name, quality=quality)
    _write(_load(poster_source, thumbnail_size), target / thumbnail_name, quality=quality)
    pixel_hash = pixel_hash_of(poster)
    poster_source.unlink(missing_ok=True)

    video_name = f"video-{stem}.mp4"
    _run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(source),
            "-vf",
            f"scale=-2:min({video_height}\\,ih)",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            # Lets the browser start playing before the whole file has arrived.
            "-movflags",
            "+faststart",
            str(target / video_name),
        ],
        timeout=TRANSCODE_TIMEOUT_SECONDS,
    )
    # An exit code of nought is not a file. A tool that says it is happy and writes nothing
    # would otherwise be written down as done, and the medium would point at a path that is not
    # there - with nothing in the pipeline able to notice.
    _must_exist(target / video_name)

    return Derivatives(
        thumbnail=thumbnail_name,
        poster=poster_name,
        video=video_name,
        pixel_hash=pixel_hash,
        width=poster.width,
        height=poster.height,
    )


def _must_exist(file: Path) -> None:
    """What a tool claims to have written, checked before anybody relies on it."""
    try:
        if file.stat().st_size > 0:
            return
    except OSError as error:
        raise DeriveError(f"{file.name} was not written: {error}") from error
    raise DeriveError(f"{file.name} was written empty")


def pixel_hash_of(image: "pyvips.Image") -> str:
    """A hash over the decoded picture, small and normalised.

    Metadata are not part of it: writing a tag or correcting a capture time leaves this hash
    alone, and the expensive stages keep their results.
    """
    small = image.thumbnail_image(
        PIXEL_HASH_SIZE, height=PIXEL_HASH_SIZE, size=pyvips.enums.Size.FORCE
    )
    flattened = small.flatten() if small.hasalpha() else small
    rgb = flattened.colourspace(pyvips.enums.Interpretation.SRGB)
    return str(blake3(rgb.write_to_memory()).hexdigest())


def _load(source: Path, size: int) -> "pyvips.Image":
    """Decode a picture at most this large, with a RAW's embedded preview as the fallback.

    Never enlarges: a small original stays small rather than becoming a blurry big one. The EXIF
    orientation is applied, so a portrait photo is not delivered lying down.
    """
    try:
        image: pyvips.Image = pyvips.Image.thumbnail(
            str(source), size, height=size, size=pyvips.enums.Size.DOWN
        )
        return image
    except pyvips.Error:
        embedded = _extract_embedded_preview(source)
        if embedded is None:
            raise DeriveError(str(source)) from None
        try:
            preview: pyvips.Image = pyvips.Image.thumbnail_buffer(
                embedded, size, height=size, size=pyvips.enums.Size.DOWN
            )
            return preview
        except pyvips.Error as error:
            raise DeriveError(str(source)) from error


def _dimensions(source: Path) -> tuple[int | None, int | None]:
    """The size of the original the right way up, read from the header without decoding it.

    autorot applies the EXIF orientation, so a portrait photo is not reported as a landscape one
    - which is what stretched it in the viewer before.
    """
    try:
        header: pyvips.Image = pyvips.Image.new_from_file(str(source))
        turned: pyvips.Image = header.autorot()
        return turned.width, turned.height
    except pyvips.Error:
        return None, None


def _extract_embedded_preview(source: Path) -> bytes | None:
    """Cameras put a JPEG inside their RAW files; for 26 years of formats that is the way in."""
    executable = shutil.which("exiftool")
    if executable is None:
        return None

    for tag in ("-JpgFromRaw", "-PreviewImage", "-ThumbnailImage"):
        try:
            result = subprocess.run(  # noqa: S603 - fixed command, the only variable is a path
                [executable, "-b", tag, str(source)],
                capture_output=True,
                timeout=TOOL_TIMEOUT_SECONDS,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if result.returncode == 0 and result.stdout:
            return result.stdout
    return None


def _write(image: "pyvips.Image", target: Path, *, quality: int) -> None:
    """WebP, without the metadata: the originals keep those, the previews do not need them."""
    image.write_to_file(f"{target}[Q={quality},strip=true]")


def probe_duration(source: Path) -> float | None:
    """How long a video is, read from its streams."""
    output = _run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(source)],
        timeout=TOOL_TIMEOUT_SECONDS,
        allow_failure=True,
    )
    if output is None:
        return None
    try:
        return float(json.loads(output).get("format", {}).get("duration"))
    except (json.JSONDecodeError, TypeError, ValueError):
        return None


def _run(command: list[str], *, timeout: int, allow_failure: bool = False) -> str | None:
    executable = shutil.which(command[0])
    if executable is None:
        if allow_failure:
            return None
        raise DeriveError(f"{command[0]} is not installed")

    try:
        result = subprocess.run(  # noqa: S603 - fixed command, the only variable is a path
            [executable, *command[1:]],
            capture_output=True,
            # What these tools print is whatever was written into the file years ago. A 3GP
            # from 2010 carries a byte that is not UTF-8, and decoding strictly raised before
            # anything could be read - taking the whole stage down for that medium. The
            # unreadable byte is replaced; every field around it still arrives.
            text=True,
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        if allow_failure:
            return None
        raise DeriveError(str(error)) from error

    if result.returncode != 0:
        if allow_failure:
            return None
        raise DeriveError(result.stderr.strip()[:500])
    return result.stdout
