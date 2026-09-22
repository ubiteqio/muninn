"""Authentication: checking passwords and handing out token pairs.

Only this module touches the database for authentication; the router does HTTP and nothing else.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from muninn.core.config import Settings
from muninn.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    password_needs_rehash,
    verify_password,
)
from muninn.models.refresh_token import RefreshToken
from muninn.models.user import User, UserStatus


class AuthenticationError(Exception):
    """Wrong credentials. Deliberately says no more than that."""


class AccountDisabledError(Exception):
    """The account exists but an admin has disabled it."""


class InvalidRefreshTokenError(Exception):
    """Unknown, expired or revoked refresh token."""


class RefreshTokenReplayError(Exception):
    """A token that was already exchanged turned up again; the whole family is now revoked."""


@dataclass(frozen=True, slots=True)
class TokenPair:
    access_token: str
    access_token_expires_at: datetime
    refresh_token: str
    refresh_token_expires_at: datetime


@dataclass(frozen=True, slots=True)
class LoginResult:
    user: User
    tokens: TokenPair


async def authenticate(session: AsyncSession, *, username: str, password: str) -> User:
    """Return the user for these credentials, or raise."""
    user = await session.scalar(select(User).where(User.username == username))

    if user is None:
        # Hash anyway, so that a missing account takes as long as a wrong password.
        hash_password(password)
        raise AuthenticationError

    if not verify_password(user.password_hash, password):
        raise AuthenticationError

    if user.status is not UserStatus.ACTIVE:
        raise AccountDisabledError

    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)

    user.last_login_at = datetime.now(UTC)
    return user


async def issue_tokens(
    session: AsyncSession,
    *,
    user: User,
    settings: Settings,
    user_agent: str | None = None,
    ip_address: str | None = None,
    family_id: uuid.UUID | None = None,
    parent_expires_at: datetime | None = None,
) -> TokenPair:
    """Create an access token and a refresh token.

    A rotated token keeps the family and the original expiry: rotating must not extend a session
    forever, otherwise a stolen token could be refreshed indefinitely.
    """
    access_token, access_expires_at = create_access_token(
        user_id=user.id,
        role=user.role,
        secret=settings.jwt_secret,
        ttl=timedelta(minutes=settings.access_token_ttl_minutes),
    )

    refresh_token = generate_refresh_token()
    expires_at = parent_expires_at or datetime.now(UTC) + timedelta(
        days=settings.refresh_token_ttl_days
    )

    session.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_refresh_token(refresh_token),
            family_id=family_id or uuid.uuid4(),
            expires_at=expires_at,
            user_agent=user_agent,
            ip_address=ip_address,
        )
    )

    return TokenPair(
        access_token=access_token,
        access_token_expires_at=access_expires_at,
        refresh_token=refresh_token,
        refresh_token_expires_at=expires_at,
    )


async def login(
    session: AsyncSession,
    *,
    username: str,
    password: str,
    settings: Settings,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> LoginResult:
    user = await authenticate(session, username=username, password=password)
    tokens = await issue_tokens(
        session,
        user=user,
        settings=settings,
        user_agent=user_agent,
        ip_address=ip_address,
    )
    await session.commit()
    return LoginResult(user=user, tokens=tokens)


async def rotate_refresh_token(
    session: AsyncSession,
    *,
    token: str,
    settings: Settings,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> LoginResult:
    """Exchange a refresh token for a fresh pair, detecting replays."""
    stored = await session.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(token))
    )
    if stored is None:
        raise InvalidRefreshTokenError

    now = datetime.now(UTC)

    if stored.used_at is not None:
        # Somebody is replaying an old token. Whoever it is, end every session of that family.
        await revoke_family(session, family_id=stored.family_id)
        await session.commit()
        raise RefreshTokenReplayError

    if stored.revoked_at is not None or stored.expires_at <= now:
        raise InvalidRefreshTokenError

    user = await session.get(User, stored.user_id)
    if user is None or user.status is not UserStatus.ACTIVE:
        raise InvalidRefreshTokenError

    stored.used_at = now
    tokens = await issue_tokens(
        session,
        user=user,
        settings=settings,
        user_agent=user_agent,
        ip_address=ip_address,
        family_id=stored.family_id,
        parent_expires_at=stored.expires_at,
    )
    await session.commit()
    return LoginResult(user=user, tokens=tokens)


async def revoke_family(session: AsyncSession, *, family_id: uuid.UUID) -> None:
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )


async def revoke_all_for_user(session: AsyncSession, *, user_id: uuid.UUID) -> None:
    """Used on logout of every device, on a password change and when an account is disabled."""
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )


async def logout(session: AsyncSession, *, token: str) -> None:
    """Revoke the family the token belongs to. An unknown token is not an error."""
    stored = await session.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(token))
    )
    if stored is not None:
        await revoke_family(session, family_id=stored.family_id)
    await session.commit()


async def change_password(
    session: AsyncSession,
    *,
    user: User,
    current_password: str,
    new_password: str,
    settings: Settings,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> TokenPair:
    """Set the user's own password and end every session but this one.

    Every other device is signed out, because the old password may have been seen or spoken aloud.
    This device stays: whoever is here just proved they know the current password, and throwing
    them out to type the new one again protects nobody. It gets a fresh token family, so the
    tokens handed out under the old password are dead too.
    """
    if not verify_password(user.password_hash, current_password):
        raise AuthenticationError

    user.password_hash = hash_password(new_password)
    user.must_change_password = False
    await revoke_all_for_user(session, user_id=user.id)

    tokens = await issue_tokens(
        session,
        user=user,
        settings=settings,
        user_agent=user_agent,
        ip_address=ip_address,
    )
    await session.commit()
    return tokens
