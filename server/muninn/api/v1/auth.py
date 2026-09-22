"""Logging in, refreshing, logging out and changing the own password."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from muninn.api.schemas.auth import (
    LoginRequest,
    PasswordChangeRequest,
    RefreshRequest,
    TokenResponse,
)
from muninn.api.schemas.users import UserProfile
from muninn.auth import service
from muninn.core.config import Settings
from muninn.core.deps import (
    CurrentUser,
    get_login_rate_limiter,
    get_session,
    get_settings_from_state,
)
from muninn.core.problem import ProblemError, problem_type
from muninn.core.ratelimit import RateLimiter

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE_NAME = "muninn_refresh"
REFRESH_COOKIE_PATH = "/api/v1/auth"
LOGIN_SCOPE = "login"


def _client_address(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _set_refresh_cookie(
    response: Response, *, token: str, settings: Settings, max_age_seconds: int
) -> None:
    response.set_cookie(
        REFRESH_COOKIE_NAME,
        token,
        max_age=max_age_seconds,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=settings.refresh_cookie_secure,
        samesite="lax",
    )


def _token_response(
    result: service.LoginResult, *, response: Response, settings: Settings, is_web: bool
) -> TokenResponse:
    tokens = result.tokens
    if is_web:
        remaining = tokens.refresh_token_expires_at - datetime.now(UTC)
        _set_refresh_cookie(
            response,
            token=tokens.refresh_token,
            settings=settings,
            max_age_seconds=max(int(remaining.total_seconds()), 0),
        )

    return TokenResponse(
        access_token=tokens.access_token,
        expires_at=tokens.access_token_expires_at,
        refresh_token=None if is_web else tokens.refresh_token,
        user=UserProfile.model_validate(result.user),
    )


@router.post("/login", summary="Log in with e-mail and password")
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings_from_state)],
    limiter: Annotated[RateLimiter, Depends(get_login_rate_limiter)],
) -> TokenResponse:
    address = _client_address(request)
    limit = await limiter.check(LOGIN_SCOPE, address)
    if not limit.allowed:
        raise ProblemError(
            status=status.HTTP_429_TOO_MANY_REQUESTS,
            type=problem_type("too-many-login-attempts"),
            title="Too many login attempts",
            detail="Too many failed logins from this address. Try again later.",
            extra={"retry_after_seconds": limit.retry_after_seconds},
        )

    try:
        result = await service.login(
            session,
            username=payload.username,
            password=payload.password,
            settings=settings,
            user_agent=request.headers.get("User-Agent"),
            ip_address=address,
        )
    except service.AuthenticationError as error:
        await limiter.record_failure(LOGIN_SCOPE, address)
        raise ProblemError(
            status=status.HTTP_401_UNAUTHORIZED,
            type=problem_type("invalid-credentials"),
            title="Invalid credentials",
            detail="Username or password is wrong.",
        ) from error
    except service.AccountDisabledError as error:
        raise ProblemError(
            status=status.HTTP_403_FORBIDDEN,
            type=problem_type("account-disabled"),
            title="Account disabled",
            detail="An admin has disabled this account.",
        ) from error

    await limiter.reset(LOGIN_SCOPE, address)
    return _token_response(
        result, response=response, settings=settings, is_web=payload.client == "web"
    )


@router.post("/refresh", summary="Exchange a refresh token for a new pair")
async def refresh(
    payload: RefreshRequest,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings_from_state)],
) -> TokenResponse:
    from_cookie = request.cookies.get(REFRESH_COOKIE_NAME)
    token = payload.refresh_token or from_cookie
    if token is None:
        raise ProblemError(
            status=status.HTTP_401_UNAUTHORIZED,
            type=problem_type("missing-refresh-token"),
            title="Missing refresh token",
            detail="Send the refresh token in the body or as a cookie.",
        )

    try:
        result = await service.rotate_refresh_token(
            session,
            token=token,
            settings=settings,
            user_agent=request.headers.get("User-Agent"),
            ip_address=_client_address(request),
        )
    except service.RefreshTokenReplayError as error:
        response.delete_cookie(REFRESH_COOKIE_NAME, path=REFRESH_COOKIE_PATH)
        raise ProblemError(
            status=status.HTTP_401_UNAUTHORIZED,
            type=problem_type("refresh-token-replayed"),
            title="Refresh token replayed",
            detail="This token was already used. All sessions of it were ended; log in again.",
        ) from error
    except service.InvalidRefreshTokenError as error:
        response.delete_cookie(REFRESH_COOKIE_NAME, path=REFRESH_COOKIE_PATH)
        raise ProblemError(
            status=status.HTTP_401_UNAUTHORIZED,
            type=problem_type("invalid-refresh-token"),
            title="Invalid refresh token",
            detail="The refresh token is unknown, expired or revoked. Log in again.",
        ) from error

    return _token_response(
        result, response=response, settings=settings, is_web=payload.refresh_token is None
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="End this session")
async def logout(
    payload: RefreshRequest,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    token = payload.refresh_token or request.cookies.get(REFRESH_COOKIE_NAME)
    if token is not None:
        await service.logout(session, token=token)
    response.delete_cookie(REFRESH_COOKIE_NAME, path=REFRESH_COOKIE_PATH)


@router.post("/password", summary="Set your own password")
async def change_password(
    payload: PasswordChangeRequest,
    request: Request,
    user: CurrentUser,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings_from_state)],
) -> TokenResponse:
    """Available while the starting password is still in place; that is the point of it.

    Answers with a fresh token pair: every other device is signed out, this one carries on.
    """
    try:
        tokens = await service.change_password(
            session,
            user=user,
            current_password=payload.current_password,
            new_password=payload.new_password,
            settings=settings,
            user_agent=request.headers.get("User-Agent"),
            ip_address=_client_address(request),
        )
    except service.AuthenticationError as error:
        raise ProblemError(
            status=status.HTTP_401_UNAUTHORIZED,
            type=problem_type("invalid-credentials"),
            title="Invalid credentials",
            detail="The current password is wrong.",
        ) from error

    return _token_response(
        service.LoginResult(user=user, tokens=tokens),
        response=response,
        settings=settings,
        is_web=payload.client == "web",
    )
