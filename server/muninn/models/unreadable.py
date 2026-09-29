"""Files the reading could not open, so that somebody can be told which."""

from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from muninn.models.base import Base


class UnreadableFile(Base):
    """One file the scanner had to walk past, and what the operating system said about it.

    Not an error of the medium - there may be no medium at all - and not a deletion: the file
    is there, it simply cannot be opened. A permission that arrived with a copy is the usual
    reason, and until it was written down the only trace of it was a worker's traceback.

    Held per path and replaced on every reading of the folder it lies in, so a permission put
    right disappears from the engine room by itself.
    """

    __tablename__ = "unreadable_files"

    relative_path: Mapped[str] = mapped_column(String(1024), primary_key=True)
    #: What the operating system said, kept short enough to read in a line.
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    last_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
