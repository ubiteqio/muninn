"""The own account and admin user management."""

import uuid

import pytest
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from muninn.models.refresh_token import RefreshToken
from muninn.models.user import User, UserRole, UserStatus
from tests.helpers import PASSWORD, auth_header, create_user, login

pytestmark = pytest.mark.usefixtures("api_client")


async def _admin_headers(
    api_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    username: str = "admin",
) -> dict[str, str]:
    await create_user(session_factory, username=username, display_name="Admin", role=UserRole.ADMIN)
    return auth_header(await login(api_client, username=username))


async def test_admin_creates_an_account_and_gets_the_starting_password(
    api_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    headers = await _admin_headers(api_client, session_factory)

    response = await api_client.post(
        "/admin/users",
        json={"username": "anna", "display_name": "Anna"},
        headers=headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["user"]["must_change_password"] is True
    assert body["user"]["role"] == "user"
    assert len(body["starting_password"]) >= 12
    # A generated password meets the same rule people have to meet.
    assert any(character.isdigit() for character in body["starting_password"])
    assert any(character.isalpha() for character in body["starting_password"])

    # The starting password really works.
    tokens = await login(api_client, username="anna", password=body["starting_password"])
    assert tokens["user"]["username"] == "anna"


async def test_the_starting_password_is_not_stored_in_clear_text(
    api_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    headers = await _admin_headers(api_client, session_factory)

    created = await api_client.post(
        "/admin/users",
        json={"username": "anna", "display_name": "Anna"},
        headers=headers,
    )
    starting_password = created.json()["starting_password"]

    async with session_factory() as session:
        stored = await session.scalar(sa.select(User.password_hash).where(User.username == "anna"))
    assert stored is not None
    assert starting_password not in stored
    assert stored.startswith("$argon2id$")


async def test_a_duplicate_username_is_refused(
    api_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    headers = await _admin_headers(api_client, session_factory)
    await create_user(session_factory, username="anna")

    response = await api_client.post(
        "/admin/users",
        json={"username": "ANNA", "display_name": "Anna again"},
        headers=headers,
    )

    assert response.status_code == 409
    assert response.json()["type"] == "urn:muninn:problem:name-already-used"


async def test_a_normal_user_cannot_reach_the_admin_area(
    api_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await create_user(session_factory, username="anna")
    tokens = await login(api_client, username="anna")

    response = await api_client.get("/admin/users", headers=auth_header(tokens))

    assert response.status_code == 403
    assert response.json()["type"] == "urn:muninn:problem:admin-required"


async def test_the_starting_password_blocks_everything_but_the_own_account(
    api_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await create_user(session_factory, username="anna", must_change_password=True)
    tokens = await login(api_client, username="anna")

    profile = await api_client.get("/me", headers=auth_header(tokens))
    change = await api_client.patch(
        "/me", json={"display_name": "Anna B"}, headers=auth_header(tokens)
    )

    assert profile.status_code == 200
    assert profile.json()["must_change_password"] is True
    assert change.status_code == 403
    assert change.json()["type"] == "urn:muninn:problem:password-change-required"


async def test_a_user_can_rename_themselves(
    api_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await create_user(session_factory, username="anna", display_name="Anna")
    tokens = await login(api_client, username="anna")

    response = await api_client.patch(
        "/me", json={"display_name": "Anna B."}, headers=auth_header(tokens)
    )

    assert response.status_code == 200
    assert response.json()["display_name"] == "Anna B."


async def test_the_list_pages_with_a_cursor(
    api_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    headers = await _admin_headers(api_client, session_factory)
    for index in range(4):
        await create_user(session_factory, username=f"user{index}")

    first = await api_client.get("/admin/users?limit=2", headers=headers)
    body = first.json()
    second = await api_client.get(
        f"/admin/users?limit=2&cursor={body['next_cursor']}", headers=headers
    )

    assert first.status_code == 200
    assert len(body["items"]) == 2
    assert body["next_cursor"] is not None

    seen = {user["username"] for user in body["items"]} | {
        user["username"] for user in second.json()["items"]
    }
    assert len(seen) == 4


async def test_the_last_page_has_no_cursor(
    api_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    headers = await _admin_headers(api_client, session_factory)

    response = await api_client.get("/admin/users?limit=50", headers=headers)

    assert response.json()["next_cursor"] is None


async def test_a_made_up_cursor_is_refused(
    api_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    headers = await _admin_headers(api_client, session_factory)

    response = await api_client.get("/admin/users?cursor=nonsense", headers=headers)

    assert response.status_code == 400
    assert response.json()["type"] == "urn:muninn:problem:invalid-cursor"


async def test_an_admin_can_promote_somebody(
    api_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    headers = await _admin_headers(api_client, session_factory)
    anna = await create_user(session_factory, username="anna")

    response = await api_client.patch(
        f"/admin/users/{anna.id}", json={"role": "admin"}, headers=headers
    )

    assert response.status_code == 200
    assert response.json()["role"] == "admin"


async def test_disabling_an_account_ends_its_sessions(
    api_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    headers = await _admin_headers(api_client, session_factory)
    anna = await create_user(session_factory, username="anna")
    tokens = await login(api_client, username="anna")

    disabled = await api_client.patch(
        f"/admin/users/{anna.id}", json={"status": "disabled"}, headers=headers
    )
    reuse = await api_client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    with_access_token = await api_client.get("/me", headers=auth_header(tokens))

    assert disabled.status_code == 200
    assert reuse.status_code == 401
    assert with_access_token.status_code == 401

    async with session_factory() as session:
        revoked = await session.scalars(
            sa.select(RefreshToken.revoked_at).where(RefreshToken.user_id == anna.id)
        )
        assert all(value is not None for value in revoked)


async def test_the_last_admin_cannot_be_demoted(
    api_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    headers = await _admin_headers(api_client, session_factory)
    async with session_factory() as session:
        admin_id = await session.scalar(sa.select(User.id).where(User.role == UserRole.ADMIN))

    response = await api_client.patch(
        f"/admin/users/{admin_id}", json={"role": "user"}, headers=headers
    )

    assert response.status_code == 409
    assert response.json()["type"] == "urn:muninn:problem:last-admin"


async def test_the_last_admin_cannot_be_disabled(
    api_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    headers = await _admin_headers(api_client, session_factory)
    async with session_factory() as session:
        admin_id = await session.scalar(sa.select(User.id).where(User.role == UserRole.ADMIN))

    response = await api_client.patch(
        f"/admin/users/{admin_id}", json={"status": "disabled"}, headers=headers
    )

    assert response.status_code == 409


async def test_an_admin_may_step_down_when_another_one_is_left(
    api_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    headers = await _admin_headers(api_client, session_factory)
    second = await create_user(session_factory, username="zweiter", role=UserRole.ADMIN)

    response = await api_client.patch(
        f"/admin/users/{second.id}", json={"role": "user"}, headers=headers
    )

    assert response.status_code == 200


async def test_a_forgotten_password_is_reset_by_an_admin(
    api_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    headers = await _admin_headers(api_client, session_factory)
    anna = await create_user(session_factory, username="anna")
    old_tokens = await login(api_client, username="anna")

    response = await api_client.post(f"/admin/users/{anna.id}/password", headers=headers)
    new_password = response.json()["starting_password"]

    assert response.status_code == 200

    # The old password and the old session are gone, the new one works and is a starting password.
    with_old = await api_client.post("/auth/login", json={"username": "anna", "password": PASSWORD})
    reuse = await api_client.post(
        "/auth/refresh", json={"refresh_token": old_tokens["refresh_token"]}
    )
    with_new = await login(api_client, username="anna", password=new_password)

    assert with_old.status_code == 401
    assert reuse.status_code == 401
    assert with_new["user"]["must_change_password"] is True


async def test_an_unknown_account_is_a_404(
    api_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    headers = await _admin_headers(api_client, session_factory)

    response = await api_client.patch(
        f"/admin/users/{uuid.uuid4()}", json={"display_name": "X"}, headers=headers
    )

    assert response.status_code == 404
    assert response.json()["type"] == "urn:muninn:problem:user-not-found"


async def test_a_created_admin_is_really_an_admin(
    api_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    headers = await _admin_headers(api_client, session_factory)

    response = await api_client.post(
        "/admin/users",
        json={"username": "zweiter", "display_name": "Zweiter", "role": "admin"},
        headers=headers,
    )

    assert response.status_code == 201
    assert response.json()["user"]["role"] == UserRole.ADMIN.value
    assert response.json()["user"]["status"] == UserStatus.ACTIVE.value


async def test_an_admin_changes_name_username_and_email(
    api_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    headers = await _admin_headers(api_client, session_factory)
    anna = await create_user(session_factory, username="anna")

    changed = await api_client.patch(
        f"/admin/users/{anna.id}",
        json={"display_name": "Anna Berg", "username": "anna.berg", "email": "anna@example.org"},
        headers=headers,
    )
    cleared = await api_client.patch(f"/admin/users/{anna.id}", json={"email": ""}, headers=headers)

    assert (changed.json()["display_name"], changed.json()["username"]) == (
        "Anna Berg",
        "anna.berg",
    )
    assert changed.json()["email"] == "anna@example.org"
    assert cleared.json()["email"] is None
    # The new name is the one to sign in with.
    assert await login(api_client, username="anna.berg")


async def test_a_username_somebody_else_has_is_refused(
    api_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    headers = await _admin_headers(api_client, session_factory)
    anna = await create_user(session_factory, username="anna")
    await create_user(session_factory, username="boris")

    response = await api_client.patch(
        f"/admin/users/{anna.id}", json={"username": "Boris"}, headers=headers
    )

    assert response.status_code == 409
    assert response.json()["type"].endswith("name-already-used")


async def test_an_admin_deletes_an_account_with_what_was_only_theirs(
    api_client: AsyncClient,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    from tests.test_social import a_picture

    headers = await _admin_headers(api_client, session_factory)
    await create_user(session_factory, username="anna", display_name="Anna")
    anna_headers = auth_header(await login(api_client, username="anna"))
    medium = await a_picture(session)
    await api_client.post(f"/media/{medium.id}/like", headers=anna_headers)
    await api_client.post(
        f"/media/{medium.id}/comments", json={"body": "Schön"}, headers=anna_headers
    )
    anna_id = (await api_client.get("/me", headers=anna_headers)).json()["id"]

    response = await api_client.delete(f"/admin/users/{anna_id}", headers=headers)

    assert response.status_code == 204
    social = (await api_client.get(f"/media/{medium.id}/social", headers=headers)).json()
    assert (social["likes"], social["comments"]) == (0, 0)
    assert (await api_client.get(f"/admin/users/{anna_id}", headers=headers)).status_code in (
        404,
        405,
    )


async def test_nobody_deletes_themselves_or_the_last_admin(
    api_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    headers = await _admin_headers(api_client, session_factory)
    me = (await api_client.get("/me", headers=headers)).json()["id"]

    own = await api_client.delete(f"/admin/users/{me}", headers=headers)

    assert own.status_code == 409
    assert own.json()["type"].endswith("own-account")


async def test_a_user_cannot_delete_accounts(
    api_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await create_user(session_factory, username="anna")
    boris = await create_user(session_factory, username="boris")
    headers = auth_header(await login(api_client, username="anna"))

    assert (await api_client.delete(f"/admin/users/{boris.id}", headers=headers)).status_code == 403
