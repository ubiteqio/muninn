"""Groups of media that are the same picture, found again by a job every quarter of an hour."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from muninn.models.base import Base


class DuplicateGroup(Base):
    """Media that are one picture: the same file, a smaller copy, or shots of one burst.

    The job replaces all groups each time, so an id only holds until the next run; what an admin
    decides is stored on the media (Media.duplicate_of), never on the group.
    """

    __tablename__ = "duplicate_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    #: "exact", "near" or "burst": the loosest tie inside the group.
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    #: When its newest member was taken, to list the groups newest first.
    newest: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DuplicateMember(Base):
    __tablename__ = "duplicate_members"

    group_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("duplicate_groups.id", ondelete="CASCADE"), primary_key=True
    )
    media_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("media.id", ondelete="CASCADE"), primary_key=True
    )
    #: The one to keep: largest, most complete metadata, original format.
    best: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    #: Best first.
    position: Mapped[int] = mapped_column(Integer, nullable=False)
