"""Refresh tokens.

A refresh token is an opaque random value; only its hash is stored. Every use issues a successor
and marks the predecessor as used. All successors of one login share a ``family_id``: if a token
that was already used turns up again, the whole family is revoked, because either the client or a
thief is replaying an old token.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import INET, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from muninn.models.base import Base

if TYPE_CHECKING:
    from muninn.models.user import User


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    __table_args__ = (
        Index("ix_refresh_tokens_user_id_expires_at", "user_id", "expires_at"),
        Index("ix_refresh_tokens_family_id", "family_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    #: SHA-256 of the token; the token itself is only ever seen by the client.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    #: All tokens descending from one login.
    family_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: Set when this token was exchanged for a successor.
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    #: Set on logout, on a password change, or when the family was revoked after a replay.
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    #: Kept so a user can recognise their own sessions later.
    user_agent: Mapped[str | None] = mapped_column(String(400), default=None)
    ip_address: Mapped[str | None] = mapped_column(INET, default=None)

    user: Mapped["User"] = relationship(back_populates="refresh_tokens")
