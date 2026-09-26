"""The installation's own settings, as far as an admin may change them at runtime.

Everything that has to be in place before the process starts - database, Redis, the JWT secret,
the mount points - stays in the environment (see muninn.core.config). What an admin decides while
Muninn runs lives here: one row, changed in the admin area, read by the pipeline.
"""

from sqlalchemy import ARRAY, Boolean, CheckConstraint, Integer, SmallInteger, Text
from sqlalchemy.orm import Mapped, mapped_column

from muninn.models.base import Base, TimestampMixin

#: There is exactly one settings row, and this is its primary key.
SETTINGS_ID = 1

#: The concept's values (docs/konzept.md, "Indexierungs-Pipeline Huginn") as the starting point.
DEFAULT_THUMBNAIL_SIZE = 400
DEFAULT_PREVIEW_SIZE = 2048
DEFAULT_IMAGE_QUALITY = 82
DEFAULT_VIDEO_HEIGHT = 720

#: Folders and files of the NAS itself, never media. Hidden entries are skipped by the scanner
#: regardless of this list; these are the ones that are not hidden.
DEFAULT_IGNORED_NAMES = ["@eaDir", "#recycle", ".DS_Store", "Thumbs.db"]

#: How the library is kept in step with the NAS, as the concept's settings table lists it.
DEFAULT_QUICK_SYNC_SECONDS = 300
DEFAULT_FULL_SYNC_HOUR = 3
DEFAULT_STABILITY_SECONDS = 30
DEFAULT_MISSING_GRACE_DAYS = 30

#: The pause before many deletions at once. 0 is off, and off is the default: a file deleted on
#: the NAS disappears from the albums with the next read, without anybody confirming it.
DEFAULT_DELETION_SHARE_PERCENT = 0
DEFAULT_DELETION_COUNT = 0

#: How many media one smart album holds at most. A chapter is something to look through, not a
#: second library: beyond a few hundred nobody reaches the end, and the rest is found by the
#: chapters it also belongs to.
DEFAULT_SMART_MAX_MEDIA = 500


class AppSettings(TimestampMixin, Base):
    """Single-row table. Use muninn.settings.service to read it, never construct it elsewhere."""

    __tablename__ = "settings"
    __table_args__ = (CheckConstraint(f"id = {SETTINGS_ID}", name="single_row"),)

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=False)

    #: Longest edge of the grid thumbnail, in pixels.
    thumbnail_size: Mapped[int] = mapped_column(Integer, nullable=False)
    #: Longest edge of the full-screen preview, in pixels.
    preview_size: Mapped[int] = mapped_column(Integer, nullable=False)
    #: WebP quality of both, 50 to 100.
    image_quality: Mapped[int] = mapped_column(Integer, nullable=False)
    #: Height of the video preview, in pixels; the width follows the aspect ratio.
    video_height: Mapped[int] = mapped_column(Integer, nullable=False)

    #: Folder and file names the scanner skips.
    ignored_names: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)

    #: How often the quick sync compares folder signatures.
    quick_sync_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    #: Hour of the night at which every file is read again.
    full_sync_hour: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    #: How far two listings have to lie apart before a file counts as fully copied.
    stability_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    #: How long a missing medium is kept before it is removed for good; 0 removes it at once.
    missing_grace_days: Mapped[int] = mapped_column(Integer, nullable=False)

    #: A sync pauses when it would mark away this share of its scope, or this many files.
    deletion_share_percent: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    deletion_count: Mapped[int] = mapped_column(Integer, nullable=False)

    #: Whether the optional agent on the NAS may report folders.
    nas_agent_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)

    #: Whether faces are looked for and shown. Off, nothing new is found and nobody is named;
    #: what was found stays until an admin deletes it.
    faces_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    #: How many media one smart album holds at most.
    smart_max_media: Mapped[int] = mapped_column(
        Integer, nullable=False, default=DEFAULT_SMART_MAX_MEDIA
    )
