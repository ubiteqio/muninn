"""Logging in, refreshing, logging out and changing the own password."""

from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from muninn.api.v1.auth import REFRESH_COOKIE_NAME
from muninn.models.refresh_token import RefreshToken
from muninn.models.user import UserStatus
from tests.helpers import PASSWORD, auth_header, create_user, login

pytestmark = pytest.mark.usefixtures("api_client")


async def test_login_returns_a_token_pair(
    api_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await create_user(session_factory, username="anna", display_name="Anna")

    tokens = await login(api_client, username="anna")

    assert tokens["token_type"] == "bearer"
    assert tokens["refresh_token"]
    assert tokens["user"]["display_name"] == "Anna"
    assert datetime.fromisoformat(tokens["expires_at"]) > datetime.now(UTC)


async def test_login_ignores_the_case_of_the_username(
    api_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await create_user(session_factory, username="anna")

    response = await api_client.post(
        "/auth/login",
        json={"username": "ANNA", "password": PASSWORD, "client": "native"},
    )

    assert response.status_code == 200


async def test_login_records_the_time(
    api_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    user = await create_user(session_factory, username="anna")
    assert user.last_login_at is None

    await login(api_client, username="anna")

    async with session_factory() as session:
        refreshed = await session.get(type(user), user.id)
        assert refreshed is not None
        assert refreshed.last_login_at is not None


async def test_wrong_password_is_refused(
    api_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await create_user(session_factory, username="anna")

    response = await api_client.post("/auth/login", json={"username": "anna", "password": "falsch"})

    assert response.status_code == 401
    assert response.json()["type"] == "urn:muninn:problem:invalid-credentials"


async def test_unknown_account_looks_the_same_as_a_wrong_password(api_client: AsyncClient) -> None:
    response = await api_client.post(
        "/auth/login", json={"username": "niemand", "password": "falsch"}
    )

    assert response.status_code == 401
    assert response.json()["type"] == "urn:muninn:problem:invalid-credentials"


async def test_disabled_account_is_told_why(
    api_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await create_user(session_factory, username="anna", status=UserStatus.DISABLED)

    response = await api_client.post("/auth/login", json={"username": "anna", "password": PASSWORD})

    assert response.status_code == 403
    assert response.json()["type"] == "urn:muninn:problem:account-disabled"


async def test_web_client_gets_a_cookie_and_no_token_in_the_body(
    api_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await create_user(session_factory, username="anna")

    response = await api_client.post(
        "/auth/login",
        json={"username": "anna", "password": PASSWORD, "client": "web"},
    )

    assert response.json()["refresh_token"] is None
    cookie = response.cookies[REFRESH_COOKIE_NAME]
    assert cookie
    assert "httponly" in response.headers["set-cookie"].lower()


async def test_refresh_rotates_the_token(
    api_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await create_user(session_factory, username="anna")
    tokens = await login(api_client, username="anna")

    response = await api_client.post(
        "/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )

    assert response.status_code == 200
    assert response.json()["refresh_token"] != tokens["refresh_token"]


async def test_replaying_a_used_token_ends_the_whole_family(
    api_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await create_user(session_factory, username="anna")
    tokens = await login(api_client, username="anna")
    rotated = (
        await api_client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    ).json()

    replay = await api_client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    after_replay = await api_client.post(
        "/auth/refresh", json={"refresh_token": rotated["refresh_token"]}
    )

    assert replay.status_code == 401
    assert replay.json()["type"] == "urn:muninn:problem:refresh-token-replayed"
    # The token the honest client holds is dead too; that is the point.
    assert after_replay.status_code == 401


async def test_rotation_does_not_extend_the_session(
    api_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await create_user(session_factory, username="anna")
    tokens = await login(api_client, username="anna")

    await api_client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})

    async with session_factory() as session:
        expiries = list(await session.scalars(sa.select(RefreshToken.expires_at)))
    assert len(expiries) == 2
    assert expiries[0] == expiries[1]


async def test_expired_refresh_token_is_refused(
    api_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await create_user(session_factory, username="anna")
    tokens = await login(api_client, username="anna")

    async with session_factory() as session:
        await session.execute(
            sa.update(RefreshToken).values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
        await session.commit()

    response = await api_client.post(
        "/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )

    assert response.status_code == 401
    assert response.json()["type"] == "urn:muninn:problem:invalid-refresh-token"


async def test_refresh_without_any_token_is_refused(api_client: AsyncClient) -> None:
    response = await api_client.post("/auth/refresh", json={})

    assert response.status_code == 401
    assert response.json()["type"] == "urn:muninn:problem:missing-refresh-token"


async def test_logout_ends_the_session(
    api_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await create_user(session_factory, username="anna")
    tokens = await login(api_client, username="anna")

    logout = await api_client.post("/auth/logout", json={"refresh_token": tokens["refresh_token"]})
    reuse = await api_client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})

    assert logout.status_code == 204
    assert reuse.status_code == 401


async def test_too_many_failed_logins_are_throttled(
    api_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession], db_settings: object
) -> None:
    await create_user(session_factory, username="anna")

    for _ in range(10):
        await api_client.post("/auth/login", json={"username": "anna", "password": "falsch"})

    response = await api_client.post("/auth/login", json={"username": "anna", "password": PASSWORD})

    assert response.status_code == 429
    body = response.json()
    assert body["type"] == "urn:muninn:problem:too-many-login-attempts"
    assert body["retry_after_seconds"] > 0


async def test_a_successful_login_clears_the_counter(
    api_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await create_user(session_factory, username="anna")

    for _ in range(5):
        await api_client.post("/auth/login", json={"username": "anna", "password": "falsch"})
    await login(api_client, username="anna")
    for _ in range(5):
        await api_client.post("/auth/login", json={"username": "anna", "password": "falsch"})

    response = await api_client.post("/auth/login", json={"username": "anna", "password": PASSWORD})

    assert response.status_code == 200


async def test_changing_the_password_needs_the_current_one(
    api_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await create_user(session_factory, username="anna")
    tokens = await login(api_client, username="anna")

    response = await api_client.post(
        "/auth/password",
        json={"current_password": "falsch", "new_password": "das-neue-passwort9"},
        headers=auth_header(tokens),
    )

    assert response.status_code == 401


async def test_changing_the_password_keeps_this_device_signed_in(
    api_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await create_user(session_factory, username="anna", must_change_password=True)
    tokens = await login(api_client, username="anna")

    changed = await api_client.post(
        "/auth/password",
        json={
            "current_password": PASSWORD,
            "new_password": "das-neue-passwort9",
            "client": "native",
        },
        headers=auth_header(tokens),
    )

    assert changed.status_code == 200
    fresh = changed.json()
    assert fresh["user"]["must_change_password"] is False

    # The new pair works, and the starting password is gone.
    again = await api_client.post("/auth/refresh", json={"refresh_token": fresh["refresh_token"]})
    assert again.status_code == 200


async def test_changing_the_password_ends_the_other_sessions(
    api_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await create_user(session_factory, username="anna")
    on_the_phone = await login(api_client, username="anna")
    on_the_laptop = await login(api_client, username="anna")

    await api_client.post(
        "/auth/password",
        json={
            "current_password": PASSWORD,
            "new_password": "das-neue-passwort9",
            "client": "native",
        },
        headers=auth_header(on_the_laptop),
    )

    stranded = await api_client.post(
        "/auth/refresh", json={"refresh_token": on_the_phone["refresh_token"]}
    )
    assert stranded.status_code == 401

    with_old = await api_client.post("/auth/login", json={"username": "anna", "password": PASSWORD})
    assert with_old.status_code == 401


@pytest.mark.parametrize(
    "weak",
    ["kurz1", "nurbuchstaben", "12345678"],
    ids=["too short", "no digit", "no letter"],
)
async def test_a_password_that_breaks_the_rule_is_refused(
    api_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession], weak: str
) -> None:
    await create_user(session_factory, username="anna")
    tokens = await login(api_client, username="anna")

    response = await api_client.post(
        "/auth/password",
        json={"current_password": PASSWORD, "new_password": weak},
        headers=auth_header(tokens),
    )

    assert response.status_code == 422
    assert response.json()["type"] == "urn:muninn:problem:validation-failed"


async def test_an_access_token_is_needed(api_client: AsyncClient) -> None:
    response = await api_client.get("/me")

    assert response.status_code == 401
    assert response.json()["type"] == "urn:muninn:problem:not-authenticated"


async def test_a_forged_access_token_is_refused(api_client: AsyncClient) -> None:
    response = await api_client.get("/me", headers={"Authorization": "Bearer not.a.token"})

    assert response.status_code == 401
    assert response.json()["type"] == "urn:muninn:problem:invalid-access-token"


class TestFromAPhone:
    """The app on a phone is its own origin, so the browser in it asks permission first."""

    async def test_the_native_app_is_allowed_to_ask(self, api_client: AsyncClient) -> None:
        response = await api_client.options(
            "/auth/login",
            headers={
                "Origin": "capacitor://localhost",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )

        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == "capacitor://localhost"
        # The web app sends its session cookie on the same origin; the phone sends a token.
        assert response.headers["access-control-allow-credentials"] == "true"

    async def test_somewhere_else_is_not(self, api_client: AsyncClient) -> None:
        response = await api_client.options(
            "/auth/login",
            headers={
                "Origin": "https://woanders.example",
                "Access-Control-Request-Method": "POST",
            },
        )

        assert "access-control-allow-origin" not in response.headers


def test_the_origins_are_read_comma_separated_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from muninn.core.config import Settings

    # The form deploy/.env.example shows; a JSON list is not what anyone writes there.
    monkeypatch.setenv("MUNINN_CORS_ORIGINS", "capacitor://localhost, https://fotos.example")

    settings = Settings(
        database_url="postgresql+asyncpg://x@localhost/x", redis_url="redis://x", jwt_secret="x"
    )

    assert settings.cors_origins == ["capacitor://localhost", "https://fotos.example"]
