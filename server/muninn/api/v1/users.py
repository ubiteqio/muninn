"""The own account (/me) and admin user management (/admin/users)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from muninn.api.schemas.pagination import Page, decode_cursor, encode_cursor
from muninn.api.schemas.users import (
    PasswordReset,
    ProfileUpdate,
    UserCreate,
    UserCreated,
    UserProfile,
    UserUpdate,
)
from muninn.core.deps import ActiveUser, AdminUser, CurrentUser, get_session
from muninn.core.problem import ProblemError, problem_type
from muninn.models.user import User
from muninn.users import service

me_router = APIRouter(tags=["account"])
admin_router = APIRouter(prefix="/admin/users", tags=["admin: users"])


@me_router.get("/me", summary="Your own account")
async def read_me(user: CurrentUser) -> UserProfile:
    """Readable even while the starting password is still in place, so the app can react to it."""
    return UserProfile.model_validate(user)


@me_router.patch("/me", summary="Change your own account")
async def update_me(
    payload: ProfileUpdate,
    user: ActiveUser,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> UserProfile:
    updated = await service.update_own_profile(
        session, user=user, display_name=payload.display_name
    )
    return UserProfile.model_validate(updated)


@admin_router.get("", summary="List all accounts")
async def list_users(
    admin: AdminUser,
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=service.MAX_PAGE_SIZE)] = service.DEFAULT_PAGE_SIZE,
    cursor: str | None = None,
) -> Page[UserProfile]:
    decoded = None
    if cursor is not None:
        try:
            decoded = decode_cursor(cursor)
        except ValueError as error:
            raise ProblemError(
                status=status.HTTP_400_BAD_REQUEST,
                type=problem_type("invalid-cursor"),
                title="Invalid cursor",
                detail="Pass back a cursor exactly as it was handed out.",
            ) from error

    users, has_more = await service.list_users(session, limit=limit, cursor=decoded)
    next_cursor = encode_cursor(users[-1].created_at, users[-1].id) if has_more and users else None

    return Page(items=[UserProfile.model_validate(user) for user in users], next_cursor=next_cursor)


@admin_router.post("", status_code=status.HTTP_201_CREATED, summary="Create an account")
async def create_user(
    payload: UserCreate,
    admin: AdminUser,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> UserCreated:
    """Returns the starting password once. Pass it on personally; Muninn sends no mail."""
    try:
        created = await service.create_user(
            session,
            username=payload.username,
            display_name=payload.display_name,
            email=payload.email,
            role=payload.role,
        )
    except service.NameAlreadyUsedError as error:
        raise ProblemError(
            status=status.HTTP_409_CONFLICT,
            type=problem_type("name-already-used"),
            title="Name already used",
            detail="Another account already uses this username or e-mail address.",
        ) from error

    return UserCreated(
        user=UserProfile.model_validate(created.user),
        starting_password=created.starting_password,
    )


@admin_router.patch("/{user_id}", summary="Change an account")
async def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    admin: AdminUser,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> UserProfile:
    target = await _load(session, user_id)
    try:
        updated = await service.update_user(
            session,
            user=target,
            display_name=payload.display_name,
            username=payload.username,
            email=payload.email or None,
            clear_email=payload.email == "",
            role=payload.role,
            status=payload.status,
        )
    except service.NameAlreadyUsedError as error:
        raise ProblemError(
            status=status.HTTP_409_CONFLICT,
            type=problem_type("name-already-used"),
            title="Name already used",
            detail="Another account already uses this username or e-mail address.",
        ) from error
    except service.LastAdminError as error:
        raise ProblemError(
            status=status.HTTP_409_CONFLICT,
            type=problem_type("last-admin"),
            title="Last admin",
            detail="This is the last active admin; make somebody else admin first.",
        ) from error

    return UserProfile.model_validate(updated)


@admin_router.delete(
    "/{user_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete an account for good"
)
async def delete_user(
    user_id: uuid.UUID,
    admin: AdminUser,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    """Removes the account with its likes, favourites, comments and notifications. Nobody
    deletes their own account here, and the last admin stays."""
    target = await _load(session, user_id)
    try:
        await service.delete_user(session, user=target, admin=admin)
    except service.SelfDeletionError as error:
        raise ProblemError(
            status=status.HTTP_409_CONFLICT,
            type=problem_type("own-account"),
            title="Own account",
            detail="You cannot delete the account you are signed in with.",
        ) from error
    except service.LastAdminError as error:
        raise ProblemError(
            status=status.HTTP_409_CONFLICT,
            type=problem_type("last-admin"),
            title="Last admin",
            detail="This is the last active admin; make somebody else admin first.",
        ) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@admin_router.post("/{user_id}/password", summary="Issue a new starting password")
async def reset_password(
    user_id: uuid.UUID,
    admin: AdminUser,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PasswordReset:
    """The way back in after a forgotten password, since Muninn cannot send mail."""
    target = await _load(session, user_id)
    starting_password = await service.reset_password(session, user=target)
    return PasswordReset(starting_password=starting_password)


async def _load(session: AsyncSession, user_id: uuid.UUID) -> User:
    try:
        return await service.get_user(session, user_id)
    except service.UserNotFoundError as error:
        raise ProblemError(
            status=status.HTTP_404_NOT_FOUND,
            type=problem_type("user-not-found"),
            title="User not found",
            detail="No account with this id.",
        ) from error
