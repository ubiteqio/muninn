"""The settings an admin may change at runtime (/admin/settings)."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from muninn.models.settings import (
    DEFAULT_IGNORED_NAMES,
    DEFAULT_PREVIEW_SIZE,
    DEFAULT_THUMBNAIL_SIZE,
)
from muninn.models.user import UserRole
from tests.helpers import auth_header, create_user, login

pytestmark = pytest.mark.usefixtures("api_client")

VALID = {
    "thumbnail_size": 320,
    "preview_size": 1600,
    "image_quality": 90,
    "video_height": 1080,
    "ignored_names": ["@eaDir", "#recycle"],
    "quick_sync_seconds": 300,
    "full_sync_hour": 3,
    "stability_seconds": 30,
    "missing_grace_days": 30,
    "deletion_share_percent": 5,
    "deletion_count": 500,
    "nas_agent_enabled": False,
}


async def _admin_headers(
    api_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> dict[str, str]:
    await create_user(session_factory, username="admin", display_name="Admin", role=UserRole.ADMIN)
    return auth_header(await login(api_client, username="admin"))


async def test_the_defaults_are_the_values_from_the_concept(
    api_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    headers = await _admin_headers(api_client, session_factory)

    response = await api_client.get("/admin/settings", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["thumbnail_size"] == DEFAULT_THUMBNAIL_SIZE
    assert body["preview_size"] == DEFAULT_PREVIEW_SIZE
    assert body["ignored_names"] == DEFAULT_IGNORED_NAMES
    assert body["quick_sync_seconds"] == 300
    assert body["missing_grace_days"] == 30
    # No pause before deletions unless an admin asks for one.
    assert (body["deletion_share_percent"], body["deletion_count"]) == (0, 0)


async def test_a_user_may_not_read_or_change_the_settings(
    api_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await create_user(session_factory, username="anna", display_name="Anna")
    headers = auth_header(await login(api_client, username="anna"))

    assert (await api_client.get("/admin/settings", headers=headers)).status_code == 403
    assert (await api_client.put("/admin/settings", json=VALID, headers=headers)).status_code == 403


async def test_without_a_token_the_settings_stay_closed(api_client: AsyncClient) -> None:
    assert (await api_client.get("/admin/settings")).status_code == 401


async def test_a_change_is_stored_and_read_back(
    api_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    headers = await _admin_headers(api_client, session_factory)

    response = await api_client.put("/admin/settings", json=VALID, headers=headers)

    assert response.status_code == 200
    assert response.json()["thumbnail_size"] == 320

    again = await api_client.get("/admin/settings", headers=headers)
    assert again.json()["preview_size"] == 1600
    assert again.json()["video_height"] == 1080


@pytest.mark.parametrize(
    "change",
    [
        {"thumbnail_size": 40},
        {"thumbnail_size": 4000},
        {"preview_size": 400},
        {"image_quality": 10},
        {"video_height": 120},
        {"ignored_names": ["   "]},
        {"ignored_names": ["fotos/2009"]},
        {"quick_sync_seconds": 10},
        {"full_sync_hour": 24},
        {"stability_seconds": 1},
        {"missing_grace_days": -1},
        # The safety net can be adjusted, never switched off.
        {"deletion_share_percent": 80},
        {"deletion_count": -1},
        # A preview no larger than the thumbnail would make the thumbnail the better picture.
        {"thumbnail_size": 900, "preview_size": 900},
    ],
)
async def test_values_outside_the_bounds_are_refused(
    api_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    change: dict[str, object],
) -> None:
    headers = await _admin_headers(api_client, session_factory)

    response = await api_client.put("/admin/settings", json={**VALID, **change}, headers=headers)

    assert response.status_code == 422
    # Refusing has to leave the stored settings alone.
    assert (await api_client.get("/admin/settings", headers=headers)).json()[
        "thumbnail_size"
    ] == DEFAULT_THUMBNAIL_SIZE


async def test_ignored_names_are_trimmed_and_deduplicated(
    api_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    headers = await _admin_headers(api_client, session_factory)

    response = await api_client.put(
        "/admin/settings",
        json={**VALID, "ignored_names": [" @eaDir ", "@EADIR", "#recycle"]},
        headers=headers,
    )

    assert response.json()["ignored_names"] == ["@eaDir", "#recycle"]


async def test_the_settings_survive_a_missing_row(
    session: AsyncSession,
) -> None:
    """The row is truncated between tests, so this reads it back from the defaults."""
    from muninn.settings import service

    settings = await service.get_settings(session)

    assert settings.thumbnail_size == DEFAULT_THUMBNAIL_SIZE
    assert settings.ignored_names == DEFAULT_IGNORED_NAMES


async def test_the_sync_settings_are_stored(
    api_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """A grace period of zero removes a missing medium at once, which is allowed on purpose."""
    headers = await _admin_headers(api_client, session_factory)

    response = await api_client.put(
        "/admin/settings",
        json={**VALID, "quick_sync_seconds": 600, "missing_grace_days": 0},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["quick_sync_seconds"] == 600
    assert response.json()["missing_grace_days"] == 0
