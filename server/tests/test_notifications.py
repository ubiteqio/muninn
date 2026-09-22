"""The bell and the news: who hears of what, bundled, and only they."""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from muninn.models.change_log import ChangeKind, ChangeLogEntry, SyncTrigger
from muninn.models.notification import NotificationKind
from muninn.models.user import User
from muninn.notify import service
from tests.test_comments import person, say
from tests.test_social import a_picture

pytestmark = pytest.mark.usefixtures("api_client")


async def bell(api_client: AsyncClient, headers: dict[str, str]) -> list[dict[str, object]]:
    items: list[dict[str, object]] = (
        await api_client.get("/notifications", headers=headers)
    ).json()["items"]
    return items


async def test_an_answer_a_mention_and_a_followed_comment_reach_the_right_people(
    api_client: AsyncClient,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    medium = await a_picture(session)
    anna = await person(api_client, session_factory, "anna", "Anna")
    boris = await person(api_client, session_factory, "boris", "Boris")
    lena = await person(api_client, session_factory, "lena", "Lena")
    omi = await person(api_client, session_factory, "omi", "Omi")
    where = f"/media/{medium.id}"
    # Omi keeps the picture in Walhall, so she hears of what is said about it.
    await api_client.post("/favorites", json={"media_id": str(medium.id)}, headers=omi)

    question = await say(api_client, anna, where, "Wo war das?")
    await say(api_client, boris, where, "In Venedig, frag @lena", parent_id=str(question["id"]))

    to_anna = await bell(api_client, anna)
    to_lena = await bell(api_client, lena)
    to_omi = await bell(api_client, omi)
    to_boris = await bell(api_client, boris)

    assert [(item["kind"], item["actors"]) for item in to_anna] == [("reply", ["Boris"])]
    assert [(item["kind"], item["actors"]) for item in to_lena] == [("mention", ["Boris"])]
    # Omi heard of both comments - as one notification, the most recent person first.
    assert [(item["kind"], item["actors"], item["count"]) for item in to_omi] == [
        ("comment", ["Boris", "Anna"], 2)
    ]
    assert to_omi[0]["excerpt"] == "In Venedig, frag @lena"
    # Nobody is told about what they did themselves.
    assert to_boris == []


async def test_a_like_on_my_comment_is_news_for_me(
    api_client: AsyncClient,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    medium = await a_picture(session)
    anna = await person(api_client, session_factory, "anna", "Anna")
    boris = await person(api_client, session_factory, "boris", "Boris")
    comment = await say(api_client, anna, f"/media/{medium.id}", "Schön!")

    await api_client.post(f"/comments/{comment['id']}/like", headers=boris)
    await api_client.post(f"/comments/{comment['id']}/like", headers=boris)

    assert [(item["kind"], item["count"]) for item in await bell(api_client, anna)] == [
        ("comment_like", 1)
    ]
    assert (await api_client.get("/notifications/unread", headers=anna)).json() == {"count": 1}


async def test_read_is_read_and_the_count_follows(
    api_client: AsyncClient,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    medium = await a_picture(session)
    other = await a_picture(session, "IMG_2.jpg")
    anna = await person(api_client, session_factory, "anna", "Anna")
    boris = await person(api_client, session_factory, "boris", "Boris")
    first = await say(api_client, anna, f"/media/{medium.id}", "Eins")
    second = await say(api_client, anna, f"/media/{other.id}", "Zwei")
    await say(api_client, boris, f"/media/{medium.id}", "Ja", parent_id=str(first["id"]))
    await say(api_client, boris, f"/media/{other.id}", "Ja", parent_id=str(second["id"]))
    items = await bell(api_client, anna)

    await api_client.post("/notifications/read", json={"ids": [str(items[0]["id"])]}, headers=anna)
    assert (await api_client.get("/notifications/unread", headers=anna)).json() == {"count": 1}

    await api_client.post("/notifications/read", json={}, headers=anna)
    assert (await api_client.get("/notifications/unread", headers=anna)).json() == {"count": 0}
    assert all(item["read"] for item in await bell(api_client, anna))


async def test_new_media_are_bundled_per_album_and_window(session: AsyncSession) -> None:
    medium = await a_picture(session)
    anna = User(username="anna", display_name="Anna", password_hash="x")
    session.add(anna)
    await session.commit()
    now = datetime.now(UTC)
    about = service.About(album_id=medium.album_id)

    await service.notify(session, [anna.id], NotificationKind.NEW_MEDIA, about, count=12, now=now)
    await service.notify(
        session,
        [anna.id],
        NotificationKind.NEW_MEDIA,
        about,
        count=30,
        now=now + timedelta(minutes=5),
    )
    # Beyond the window it is news of its own.
    await service.notify(
        session,
        [anna.id],
        NotificationKind.NEW_MEDIA,
        about,
        count=5,
        now=now + timedelta(minutes=20),
    )
    await session.commit()

    found, _ = await service.entries(session, anna)
    assert [entry.notification.count for entry in found] == [5, 42]


async def test_the_news_tells_what_everybody_did(
    api_client: AsyncClient,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    medium = await a_picture(session)
    for _ in range(3):
        session.add(
            ChangeLogEntry(
                kind=ChangeKind.MEDIA_ADDED,
                trigger=SyncTrigger.QUICK,
                album_id=medium.album_id,
                media_id=medium.id,
                path="Urlaub/IMG_1.jpg",
            )
        )
    await session.commit()
    anna = await person(api_client, session_factory, "anna", "Anna")
    boris = await person(api_client, session_factory, "boris", "Boris")
    await api_client.post(f"/media/{medium.id}/like", headers=boris)
    await say(api_client, anna, f"/media/{medium.id}", "Herrlich")

    news = (await api_client.get("/activity", headers=boris)).json()["items"]

    assert [(item["kind"], item["actor"], item["count"]) for item in news] == [
        ("comment", "Anna", 1),
        ("like", "Boris", 1),
        ("new_media", None, 3),
    ]
    assert news[0]["excerpt"] == "Herrlich"
    assert news[0]["media"]["id"] == str(medium.id)


async def test_nobody_else_sees_my_bell(
    api_client: AsyncClient,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    medium = await a_picture(session)
    anna = await person(api_client, session_factory, "anna", "Anna")
    boris = await person(api_client, session_factory, "boris", "Boris")
    lena = await person(api_client, session_factory, "lena", "Lena")
    comment = await say(api_client, anna, f"/media/{medium.id}", "Hallo")
    await say(api_client, boris, f"/media/{medium.id}", "Hi", parent_id=str(comment["id"]))

    assert await bell(api_client, lena) == []
    owners = await session.scalars(select(User.username))
    assert "lena" in list(owners)
