"""The phones the bell reaches: registered by the app, moved with the phone, forgotten on
sign-out."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from muninn.models.device import Device
from muninn.models.user import User, UserRole
from tests.test_comments import person

pytestmark = pytest.mark.usefixtures("api_client")

TOKEN = "a1b2c3d4" * 8


async def phones(session: AsyncSession) -> list[tuple[str, str]]:
    rows = await session.execute(
        select(User.username, Device.token)
        .join(User, User.id == Device.user_id)
        .order_by(Device.token)
        .execution_options(populate_existing=True)
    )
    return [(username, token) for username, token in rows]


async def test_a_phone_is_registered_once_moves_with_its_owner_and_is_forgotten(
    api_client: AsyncClient,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    anna = await person(api_client, session_factory, "anna", "Anna")
    jonas = await person(api_client, session_factory, "jonas", "Jonas")
    phone = {"platform": "ios", "token": TOKEN}

    assert (await api_client.post("/me/devices", json=phone, headers=anna)).status_code == 204
    # The app says so again on every start: still one phone.
    await api_client.post("/me/devices", json=phone, headers=anna)
    assert await phones(session) == [("anna", TOKEN)]

    # Jonas signs in on the same phone: it is his now.
    await api_client.post("/me/devices", json=phone, headers=jonas)
    assert await phones(session) == [("jonas", TOKEN)]

    # Anna cannot take it away from him; Jonas signing out can.
    await api_client.delete(f"/me/devices/{TOKEN}", headers=anna)
    assert await phones(session) == [("jonas", TOKEN)]
    await api_client.delete(f"/me/devices/{TOKEN}", headers=jonas)
    assert await phones(session) == []

    unknown = await api_client.post(
        "/me/devices", json={"platform": "palm", "token": TOKEN}, headers=anna
    )
    assert unknown.status_code == 422


async def test_a_deleted_account_takes_its_phones_along(
    api_client: AsyncClient,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    admin = await person(api_client, session_factory, "omi", "Omi", role=UserRole.ADMIN)
    anna = await person(api_client, session_factory, "anna", "Anna")
    await api_client.post("/me/devices", json={"platform": "ios", "token": TOKEN}, headers=anna)
    account = await session.scalar(select(User).where(User.username == "anna"))
    assert account is not None

    await api_client.delete(f"/admin/users/{account.id}", headers=admin)

    assert await phones(session) == []
