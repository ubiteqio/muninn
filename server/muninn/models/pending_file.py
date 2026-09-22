"""Files that are still being written.

A file counts as ready when two listings, at least the stability window apart, show the same size
and the same modification time. Compared are two observations of the NAS with each other, never a
NAS time against the server clock - the two machines' clocks need not agree.

New files are the common case here (somebody copies a folder onto the share), and they have no
medium yet, so the first observation is kept in a table of its own rather than on the medium.
"""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from muninn.models.base import Base


class PendingFile(Base):
    """The first of the two observations, waiting to be confirmed by the next sync."""

    __tablename__ = "pending_files"
    __table_args__ = (UniqueConstraint("relative_path", name="uq_pending_files_relative_path"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    #: Path below the mounted library.
    relative_path: Mapped[str] = mapped_column(Text, nullable=False)

    #: What the NAS reported the first time.
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    modified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: When Muninn saw it - its own clock, used only to measure the distance between two listings.
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
