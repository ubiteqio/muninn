"""The bell and the news: who hears of what, bundled, and only they."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from muninn.huginn import attempts
from muninn.models.attempt import GIVE_UP_AFTER
from muninn.models.change_log import ChangeKind, ChangeLogEntry, SyncTrigger
from muninn.models.face import Face, Person
from muninn.models.notification import Notification, NotificationKind
from muninn.models.user import User, UserRole, UserStatus
from muninn.notify import service
from tests.helpers import create_user
from tests.test_comments import person, say
from tests.test_people import at, faces_in_a_photo
from tests.test_social import a_picture
from tests.test_timeline import JULY, a_medium, an_album

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
    assert [preview["id"] for preview in news[0]["previews"]] == [str(medium.id)]


async def test_new_media_in_the_news_bring_their_first_pictures(
    api_client: AsyncClient,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The feed shows a batch as a grid: the first four that arrived, each once, with the
    larger copy the viewer already has beside the thumbnail."""
    album = await an_album(session, "Sommer")
    media = [await a_medium(session, album, taken_at=JULY, name=f"IMG_{n}.jpg") for n in range(6)]
    for medium in media:
        medium.thumbnail_path = f"thumbs/{medium.id}.jpg"
        medium.preview_path = f"previews/{medium.id}.jpg"
    started = datetime(2026, 7, 1, 10, 0, tzinfo=UTC)
    # The first picture arrives twice; it is shown once.
    arrivals = [media[0], media[0], *media[1:]]
    for minute, medium in enumerate(arrivals):
        session.add(
            ChangeLogEntry(
                kind=ChangeKind.MEDIA_ADDED,
                trigger=SyncTrigger.QUICK,
                album_id=album.id,
                media_id=medium.id,
                path=f"Sommer/{medium.id}.jpg",
                occurred_at=started + timedelta(minutes=minute),
            )
        )
    await session.commit()
    anna = await person(api_client, session_factory, "anna", "Anna")

    (news,) = (await api_client.get("/activity", headers=anna)).json()["items"]

    assert (news["kind"], news["count"]) == ("new_media", 7)
    assert [preview["id"] for preview in news["previews"]] == [str(m.id) for m in media[:4]]
    assert news["media"]["id"] == str(media[0].id)
    assert news["previews"][0]["preview"].startswith(f"/api/v1/media/{media[0].id}/preview?token=")


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


async def test_a_stage_that_gives_up_tells_the_admins_what_went_wrong(
    api_client: AsyncClient,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A medium nothing can be done with used to be an entry in the engine room and nowhere
    else. The admins hear of it, with the machine's own words."""
    admin = await person(api_client, session_factory, "chef", "Chef", UserRole.ADMIN)
    family = await person(api_client, session_factory, "oma", "Oma")
    medium = await a_picture(session)

    for _ in range(GIVE_UP_AFTER):
        await attempts.note_failure(session, medium.id, "faces", "ffmpeg: no frame to read")

    (entry,) = await bell(api_client, admin)
    assert entry["kind"] == "stage_failed"
    assert entry["stage"] == "faces"
    assert entry["detail"] == "ffmpeg: no frame to read"
    assert entry["media"] is not None
    # Not the family's business: they cannot act on it and would only be worried by it.
    assert await bell(api_client, family) == []


async def test_nothing_is_said_before_the_stage_gives_up(
    api_client: AsyncClient,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The first tries are the pipeline's own business: it will try again by itself."""
    admin = await person(api_client, session_factory, "chef", "Chef", UserRole.ADMIN)
    medium = await a_picture(session)

    for _ in range(GIVE_UP_AFTER - 1):
        await attempts.note_failure(session, medium.id, "faces", "ffmpeg: no frame to read")

    assert await bell(api_client, admin) == []


async def test_two_stages_on_one_medium_are_two_entries(
    api_client: AsyncClient,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Different problems with different answers: bundling them would hide one of the two."""
    admin = await person(api_client, session_factory, "chef", "Chef", UserRole.ADMIN)
    medium = await a_picture(session)

    for stage, said in (("faces", "no frame"), ("analysis", "model refused")):
        for _ in range(GIVE_UP_AFTER):
            await attempts.note_failure(session, medium.id, stage, said)

    entries = await bell(api_client, admin)
    assert {(one["stage"], one["detail"]) for one in entries} == {
        ("faces", "no frame"),
        ("analysis", "model refused"),
    }


async def _account(session: AsyncSession, username: str) -> User:
    found = await session.scalar(select(User).where(User.username == username))
    assert found is not None
    return found


async def in_one_photo(session: AsyncSession, cast: dict[str, tuple[str, str]]) -> uuid.UUID:
    """A photo with one face per person: username -> (how the face is theirs, the person's
    name). "user" and "auto" give the face to the person, "suggested" only asks about it.
    Every person is linked to that user's account. Returns the medium."""
    face_ids = await faces_in_a_photo(
        session, *(at(0.0, towards=index + 1) for index in range(len(cast)))
    )
    medium_id: uuid.UUID | None = None
    for face_id, (username, (how, name)) in zip(face_ids, cast.items(), strict=True):
        account = await _account(session, username)
        somebody = Person(name=name, user_id=account.id)
        session.add(somebody)
        await session.flush()
        face = await session.get(Face, face_id)
        assert face is not None
        medium_id = face.media_id
        if how == "suggested":
            face.suggested_person_id = somebody.id
            face.suggested_distance = 0.5
        else:
            face.person_id = somebody.id
            face.assigned_by = how
    await session.commit()
    assert medium_id is not None
    return medium_id


async def test_a_comment_on_a_photo_tells_whoever_is_in_it(
    api_client: AsyncClient,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    anna = await person(api_client, session_factory, "anna", "Anna")
    lena = await person(api_client, session_factory, "lena", "Lena")
    jonas = await person(api_client, session_factory, "jonas", "Jonas")
    mats = await person(api_client, session_factory, "mats", "Mats")
    omi = await person(api_client, session_factory, "omi", "Omi")
    medium = await in_one_photo(
        session,
        {
            "lena": ("user", "Lena"),
            "jonas": ("auto", "Jonas"),
            "mats": ("suggested", "Mats"),
            "omi": ("user", "Omi"),
            "anna": ("user", "Anna"),
        },
    )
    # Omi also keeps the photo in Walhall: she hears once, for the more personal reason.
    await api_client.post("/favorites", json={"media_id": str(medium)}, headers=omi)

    await say(api_client, anna, f"/media/{medium}", "Was für ein Tag!")

    pictured = [("pictured_comment", ["Anna"])]
    for headers in (lena, jonas, omi):
        assert [(item["kind"], item["actors"]) for item in await bell(api_client, headers)] == (
            pictured
        )
    # A suggestion nobody answered is not a face that is theirs; and Anna wrote it herself.
    assert await bell(api_client, mats) == []
    assert await bell(api_client, anna) == []


async def test_a_reaction_to_a_photo_tells_whoever_is_in_it_once(
    api_client: AsyncClient,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    anna = await person(api_client, session_factory, "anna", "Anna")
    boris = await person(api_client, session_factory, "boris", "Boris")
    lena = await person(api_client, session_factory, "lena", "Lena")
    await create_user(
        session_factory, username="opa", display_name="Opa", status=UserStatus.DISABLED
    )
    medium = await in_one_photo(session, {"lena": ("user", "Lena"), "opa": ("user", "Opa")})
    like = f"/media/{medium}/like"

    await api_client.post(like, headers=anna)
    # A heart traded for a laugh is the same reaction, not a new one.
    await api_client.post(like, json={"reaction": "joy"}, headers=anna)
    await api_client.post(like, headers=boris)
    # Lena's own reaction to a photo of her is no news to her.
    await api_client.post(like, headers=lena)

    assert [
        (item["kind"], item["actors"], item["count"]) for item in await bell(api_client, lena)
    ] == [("pictured_like", ["Boris", "Anna"], 2)]
    # A disabled account hears nothing.
    opa = await _account(session, "opa")
    told = await session.scalars(select(Notification).where(Notification.user_id == opa.id))
    assert list(told) == []
