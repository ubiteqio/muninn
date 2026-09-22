"""What the describing model saw in a medium (stage 5), and what is said in a video."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, SmallInteger, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column

from muninn.models.base import Base


class MediaAnalysis(Base):
    """One answer per medium, from the model and stage version that gave it."""

    __tablename__ = "media_analyses"

    media_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("media.id", ondelete="CASCADE"), primary_key=True
    )
    model: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(SmallInteger, nullable=False)

    #: One or two German sentences about what can be seen.
    caption: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    scene: Mapped[str] = mapped_column(Text, nullable=False, default="")
    #: Text that can be read in the picture, as it is written there.
    ocr_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    people_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    time_of_day: Mapped[str] = mapped_column(Text, nullable=False, default="")
    is_screenshot: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_document: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    quality: Mapped[str] = mapped_column(Text, nullable=False, default="")

    #: German full text over caption, tags and the text in the picture, weighted in that order.
    search_tsv: Mapped[str] = mapped_column(TSVECTOR, nullable=False)
    analyzed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class VideoFrame(Base):
    """What was seen at one second of a video. Only the seconds in which something changed."""

    __tablename__ = "video_frames"

    media_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("media.id", ondelete="CASCADE"), primary_key=True
    )
    second: Mapped[int] = mapped_column(Integer, primary_key=True)
    caption: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    ocr_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    people_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    search_tsv: Mapped[str] = mapped_column(TSVECTOR, nullable=False)


class MediaTranscript(Base):
    """What is said in a video, with the time of each part. Empty text for a silent video."""

    __tablename__ = "media_transcripts"

    media_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("media.id", ondelete="CASCADE"), primary_key=True
    )
    model: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    #: Whisper's code for the language, e.g. "de"; empty when nothing was said.
    language: Mapped[str] = mapped_column(Text, nullable=False, default="")
    text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    #: [{"start": 1.5, "end": 3.0, "text": "..."}], in order.
    segments: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    search_tsv: Mapped[str] = mapped_column(TSVECTOR, nullable=False)
    transcribed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
