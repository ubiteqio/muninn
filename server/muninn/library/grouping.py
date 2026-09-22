"""RAW plus JPEG, and Live Photos, belong to one medium.

The concept groups files of the same name: a RAW next to its JPEG, and the short clip iPhones
write next to a HEIC. Everything else stands on its own.
"""

from collections.abc import Iterable
from dataclasses import dataclass

from muninn.library.formats import (
    LIVE_PHOTO_IMAGE_EXTENSIONS,
    LIVE_PHOTO_VIDEO_EXTENSION,
    FileKind,
    extension_of,
    image_rank,
    kind_of,
    stem_of,
)
from muninn.library.scanner import ScannedFile
from muninn.models.media import MediaFileRole, MediaKind


@dataclass(frozen=True, slots=True)
class MediaGroup:
    """The files of one medium, with the role each of them plays."""

    kind: MediaKind
    primary: ScannedFile
    others: tuple[tuple[MediaFileRole, ScannedFile], ...] = ()

    @property
    def files(self) -> tuple[tuple[MediaFileRole, ScannedFile], ...]:
        return ((MediaFileRole.PRIMARY, self.primary), *self.others)


def group_files(files: Iterable[ScannedFile]) -> list[MediaGroup]:
    """Turn the files of one folder into media, in a stable order."""
    by_stem: dict[str, list[ScannedFile]] = {}
    for file in files:
        by_stem.setdefault(stem_of(file.name), []).append(file)

    groups: list[MediaGroup] = []
    for stem in sorted(by_stem):
        groups.extend(_group_one_name(by_stem[stem]))
    return groups


def _group_one_name(files: list[ScannedFile]) -> list[MediaGroup]:
    images = sorted(
        (file for file in files if kind_of(file.name) is FileKind.IMAGE),
        key=lambda file: (image_rank(file.name), file.name),
    )
    raws = sorted((file for file in files if kind_of(file.name) is FileKind.RAW), key=_by_name)
    videos = sorted((file for file in files if kind_of(file.name) is FileKind.VIDEO), key=_by_name)

    if not images and not raws:
        # Videos of the same name without a picture: each one is its own medium.
        return [MediaGroup(kind=MediaKind.VIDEO, primary=video) for video in videos]

    primary = images[0] if images else raws[0]
    others: list[tuple[MediaFileRole, ScannedFile]] = []

    for raw in raws:
        if raw is not primary:
            others.append((MediaFileRole.RAW, raw))

    # A Live Photo, and only that: a HEIC with a .mov of the same name. Any other video keeps its
    # own medium, because a picture and a film of the same name are usually two things.
    motion = next(
        (
            video
            for video in videos
            if extension_of(video.name) == LIVE_PHOTO_VIDEO_EXTENSION
            and extension_of(primary.name) in LIVE_PHOTO_IMAGE_EXTENSIONS
        ),
        None,
    )
    if motion is not None:
        others.append((MediaFileRole.MOTION, motion))

    groups = [MediaGroup(kind=MediaKind.IMAGE, primary=primary, others=tuple(others))]
    groups.extend(
        MediaGroup(kind=MediaKind.VIDEO, primary=video) for video in videos if video is not motion
    )
    # A second image of the same name (JPEG next to PNG) is a medium of its own.
    groups.extend(MediaGroup(kind=MediaKind.IMAGE, primary=image) for image in images[1:])
    return groups


def _by_name(file: ScannedFile) -> str:
    return file.name
