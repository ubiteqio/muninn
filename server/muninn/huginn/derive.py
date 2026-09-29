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
import tempfile
import threading
import time
from collections.abc import Callable, Iterable, Iterator
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


#: How often a conversion says how far it has got. More often only costs Redis writes.
PROGRESS_EVERY_SECONDS = 2.0


@dataclass(frozen=True, slots=True)
class Progress:
    """How far a video conversion has got, as ffmpeg reports it."""

    #: How much of the video is converted, in seconds of the video.
    done_seconds: float
    #: How long the video is, from its metadata; None when nobody could read it.
    total_seconds: float | None
    #: How many seconds of video ffmpeg converts per second - "1.8x" is 1.8.
    speed: float | None


ProgressCallback = Callable[[Progress], None]


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
    duration_seconds: float | None = None,
    on_progress: ProgressCallback | None = None,
) -> Derivatives:
    """Make every derivative of one medium. Runs in a worker, never in the API.

    A video's conversion can take many minutes; `on_progress` hears how far it is every few
    seconds, measured against `duration_seconds`.

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
                duration_seconds=duration_seconds,
                on_progress=on_progress,
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
    duration_seconds: float | None = None,
    on_progress: ProgressCallback | None = None,
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
    _transcode(
        [
            "ffmpeg",
            "-y",
            # Where it is, as key=value lines on stdout, instead of the one line it rewrites on
            # a terminal nobody is looking at.
            "-progress",
            "pipe:1",
            "-nostats",
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
        total_seconds=duration_seconds,
        on_progress=on_progress,
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


def _transcode(
    command: list[str],
    *,
    timeout: int,
    total_seconds: float | None,
    on_progress: ProgressCallback | None,
) -> None:
    """Run ffmpeg and pass on how far it is while it runs.

    It reports on stdout; what it has to complain about goes to a file, because a pipe nobody
    reads fills up and stops ffmpeg dead. The timeout is a watchdog that kills it, since a
    process that is read line by line cannot be given one the way `subprocess.run` does.
    """
    executable = shutil.which(command[0])
    if executable is None:
        raise DeriveError(f"{command[0]} is not installed")

    killed = threading.Event()
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="replace") as complaints:
        try:
            process = subprocess.Popen(  # noqa: S603 - fixed command, the only variable is a path
                [executable, *command[1:]],
                stdout=subprocess.PIPE,
                stderr=complaints,
                text=True,
                errors="replace",
            )
        except OSError as error:
            raise DeriveError(str(error)) from error

        def kill() -> None:
            killed.set()
            process.kill()

        watchdog = threading.Timer(timeout, kill)
        watchdog.start()
        try:
            said = float("-inf")
            for progress in progress_of(process.stdout or (), total_seconds):
                now = time.monotonic()
                if on_progress is not None and now - said >= PROGRESS_EVERY_SECONDS:
                    said = now
                    _tell(on_progress, progress)
            returncode = process.wait()
        finally:
            watchdog.cancel()
            if process.poll() is None:
                process.kill()
                process.wait()

        if killed.is_set():
            raise DeriveError(f"{command[0]} took longer than {timeout} seconds")
        if returncode != 0:
            complaints.seek(0)
            # The end of what it said: that is where ffmpeg names what went wrong.
            raise DeriveError(complaints.read().strip()[-500:])


def progress_of(lines: Iterable[str], total_seconds: float | None) -> Iterator[Progress]:
    """Read ffmpeg's `-progress` output: blocks of key=value lines, each ending in `progress=`."""
    block: dict[str, str] = {}
    for line in lines:
        key, _, value = line.strip().partition("=")
        if not key:
            continue
        block[key] = value
        if key == "progress":
            yield Progress(
                done_seconds=_microseconds(block.get("out_time_us")),
                total_seconds=total_seconds if total_seconds and total_seconds > 0 else None,
                speed=_speed(block.get("speed")),
            )
            block = {}


def _microseconds(value: str | None) -> float:
    """Before the first frame ffmpeg says N/A, and early on it can even go below nought."""
    try:
        return max(0.0, int(value or "") / 1_000_000)
    except ValueError:
        return 0.0


def _speed(value: str | None) -> float | None:
    try:
        speed = float((value or "").strip().removesuffix("x"))
    except ValueError:
        return None
    return speed if speed > 0 else None


def _tell(on_progress: ProgressCallback, progress: Progress) -> None:
    """Saying how far it is must never be what stops a conversion."""
    try:
        on_progress(progress)
    except Exception:
        logging.getLogger(__name__).debug("Could not pass the progress on", exc_info=True)


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
