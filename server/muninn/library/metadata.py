"""Stage 2 of the pipeline: what a file says about itself.

exiftool reads the tags, ffprobe fills in what videos keep in their streams. Both are called
through a small boundary so the part that matters - turning tags into a medium's fields - stays
pure and testable without either program installed.
"""

import json
import shutil
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from muninn.library.dates import date_from_folder, date_from_name
from muninn.models.media import DateSource, MediaKind

#: Raise this when the reader learns to fill in more; media below it are read again.
METADATA_VERSION = 1

#: A single file should never hold up a queue for minutes.
TOOL_TIMEOUT_SECONDS = 60

_EXIF_DATE_TAGS = ("SubSecDateTimeOriginal", "DateTimeOriginal", "CreateDate", "MediaCreateDate")

#: Orientations that turn the picture by a quarter: width and height then mean the other way
#: round than the tag says, and everything that shows the picture needs the turned values.
_QUARTER_TURNS = frozenset({5, 6, 7, 8})


@dataclass(frozen=True, slots=True)
class MediaMetadata:
    """What stage 2 knows about a medium."""

    taken_at: datetime | None = None
    taken_at_source: DateSource | None = None
    width: int | None = None
    height: int | None = None
    duration_seconds: float | None = None
    camera_make: str | None = None
    camera_model: str | None = None
    lens: str | None = None
    latitude: float | None = None
    longitude: float | None = None


def read_metadata(
    path: Path,
    *,
    kind: MediaKind,
    relative_path: str,
    modified_at: datetime,
) -> MediaMetadata:
    """Read one file. Missing tools are not an error: the name and the folder still say a lot."""
    tags = dict(read_exiftool(path))
    if kind is MediaKind.VIDEO:
        for key, value in read_ffprobe(path).items():
            tags.setdefault(key, value)

    return from_tags(tags, filename=path.name, relative_path=relative_path, modified_at=modified_at)


def from_tags(
    tags: Mapping[str, Any],
    *,
    filename: str,
    relative_path: str,
    modified_at: datetime,
) -> MediaMetadata:
    """Turn tags into a medium's fields, with the date from the first source that has one."""
    taken_at, source = _capture_date(tags, filename, relative_path, modified_at)
    width, height = _picture_size(tags)

    return MediaMetadata(
        taken_at=taken_at,
        taken_at_source=source,
        width=width,
        height=height,
        duration_seconds=_as_float(tags.get("Duration") or tags.get("MediaDuration")),
        camera_make=_as_text(tags.get("Make")),
        camera_model=_as_text(tags.get("Model")),
        lens=_as_text(tags.get("LensModel") or tags.get("LensID") or tags.get("Lens")),
        latitude=_as_coordinate(tags.get("GPSLatitude"), -90, 90),
        longitude=_as_coordinate(tags.get("GPSLongitude"), -180, 180),
    )


def _picture_size(tags: Mapping[str, Any]) -> tuple[int | None, int | None]:
    """How large the picture is once it is the right way up."""
    width = _as_int(tags.get("ImageWidth"))
    height = _as_int(tags.get("ImageHeight"))

    if (
        width is not None
        and height is not None
        and _as_int(tags.get("Orientation")) in _QUARTER_TURNS
    ):
        return height, width
    return width, height


def _capture_date(
    tags: Mapping[str, Any], filename: str, relative_path: str, modified_at: datetime
) -> tuple[datetime | None, DateSource | None]:
    """The five sources of the concept, in order, and which one it was."""
    for tag in _EXIF_DATE_TAGS:
        parsed = _parse_exif_date(tags.get(tag))
        if parsed is not None:
            return parsed, DateSource.EXIF

    gps = _parse_exif_date(tags.get("GPSDateTime"))
    if gps is not None:
        return gps, DateSource.GPS

    from_filename = date_from_name(filename)
    if from_filename is not None:
        return from_filename, DateSource.FILENAME

    folder = relative_path.rsplit("/", 1)[0] if "/" in relative_path else ""
    from_folder = date_from_folder(folder)
    if from_folder is not None:
        return from_folder, DateSource.FOLDER_NAME

    return modified_at, DateSource.FILE_MTIME


def _parse_exif_date(value: Any) -> datetime | None:
    """EXIF writes "2012:08:14 15:30:12", sometimes with fractions and an offset.

    Without an offset the time is read as UTC. Deriving the real zone from the coordinates is a
    refinement for the map milestone, where the geo data arrives anyway.
    """
    if not isinstance(value, str):
        return None

    text = value.strip()
    if not text or text.startswith(("0000", "    ")):
        return None

    date_part, _, time_part = text.partition(" ")
    normalised = f"{date_part.replace(':', '-')} {time_part}".strip()
    if normalised.endswith("Z"):
        normalised = f"{normalised[:-1]}+00:00"

    try:
        parsed = datetime.fromisoformat(normalised)
    except ValueError:
        return None

    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def read_exiftool(path: Path) -> Mapping[str, Any]:
    """Every tag of one file, or nothing if exiftool is not installed or gives up."""
    output = _run(["exiftool", "-json", "-n", "-charset", "utf8", str(path)])
    if output is None:
        return {}

    try:
        parsed = json.loads(output)
    except json.JSONDecodeError:
        return {}

    if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
        tags: dict[str, Any] = parsed[0]
        return tags
    return {}


def read_ffprobe(path: Path) -> Mapping[str, Any]:
    """Duration and picture size of a video, named like the exiftool tags."""
    output = _run(
        [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
        ]
    )
    if output is None:
        return {}

    try:
        parsed = json.loads(output)
    except json.JSONDecodeError:
        return {}

    tags: dict[str, Any] = {}
    duration = parsed.get("format", {}).get("duration")
    if duration is not None:
        tags["Duration"] = duration

    for stream in parsed.get("streams", []):
        if stream.get("codec_type") == "video":
            tags["ImageWidth"] = stream.get("width")
            tags["ImageHeight"] = stream.get("height")
            break

    return tags


def _run(command: list[str]) -> str | None:
    """Run a reader, or answer None when it is missing, slow or unhappy."""
    executable = shutil.which(command[0])
    if executable is None:
        return None

    try:
        result = subprocess.run(  # noqa: S603 - fixed command, the only variable is a path
            [executable, *command[1:]],
            capture_output=True,
            text=True,
            timeout=TOOL_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    return result.stdout if result.returncode == 0 else None


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text[:160] or None


def _as_coordinate(value: Any, low: float, high: float) -> float | None:
    number = _as_float(value)
    if number is None or not low <= number <= high:
        return None
    # Exactly zero in both fields is what cameras write when they have no fix.
    return number or None
