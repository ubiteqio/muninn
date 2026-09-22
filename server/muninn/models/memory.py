"""Memories: "Heute vor X Jahren", chosen once per day."""

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from muninn.models.base import Base


class Memory(Base):
    """The photos of one earlier year from the calendar day it is shown on."""

    __tablename__ = "memories"
    __table_args__ = (UniqueConstraint("day", "year", name="uq_memories_day_year"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    #: The day it is shown on.
    day: Mapped[date] = mapped_column(Date, nullable=False)
    #: The year the photos are from.
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    #: True when the day itself had nothing and the week around it was taken.
    from_week: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    #: The album most of its photos are from; its title is the memory's.
    album_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("albums.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class MemoryMedium(Base):
    __tablename__ = "memory_media"

    memory_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("memories.id", ondelete="CASCADE"), primary_key=True
    )
    media_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("media.id", ondelete="CASCADE"), primary_key=True
    )
    #: In the order they were taken: the slideshow runs through the day.
    position: Mapped[int] = mapped_column(Integer, nullable=False)
