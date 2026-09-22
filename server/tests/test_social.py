"""Likes and Walhall: public hearts, private stars."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from muninn.models.media import Media, MediaStatus
from muninn.models.social import Like
from muninn.models.user import User, UserRole
from tests.helpers import auth_header, create_user, login
from tests.test_timeline import JULY, a_medium, an_album

pytestmark = pytest.mark.usefixtures("api_client")


async def signed_in(
    api_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    username: str,
    name: str,
) -> dict[str, str]:
    await create_user(session_factory, username=username, display_name=name, role=UserRole.USER)
    return auth_header(await login(api_client, username=username))


async def a_picture(session: AsyncSession, name: str = "IMG_1.jpg") -> Media:
    album = await an_album(session, f"Urlaub-{uuid.uuid4().hex[:6]}")
    medium = await a_medium(session, album, taken_at=JULY, name=name)
    await session.commit()
    return medium


async def test_everybody_sees_who_liked_a_picture_and_it_counts_once(
    api_client: AsyncClient,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    medium = await a_picture(session)
    anna = await signed_in(api_client, session_factory, "anna", "Anna")
    boris = await signed_in(api_client, session_factory, "boris", "Boris")

    await api_client.post(f"/media/{medium.id}/like", headers=anna)
    await api_client.post(f"/media/{medium.id}/like", headers=anna)
    seen = (await api_client.post(f"/media/{medium.id}/like", headers=boris)).json()

    assert seen == {
        "likes": 2,
        "liked": True,
        "likers": ["Boris", "Anna"],
        "favorite": False,
        "comments": 0,
        "reaction": "heart",
        "reactions": [{"reaction": "heart", "count": 2}],
        "people": [{"name": "Boris", "reaction": "heart"}, {"name": "Anna", "reaction": "heart"}],
    }
    # Anna sees the same heart, herself first.
    detail = (await api_client.get(f"/media/{medium.id}", headers=anna)).json()
    assert detail["social"]["likers"] == ["Anna", "Boris"]


async def test_a_reaction_replaces_the_last_one_and_is_counted_by_kind(
    api_client: AsyncClient,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    medium = await a_picture(session)
    anna = await signed_in(api_client, session_factory, "anna", "Anna")
    boris = await signed_in(api_client, session_factory, "boris", "Boris")
    clara = await signed_in(api_client, session_factory, "clara", "Clara")

    await api_client.post(f"/media/{medium.id}/like", headers=anna)
    await api_client.post(f"/media/{medium.id}/like", json={"reaction": "joy"}, headers=anna)
    await api_client.post(f"/media/{medium.id}/like", json={"reaction": "joy"}, headers=boris)
    seen = (
        await api_client.post(
            f"/media/{medium.id}/like", json={"reaction": "hang_loose"}, headers=clara
        )
    ).json()

    assert seen["likes"] == 3
    assert seen["reaction"] == "hang_loose"
    assert seen["reactions"] == [
        {"reaction": "joy", "count": 2},
        {"reaction": "hang_loose", "count": 1},
    ]
    assert {person["name"]: person["reaction"] for person in seen["people"]} == {
        "Clara": "hang_loose",
        "Anna": "joy",
        "Boris": "joy",
    }
    news = (await api_client.get("/activity", headers=anna)).json()["items"]
    assert {item["reaction"] for item in news if item["kind"] == "like"} == {"joy", "hang_loose"}


async def test_an_unknown_reaction_is_refused(
    api_client: AsyncClient,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    medium = await a_picture(session)
    anna = await signed_in(api_client, session_factory, "anna", "Anna")

    response = await api_client.post(
        f"/media/{medium.id}/like", json={"reaction": "poop"}, headers=anna
    )

    assert response.status_code == 422


async def test_a_like_can_be_taken_back(
    api_client: AsyncClient,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    medium = await a_picture(session)
    anna = await signed_in(api_client, session_factory, "anna", "Anna")
    await api_client.post(f"/media/{medium.id}/like", headers=anna)

    seen = (await api_client.delete(f"/media/{medium.id}/like", headers=anna)).json()
    again = await api_client.delete(f"/media/{medium.id}/like", headers=anna)

    assert seen == {
        "likes": 0,
        "liked": False,
        "likers": [],
        "favorite": False,
        "comments": 0,
        "reaction": None,
        "reactions": [],
        "people": [],
    }
    assert again.status_code == 200


async def test_albums_are_liked_too(
    api_client: AsyncClient,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    medium = await a_picture(session)
    anna = await signed_in(api_client, session_factory, "anna", "Anna")

    seen = (await api_client.post(f"/albums/{medium.album_id}/like", headers=anna)).json()

    assert seen["likes"] == 1
    assert (await api_client.get(f"/albums/{medium.album_id}/social", headers=anna)).json()["liked"]


async def test_nothing_that_is_not_there_can_be_liked(
    api_client: AsyncClient,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    medium = await a_picture(session)
    medium.status = MediaStatus.MISSING
    await session.commit()
    anna = await signed_in(api_client, session_factory, "anna", "Anna")

    gone = await api_client.post(f"/media/{medium.id}/like", headers=anna)
    never = await api_client.post(f"/media/{uuid.uuid4()}/like", headers=anna)

    assert (gone.status_code, never.status_code) == (404, 404)
    assert gone.headers["content-type"].startswith("application/problem+json")


async def test_walhall_is_private_and_newest_first(
    api_client: AsyncClient,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    first = await a_picture(session, "IMG_1.jpg")
    second = await a_picture(session, "IMG_2.jpg")
    anna = await signed_in(api_client, session_factory, "anna", "Anna")
    boris = await signed_in(api_client, session_factory, "boris", "Boris")

    await api_client.post("/favorites", json={"media_id": str(first.id)}, headers=anna)
    await api_client.post("/favorites", json={"media_id": str(second.id)}, headers=anna)
    await api_client.post("/favorites", json={"album_id": str(first.album_id)}, headers=anna)

    mine = (await api_client.get("/favorites/media", headers=anna)).json()
    theirs = (await api_client.get("/favorites/media", headers=boris)).json()
    albums = (await api_client.get("/favorites/albums", headers=anna)).json()

    assert [item["origin"]["filename"] for item in mine["items"]] == ["IMG_2.jpg", "IMG_1.jpg"]
    assert theirs["items"] == []
    assert [album["id"] for album in albums] == [str(first.album_id)]
    detail = (await api_client.get(f"/media/{first.id}", headers=anna)).json()
    assert detail["social"]["favorite"] is True

    await api_client.request("DELETE", "/favorites", json={"media_id": str(first.id)}, headers=anna)
    left = (await api_client.get("/favorites/media", headers=anna)).json()
    assert [item["origin"]["filename"] for item in left["items"]] == ["IMG_2.jpg"]


async def test_walhall_hands_out_pages(
    api_client: AsyncClient,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    anna = await signed_in(api_client, session_factory, "anna", "Anna")
    for index in range(3):
        medium = await a_picture(session, f"IMG_{index}.jpg")
        await api_client.post("/favorites", json={"media_id": str(medium.id)}, headers=anna)

    first = (await api_client.get("/favorites/media?limit=2", headers=anna)).json()
    rest = (
        await api_client.get(
            "/favorites/media", params={"limit": 2, "before": first["next_cursor"]}, headers=anna
        )
    ).json()

    assert len(first["items"]) == 2
    assert len(rest["items"]) == 1
    assert rest["next_cursor"] is None


async def test_a_favourite_names_exactly_one_thing(
    api_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    anna = await signed_in(api_client, session_factory, "anna", "Anna")

    both = await api_client.post(
        "/favorites",
        json={"media_id": str(uuid.uuid4()), "album_id": str(uuid.uuid4())},
        headers=anna,
    )
    neither = await api_client.post("/favorites", json={}, headers=anna)

    assert (both.status_code, neither.status_code) == (422, 422)


async def test_likes_go_with_the_medium(session: AsyncSession) -> None:
    """Decided on 2026-09-21: when a medium is removed for good, its likes go with it."""
    medium = await a_picture(session)
    person = User(username="anna", display_name="Anna", password_hash="x", role=UserRole.USER)
    session.add(person)
    await session.flush()
    session.add(Like(user_id=person.id, media_id=medium.id))
    await session.commit()

    await session.delete(medium)
    await session.commit()

    assert await session.scalar(select(Like.id)) is None
