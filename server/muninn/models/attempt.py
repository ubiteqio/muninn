"""What a stage tried and could not do.

A medium the pipeline cannot handle - a video no decoder here understands, a file that was
damaged on its way onto the NAS - used to come back every minute: the stage gave up, wrote
nothing down, and the clock handed the same medium out again because it still counted as
outstanding. The queue then chewed the same few files forever.

An attempt that failed for the medium's own sake is counted here. After a few of them the clock
leaves that medium alone until somebody asks for it again. A machine that is away is not the
medium's fault and is not counted: that case rests on its own and comes back by itself.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, SmallInteger, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from muninn.models.base import Base

#: How often a stage tries a medium before it leaves it alone.
GIVE_UP_AFTER = 3


class MediaAttempt(Base):
    """One stage's failed attempts at one medium."""

    __tablename__ = "media_attempts"

    media_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("media.id", ondelete="CASCADE"), primary_key=True
    )
    #: The stage that could not do it: "derive", "faces", "analysis" and the others.
    stage: Mapped[str] = mapped_column(String(24), primary_key=True)

    attempts: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    #: What went wrong the last time, for the admin to read.
    last_error: Mapped[str | None] = mapped_column(Text)
    last_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
