"""FastAPI dependencies: database session, Redis, the current user and role checks."""

from collections.abc import AsyncIterator
from typing import Annotated

import httpx
from fastapi import Depends, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.requests import HTTPConnection

from muninn.core.config import Settings
from muninn.core.problem import ProblemError, problem_type
from muninn.core.ratelimit import RateLimiter
from muninn.core.security import InvalidAccessTokenError, decode_access_token
from muninn.models.user import User, UserRole, UserStatus


# These three ask nothing of the request itself, only of the application behind it. Typed as
# the connection rather than the request, they serve the WebSocket route as well.
def get_settings_from_state(connection: HTTPConnection) -> Settings:
    settings: Settings = connection.app.state.settings
    return settings


async def get_session(connection: HTTPConnection) -> AsyncIterator[AsyncSession]:
    factory: async_sessionmaker[AsyncSession] = connection.app.state.session_factory
    async with factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


def get_redis(connection: HTTPConnection) -> Redis:
    redis: Redis = connection.app.state.redis
    return redis


def get_ai_client(connection: HTTPConnection) -> httpx.AsyncClient | None:
    """The process-wide client for the AI machine, so its connection is kept between calls.

    Nothing where the lifespan did not run - a test that builds the application by hand. The
    caller then opens a client of its own for the one call, which is what it did before there
    was a shared one.
    """
    client: httpx.AsyncClient | None = getattr(connection.app.state, "ai_client", None)
    return client


def get_login_rate_limiter(
    redis: Annotated[Redis, Depends(get_redis)],
    settings: Annotated[Settings, Depends(get_settings_from_state)],
) -> RateLimiter:
    return RateLimiter(
        redis,
        limit=settings.login_attempts_per_window,
        window_seconds=settings.login_attempt_window_seconds,
    )


def _bearer_token(request: Request) -> str:
    header = request.headers.get("Authorization")
    if header is None or not header.lower().startswith("bearer "):
        raise ProblemError(
            status=401,
            type=problem_type("not-authenticated"),
            title="Not authenticated",
            detail="This endpoint needs a bearer access token.",
        )
    return header[len("bearer ") :].strip()


async def get_current_user(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings_from_state)],
) -> User:
    """The user behind the access token. Raises 401 if the token or the account is not usable."""
    token = _bearer_token(request)

    try:
        claims = decode_access_token(token, secret=settings.jwt_secret)
    except InvalidAccessTokenError as error:
        raise ProblemError(
            status=401,
            type=problem_type("invalid-access-token"),
            title="Invalid access token",
            detail="The access token is expired or not valid. Refresh it and try again.",
        ) from error

    user = await session.get(User, claims.user_id)
    if user is None or user.status is not UserStatus.ACTIVE:
        raise ProblemError(
            status=401,
            type=problem_type("account-unavailable"),
            title="Account unavailable",
            detail="This account no longer exists or has been disabled.",
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_active_user(user: CurrentUser) -> User:
    """A user who has replaced the starting password an admin handed out.

    Everything except /auth and the own account is closed until then, so a password that was
    passed on verbally cannot stay in use.
    """
    if user.must_change_password:
        raise ProblemError(
            status=403,
            type=problem_type("password-change-required"),
            title="Password change required",
            detail="Set your own password with POST /api/v1/auth/password first.",
        )
    return user


ActiveUser = Annotated[User, Depends(get_active_user)]


async def get_admin_user(user: ActiveUser) -> User:
    if user.role is not UserRole.ADMIN:
        raise ProblemError(
            status=403,
            type=problem_type("admin-required"),
            title="Admin required",
            detail="Only admins may use this endpoint.",
        )
    return user


AdminUser = Annotated[User, Depends(get_admin_user)]


async def get_optional_user(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings_from_state)],
) -> User | None:
    """The user behind the access token, or None when there is none or it is not usable.

    Media are normally fetched with a signed address; the native app sends its token in the
    header instead. Both are allowed, so this may come back empty without that being an error.
    """
    try:
        return await get_current_user(request, session, settings)
    except ProblemError:
        return None


OptionalUser = Annotated[User | None, Depends(get_optional_user)]
