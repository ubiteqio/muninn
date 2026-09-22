"""Small helpers shared by the API tests."""

from typing import Any

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from muninn.core.security import hash_password
from muninn.models.user import User, UserRole, UserStatus

PASSWORD = "ein-gutes-passwort7"


async def create_user(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    username: str,
    display_name: str = "Test",
    email: str | None = None,
    password: str = PASSWORD,
    role: UserRole = UserRole.USER,
    status: UserStatus = UserStatus.ACTIVE,
    must_change_password: bool = False,
) -> User:
    async with session_factory() as session:
        user = User(
            username=username,
            email=email,
            display_name=display_name,
            password_hash=hash_password(password),
            role=role,
            status=status,
            must_change_password=must_change_password,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


async def login(
    client: AsyncClient,
    *,
    username: str,
    password: str = PASSWORD,
    client_kind: str = "native",
) -> dict[str, Any]:
    response = await client.post(
        "/auth/login",
        json={"username": username, "password": password, "client": client_kind},
    )
    response.raise_for_status()
    body: dict[str, Any] = response.json()
    return body


def auth_header(tokens: dict[str, Any]) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}
