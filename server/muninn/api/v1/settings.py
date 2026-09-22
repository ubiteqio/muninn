"""Runtime settings of the installation (/admin/settings)."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from muninn.api.schemas.settings import SettingsUpdate, SettingsView
from muninn.core.deps import AdminUser, get_session
from muninn.settings import service

router = APIRouter(prefix="/admin/settings", tags=["admin: settings"])


@router.get("", summary="Read the settings")
async def read_settings(
    admin: AdminUser,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SettingsView:
    settings = await service.get_settings(session)
    return SettingsView.model_validate(settings)


@router.put("", summary="Change the settings")
async def write_settings(
    payload: SettingsUpdate,
    admin: AdminUser,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SettingsView:
    """New sizes apply to derivatives made from now on; existing ones stay until they are redone."""
    settings = await service.update_settings(session, **payload.model_dump())
    return SettingsView.model_validate(settings)
