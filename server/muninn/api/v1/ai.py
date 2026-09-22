"""The machines Muninn asks (/admin/ai).

No address and no model name lives in the code: an admin sets up one profile per interface here,
and a spare beside it if they like.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from muninn.ai import service
from muninn.api.schemas.ai import AiCheckView, AiProfileCreate, AiProfileUpdate, AiProfileView
from muninn.core.deps import AdminUser, get_session
from muninn.core.problem import ProblemError, problem_type
from muninn.models.ai import AiProfile

router = APIRouter(prefix="/admin/ai", tags=["admin: ai"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def _profile_or_404(session: AsyncSession, profile_id: uuid.UUID) -> AiProfile:
    try:
        return await service.get_profile(session, profile_id)
    except service.ProfileNotFoundError as error:
        raise ProblemError(
            status=status.HTTP_404_NOT_FOUND,
            type=problem_type("ai-profile-not-found"),
            title="Profile not found",
            detail="No AI profile with this id.",
        ) from error


@router.get("/profiles", summary="The machines Muninn can ask")
async def list_profiles(admin: AdminUser, session: SessionDep) -> list[AiProfileView]:
    return [AiProfileView.of(profile) for profile in await service.list_profiles(session)]


@router.post("/profiles", summary="Add a machine", status_code=status.HTTP_201_CREATED)
async def create_profile(
    payload: AiProfileCreate, admin: AdminUser, session: SessionDep
) -> AiProfileView:
    """The first profile of an interface is the one in use; later ones are spares."""
    profile = await service.create_profile(session, **payload.model_dump())
    return AiProfileView.of(profile)


@router.patch("/profiles/{profile_id}", summary="Change a machine")
async def update_profile(
    profile_id: uuid.UUID, payload: AiProfileUpdate, admin: AdminUser, session: SessionDep
) -> AiProfileView:
    """A key that is not sent stays as it is: nobody should have to retype a secret."""
    profile = await _profile_or_404(session, profile_id)
    updated = await service.update_profile(session, profile, **payload.model_dump())
    return AiProfileView.of(updated)


@router.post("/profiles/{profile_id}/activate", summary="Use this machine for its interface")
async def activate_profile(
    profile_id: uuid.UUID, admin: AdminUser, session: SessionDep
) -> AiProfileView:
    profile = await _profile_or_404(session, profile_id)
    return AiProfileView.of(await service.activate(session, profile))


@router.delete(
    "/profiles/{profile_id}", summary="Remove a machine", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_profile(profile_id: uuid.UUID, admin: AdminUser, session: SessionDep) -> Response:
    """Removing the one in use leaves that interface without a machine, and the stage idle."""
    profile = await _profile_or_404(session, profile_id)
    await service.delete_profile(session, profile)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/profiles/{profile_id}/test", summary="Ask whether it is there")
async def test_profile(profile_id: uuid.UUID, admin: AdminUser, session: SessionDep) -> AiCheckView:
    """One small question - the connection, the key and the model name, nothing expensive."""
    profile = await _profile_or_404(session, profile_id)
    check = await service.check_profile(profile)
    return AiCheckView(
        ok=check.ok,
        detail=check.detail,
        milliseconds=check.milliseconds,
        dimensions=check.dimensions,
    )
