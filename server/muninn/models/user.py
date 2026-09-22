"""User accounts and roles."""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String, Text
from sqlalchemy.dialects.postgresql import CITEXT, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from muninn.models.base import Base, TimestampMixin
from muninn.models.enum import pg_enum

if TYPE_CHECKING:
    from muninn.models.refresh_token import RefreshToken


class UserRole(StrEnum):
    """Two roles, as laid down in the concept. Admins additionally manage users and indexing."""

    USER = "user"
    ADMIN = "admin"


class UserStatus(StrEnum):
    DISABLED = "disabled"
    ACTIVE = "active"


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    #: What people log in with. citext, so the case they type does not matter while the spelling
    #: they chose is kept.
    username: Mapped[str] = mapped_column(CITEXT, unique=True, nullable=False)
    #: Kept as an attribute for later use. Muninn sends no mail, so nobody needs one to take part.
    email: Mapped[str | None] = mapped_column(CITEXT, unique=True, default=None)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    #: Argon2id, never a plain password.
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[UserRole] = mapped_column(
        pg_enum(UserRole, "user_role"), default=UserRole.USER, nullable=False
    )
    status: Mapped[UserStatus] = mapped_column(
        pg_enum(UserStatus, "user_status"), default=UserStatus.ACTIVE, nullable=False
    )
    #: True while the user still has the starting password an admin handed out.
    must_change_password: Mapped[bool] = mapped_column(default=True, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    @property
    def is_active(self) -> bool:
        return self.status is UserStatus.ACTIVE
