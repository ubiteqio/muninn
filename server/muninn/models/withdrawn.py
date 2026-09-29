"""Media an admin has taken down, so that the reading does not bring them back."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from muninn.models.base import Base


class WithdrawnMedium(Base):
    """One medium that was taken down, remembered by what it is rather than where it lies.

    Taking a medium down deletes it and everything that hung on it. The file itself stays on
    the NAS - originals are never written to - so the next reading would find it, index it
    again and show it again within the minute. This is what stops that.

    Held by content hash, which is what identifies a medium here: renamed, moved into another
    folder or copied beside itself, it is the same picture and stays down. The path is kept as
    well, so the reading can turn it away before it has hashed anything, and so an admin can
    see what was taken down.
    """

    __tablename__ = "withdrawn_media"

    content_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    #: Where it lay when it was taken down. For the eye, and to turn it away cheaply.
    relative_path: Mapped[str] = mapped_column(Text, nullable=False)
    withdrawn_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    #: Who took it down. Kept even when the account goes.
    withdrawn_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
