"""How Muninn reaches the machines that describe pictures and turn them into vectors.

No model name and no address belongs in the code: what the installation uses is decided in the
admin area and can be swapped for something else without a release. One profile per interface is
active at a time; the others stay as spares.
"""

import uuid
from enum import StrEnum

from sqlalchemy import Boolean, Integer, SmallInteger, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from muninn.models.base import Base, TimestampMixin
from muninn.models.enum import pg_enum


class AiKind(StrEnum):
    """What a profile is for. Each one answers a different question about a medium."""

    #: Describes a picture: caption, tags, scene, text in the image.
    ANALYZER = "analyzer"
    #: Turns a picture into a vector, so that a sentence can find it.
    IMAGE_EMBEDDER = "image_embedder"
    #: Turns a description into a vector, so that meaning can be searched for.
    TEXT_EMBEDDER = "text_embedder"
    #: Writes down what is said in a video, with the time of each part.
    TRANSCRIBER = "transcriber"
    #: Finds the faces in a picture, and a vector for each.
    FACE_DETECTOR = "face_detector"


#: Sensible for a single GPU shared by everything: enough to keep it busy, not enough to thrash.
DEFAULT_CONCURRENCY = 2
DEFAULT_TIMEOUT_SECONDS = 120


class AiProfile(TimestampMixin, Base):
    """One machine Muninn can ask, reached over an OpenAI-compatible API."""

    __tablename__ = "ai_profiles"
    __table_args__ = (
        # One active profile per interface. The others are spares and can stay as they are.
        UniqueConstraint("kind", "is_active", name="uq_ai_profiles_one_active"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    kind: Mapped[AiKind] = mapped_column(pg_enum(AiKind, "ai_kind"), nullable=False)
    #: What an admin calls it, e.g. "GPU im Keller" or "Ersatz".
    name: Mapped[str] = mapped_column(Text, nullable=False)

    #: Where the OpenAI-compatible API lives, up to and including /v1.
    base_url: Mapped[str] = mapped_column(Text, nullable=False)
    #: Sent as a bearer token. Many local servers want none; then this stays empty.
    api_key: Mapped[str] = mapped_column(Text, nullable=False, default="")
    #: The model as that server names it, e.g. "Qwen3-VL-8B-Instruct".
    model: Mapped[str] = mapped_column(Text, nullable=False)

    #: How many requests Muninn has in flight at once. The AI queue is limited to this.
    concurrency: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    #: How long one request may take before it counts as failed.
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False)

    #: Whether this is the profile in use for its interface. Null means "spare": the unique
    #: constraint only bites on true, because NULLs never equal each other.
    is_active: Mapped[bool | None] = mapped_column(Boolean)
