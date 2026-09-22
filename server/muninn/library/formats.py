"""Which files Muninn takes, and which of them belongs to whom.

The lists are the ones from the concept. Everything else in a folder is not a medium and is
passed over without comment.
"""

from enum import StrEnum, auto

IMAGE_EXTENSIONS = frozenset(
    {".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp", ".tif", ".tiff", ".gif"}
)
RAW_EXTENSIONS = frozenset({".cr2", ".cr3", ".nef", ".arw", ".dng", ".orf", ".rw2"})
VIDEO_EXTENSIONS = frozenset(
    {".mp4", ".mov", ".avi", ".mts", ".m2ts", ".3gp", ".mpg", ".mpeg", ".wmv", ".mkv"}
)

#: A Live Photo is one of these next to a .mov of the same name.
LIVE_PHOTO_IMAGE_EXTENSIONS = frozenset({".heic", ".heif"})
LIVE_PHOTO_VIDEO_EXTENSION = ".mov"

#: When several images share a name, this is the order in which Muninn picks the one to show.
IMAGE_PREFERENCE = (".jpg", ".jpeg", ".heic", ".heif", ".png", ".webp", ".tif", ".tiff", ".gif")


class FileKind(StrEnum):
    IMAGE = auto()
    RAW = auto()
    VIDEO = auto()


def extension_of(filename: str) -> str:
    """The lower-case extension including the dot, or "" for a name without one."""
    _, dot, suffix = filename.rpartition(".")
    return f".{suffix.lower()}" if dot else ""


def kind_of(filename: str) -> FileKind | None:
    """What kind of medium this file is, or None if it is not one at all."""
    extension = extension_of(filename)
    if extension in IMAGE_EXTENSIONS:
        return FileKind.IMAGE
    if extension in RAW_EXTENSIONS:
        return FileKind.RAW
    if extension in VIDEO_EXTENSIONS:
        return FileKind.VIDEO
    return None


def stem_of(filename: str) -> str:
    """The name without its extension, folded, because NAS shares differ on case."""
    extension = extension_of(filename)
    stem = filename[: -len(extension)] if extension else filename
    return stem.casefold()


def image_rank(filename: str) -> int:
    """Lower is better. Anything unlisted sorts last."""
    extension = extension_of(filename)
    return (
        IMAGE_PREFERENCE.index(extension)
        if extension in IMAGE_PREFERENCE
        else len(IMAGE_PREFERENCE)
    )
