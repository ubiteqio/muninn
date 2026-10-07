"""The phones a user's bell reaches as push notifications."""

import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from muninn.models.device import Device, DevicePlatform
from muninn.models.user import User


async def register(session: AsyncSession, user: User, platform: DevicePlatform, token: str) -> None:
    """This phone pushes for this user from now on. A token known from somebody else - a phone
    handed on, a second account on it - moves to whoever registers it now."""
    await session.execute(
        insert(Device)
        .values(id=uuid.uuid4(), user_id=user.id, platform=platform.value, token=token)
        .on_conflict_do_update(
            index_elements=[Device.token],
            set_={"user_id": user.id, "platform": platform.value, "seen_at": func.now()},
        )
    )
    await session.commit()


async def forget(session: AsyncSession, user: User, token: str) -> None:
    """Signed out on that phone: it hears nothing more for this user. Somebody else's token is
    left alone."""
    await session.execute(delete(Device).where(Device.token == token, Device.user_id == user.id))
    await session.commit()


async def of_user(session: AsyncSession, user_id: uuid.UUID) -> list[Device]:
    return list(await session.scalars(select(Device).where(Device.user_id == user_id)))


async def gone(session: AsyncSession, tokens: list[str]) -> None:
    """Tokens the push service no longer knows: the app was removed, or notifications denied."""
    if tokens:
        await session.execute(delete(Device).where(Device.token.in_(tokens)))
        await session.commit()
