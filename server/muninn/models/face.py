"""Faces and the persons they belong to. Biometric data: it never leaves the server."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from muninn.models.base import Base


class Person(Base):
    """Somebody with a name. Only ever made by a user naming a group of faces."""

    __tablename__ = "persons"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    #: Strangers in the background: kept, so their faces are not asked about again.
    hidden: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Face(Base):
    """One face in a medium.

    Its vector (embedding, model, dimensions) is only read and written by muninn.search, so it is
    left out here.
    """

    __tablename__ = "faces"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    media_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("media.id", ondelete="CASCADE"), nullable=False
    )
    #: Where it is, as fractions of the picture's width and height.
    box_left: Mapped[float] = mapped_column(Float, nullable=False)
    box_top: Mapped[float] = mapped_column(Float, nullable=False)
    box_right: Mapped[float] = mapped_column(Float, nullable=False)
    box_bottom: Mapped[float] = mapped_column(Float, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    #: Its smaller side in pixels of the picture that was looked at.
    pixels: Mapped[int] = mapped_column(Integer, nullable=False)
    #: For a video, the second it was seen at.
    second: Mapped[float | None] = mapped_column(Float)
    #: The picture's width divided by its height, to cut a square around the face.
    aspect: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    person_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("persons.id", ondelete="SET NULL")
    )
    #: "user" when somebody said who it is, "auto" when it lay that close to them.
    assigned_by: Mapped[str | None] = mapped_column(String(8))
    suggested_person_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("persons.id", ondelete="SET NULL")
    )
    #: How far it lay from the suggested person's nearest face (cosine distance), for the app to
    #: say how alike they are.
    suggested_distance: Mapped[float | None] = mapped_column(Float)
    #: The group the job put it in while it has no person.
    cluster: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class FaceRejection(Base):
    """Somebody said: this face is not that person. It is not suggested again."""

    __tablename__ = "face_rejections"

    face_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("faces.id", ondelete="CASCADE"), primary_key=True
    )
    person_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("persons.id", ondelete="CASCADE"), primary_key=True
    )
