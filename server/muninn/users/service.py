"""Accounts: creating, listing and changing users. Only admins reach most of this."""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from muninn.auth.service import revoke_all_for_user
from muninn.core.security import generate_password, hash_password
from muninn.models.user import User, UserRole, UserStatus

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200


class NameAlreadyUsedError(Exception):
    """Another account already uses this username or e-mail address."""


class UserNotFoundError(Exception):
    pass


class LastAdminError(Exception):
    """Refused: the change would leave the installation without a usable admin."""


@dataclass(frozen=True, slots=True)
class CreatedUser:
    user: User
    #: Handed to the admin once, to pass on verbally. Muninn never mails it.
    starting_password: str


async def create_user(
    session: AsyncSession,
    *,
    username: str,
    display_name: str,
    email: str | None = None,
    role: UserRole = UserRole.USER,
) -> CreatedUser:
    """Create an account with a generated starting password the user must replace."""
    starting_password = generate_password()
    user = User(
        username=username,
        email=email,
        display_name=display_name,
        password_hash=hash_password(starting_password),
        role=role,
        status=UserStatus.ACTIVE,
        must_change_password=True,
    )
    session.add(user)
    try:
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise NameAlreadyUsedError from error

    await session.refresh(user)
    return CreatedUser(user=user, starting_password=starting_password)


async def get_user(session: AsyncSession, user_id: uuid.UUID) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise UserNotFoundError
    return user


async def list_users(
    session: AsyncSession,
    *,
    limit: int = DEFAULT_PAGE_SIZE,
    cursor: tuple[datetime, uuid.UUID] | None = None,
) -> tuple[list[User], bool]:
    """Newest accounts first. Returns the page and whether more rows follow."""
    limit = min(max(limit, 1), MAX_PAGE_SIZE)
    query = select(User).order_by(User.created_at.desc(), User.id.desc()).limit(limit + 1)

    if cursor is not None:
        created_at, user_id = cursor
        query = query.where(
            (User.created_at < created_at) | ((User.created_at == created_at) & (User.id < user_id))
        )

    rows = list(await session.scalars(query))
    has_more = len(rows) > limit
    return rows[:limit], has_more


async def update_user(
    session: AsyncSession,
    *,
    user: User,
    display_name: str | None = None,
    username: str | None = None,
    email: str | None = None,
    clear_email: bool = False,
    role: UserRole | None = None,
    status: UserStatus | None = None,
) -> User:
    """Change a user. Disabling or demoting the last admin is refused, and so is a username or
    e-mail address another account already uses."""
    loses_admin = (role is not None and role is not UserRole.ADMIN) or (
        status is not None and status is not UserStatus.ACTIVE
    )
    if (
        user.role is UserRole.ADMIN
        and loses_admin
        and await _count_other_admins(session, user) == 0
    ):
        raise LastAdminError

    if display_name is not None:
        user.display_name = display_name
    if username is not None:
        user.username = username
    if email is not None:
        user.email = email
    elif clear_email:
        user.email = None
    if role is not None:
        user.role = role
    if status is not None:
        user.status = status
        if status is not UserStatus.ACTIVE:
            await revoke_all_for_user(session, user_id=user.id)

    try:
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise NameAlreadyUsedError from error
    await session.refresh(user)
    return user


class SelfDeletionError(Exception):
    """An admin does not delete their own account from inside it."""


async def delete_user(session: AsyncSession, *, user: User, admin: User) -> None:
    """Remove an account for good, and with it everything that is only theirs: likes,
    favourites, comments and notifications. The last admin stays."""
    if user.id == admin.id:
        raise SelfDeletionError
    if user.role is UserRole.ADMIN and await _count_other_admins(session, user) == 0:
        raise LastAdminError
    await session.delete(user)
    await session.commit()


async def reset_password(session: AsyncSession, *, user: User) -> str:
    """Give the user a new starting password and end all their sessions."""
    starting_password = generate_password()
    user.password_hash = hash_password(starting_password)
    user.must_change_password = True
    await revoke_all_for_user(session, user_id=user.id)
    await session.commit()
    return starting_password


async def update_own_profile(session: AsyncSession, *, user: User, display_name: str) -> User:
    user.display_name = display_name
    await session.commit()
    await session.refresh(user)
    return user


async def _count_other_admins(session: AsyncSession, user: User) -> int:
    query = (
        select(User.id)
        .where(
            User.role == UserRole.ADMIN,
            User.status == UserStatus.ACTIVE,
            User.id != user.id,
        )
        .limit(1)
    )
    return len(list(await session.scalars(query)))
