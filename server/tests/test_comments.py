"""Comments: one level of answers, mentions, and who may change what."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from muninn.models.social import CommentMention
from muninn.models.user import User, UserRole
from tests.helpers import auth_header, create_user, login
from tests.test_social import a_picture

pytestmark = pytest.mark.usefixtures("api_client")


async def person(
    api_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    username: str,
    name: str,
    role: UserRole = UserRole.USER,
) -> dict[str, str]:
    await create_user(session_factory, username=username, display_name=name, role=role)
    return auth_header(await login(api_client, username=username))


async def say(
    api_client: AsyncClient, headers: dict[str, str], where: str, body: str, **extra: str
) -> dict[str, object]:
    response = await api_client.post(
        f"{where}/comments", json={"body": body, **extra}, headers=headers
    )
    assert response.status_code == 201, response.text
    comment: dict[str, object] = response.json()
    return comment


async def test_a_conversation_under_a_picture(
    api_client: AsyncClient,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    medium = await a_picture(session)
    anna = await person(api_client, session_factory, "anna", "Anna")
    boris = await person(api_client, session_factory, "boris", "Boris")
    where = f"/media/{medium.id}"

    question = await say(api_client, anna, where, "Wo war das?")
    answer = await say(api_client, boris, where, "In Venedig!", parent_id=str(question["id"]))
    # An answer to an answer joins the same conversation: one level only.
    await say(api_client, anna, where, "Schön!", parent_id=str(answer["id"]))

    listed = (await api_client.get(f"{where}/comments", headers=anna)).json()

    assert listed["count"] == 3
    (thread,) = listed["items"]
    assert thread["author"]["display_name"] == "Anna"
    assert [reply["body"] for reply in thread["replies"]] == ["In Venedig!", "Schön!"]
    assert thread["can_edit"] is True
    assert thread["replies"][0]["can_edit"] is False
    social = (await api_client.get(f"{where}/social", headers=anna)).json()
    assert social["comments"] == 3


async def test_a_mention_is_remembered_for_the_named_person_only(
    api_client: AsyncClient,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    medium = await a_picture(session)
    anna = await person(api_client, session_factory, "anna", "Anna")
    await person(api_client, session_factory, "boris", "Boris")

    comment = await say(
        api_client, anna, f"/media/{medium.id}", "Guck mal @Boris und @anna und @niemand"
    )

    mentioned = await session.scalars(
        select(User.username)
        .join(CommentMention, CommentMention.user_id == User.id)
        .where(CommentMention.comment_id == uuid.UUID(str(comment["id"])))
    )
    # The author does not notify herself, and nobody is invented.
    assert list(mentioned) == ["boris"]


async def test_only_the_author_changes_the_words(
    api_client: AsyncClient,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    medium = await a_picture(session)
    anna = await person(api_client, session_factory, "anna", "Anna")
    admin = await person(api_client, session_factory, "chef", "Chef", UserRole.ADMIN)
    comment = await say(api_client, anna, f"/media/{medium.id}", "Tippfehlr")

    edited = await api_client.patch(
        f"/comments/{comment['id']}", json={"body": "Tippfehler"}, headers=anna
    )
    by_admin = await api_client.patch(
        f"/comments/{comment['id']}", json={"body": "Zensiert"}, headers=admin
    )

    assert edited.json()["body"] == "Tippfehler"
    assert edited.json()["edited_at"] is not None
    assert by_admin.status_code == 403


async def test_an_admin_may_delete_any_comment_a_user_only_their_own(
    api_client: AsyncClient,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    medium = await a_picture(session)
    anna = await person(api_client, session_factory, "anna", "Anna")
    boris = await person(api_client, session_factory, "boris", "Boris")
    admin = await person(api_client, session_factory, "chef", "Chef", UserRole.ADMIN)
    comment = await say(api_client, anna, f"/media/{medium.id}", "Hallo")

    by_boris = await api_client.delete(f"/comments/{comment['id']}", headers=boris)
    by_admin = await api_client.delete(f"/comments/{comment['id']}", headers=admin)

    assert (by_boris.status_code, by_admin.status_code) == (403, 204)
    assert (await api_client.get(f"/media/{medium.id}/comments", headers=anna)).json() == {
        "items": [],
        "count": 0,
    }


async def test_an_answered_comment_keeps_its_place_when_deleted(
    api_client: AsyncClient,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    medium = await a_picture(session)
    anna = await person(api_client, session_factory, "anna", "Anna")
    boris = await person(api_client, session_factory, "boris", "Boris")
    where = f"/media/{medium.id}"
    question = await say(api_client, anna, where, "Wo war das?")
    answer = await say(api_client, boris, where, "Venedig", parent_id=str(question["id"]))

    await api_client.delete(f"/comments/{question['id']}", headers=anna)
    kept = (await api_client.get(f"{where}/comments", headers=anna)).json()

    (thread,) = kept["items"]
    assert (thread["deleted"], thread["body"], thread["can_delete"]) == (True, "", False)
    assert [reply["body"] for reply in thread["replies"]] == ["Venedig"]
    assert kept["count"] == 1

    # Its last answer gone, nothing is left to keep the place for.
    await api_client.delete(f"/comments/{answer['id']}", headers=boris)
    assert (await api_client.get(f"{where}/comments", headers=anna)).json()["items"] == []


async def test_comments_are_liked_too(
    api_client: AsyncClient,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    medium = await a_picture(session)
    anna = await person(api_client, session_factory, "anna", "Anna")
    boris = await person(api_client, session_factory, "boris", "Boris")
    comment = await say(api_client, anna, f"/media/{medium.id}", "Schönes Bild")

    liked = await api_client.post(f"/comments/{comment['id']}/like", headers=boris)
    listed = (await api_client.get(f"/media/{medium.id}/comments", headers=boris)).json()

    assert liked.json() == {"likes": 1, "liked": True}
    assert (listed["items"][0]["likes"], listed["items"][0]["liked"]) == (1, True)
    # A like on a comment is not a like on the picture.
    assert (await api_client.get(f"/media/{medium.id}/social", headers=boris)).json()["likes"] == 0


async def test_albums_have_comments_and_answers_stay_where_they_belong(
    api_client: AsyncClient,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    medium = await a_picture(session)
    other = await a_picture(session, "IMG_2.jpg")
    anna = await person(api_client, session_factory, "anna", "Anna")
    on_album = await say(api_client, anna, f"/albums/{medium.album_id}", "Tolles Album")

    elsewhere = await api_client.post(
        f"/media/{other.id}/comments",
        json={"body": "Falscher Ort", "parent_id": str(on_album["id"])},
        headers=anna,
    )
    empty = await api_client.post(f"/media/{other.id}/comments", json={"body": "   "}, headers=anna)
    nowhere = await api_client.post(
        f"/media/{uuid.uuid4()}/comments", json={"body": "Hallo"}, headers=anna
    )

    assert elsewhere.status_code == 422
    assert empty.status_code == 422
    assert nowhere.status_code == 404


async def test_everybody_active_can_be_mentioned(
    api_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    anna = await person(api_client, session_factory, "anna", "Anna")
    await person(api_client, session_factory, "boris", "Boris")

    people = (await api_client.get("/people/mentionable", headers=anna)).json()

    assert [(item["username"], item["display_name"]) for item in people] == [
        ("anna", "Anna"),
        ("boris", "Boris"),
    ]
