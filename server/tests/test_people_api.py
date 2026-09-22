"""The Personen screen's API, and the square pictures of faces."""

import uuid
from pathlib import Path

import pytest
import pyvips
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from muninn.ai.base import DetectedFace
from muninn.faces.service import CROP_PIXELS, crop
from muninn.models.face import Face
from tests.helpers import auth_header, create_user, login
from tests.test_people import at, faces_in_a_photo

pytestmark = pytest.mark.usefixtures("api_client")


@pytest.fixture(autouse=True)
def no_worker(monkeypatch: pytest.MonkeyPatch) -> list[bool]:
    """The API hands the re-check to the worker; there is none here."""
    asked: list[bool] = []
    monkeypatch.setattr("muninn.api.v1.people.queue_face_reassessment", lambda: asked.append(True))
    monkeypatch.setattr("muninn.api.v1.people.queue_face_sorting", lambda _: asked.append(True))
    return asked


async def _headers(
    api_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> dict[str, str]:
    await create_user(session_factory, username="anna", display_name="Anna")
    return auth_header(await login(api_client, username="anna"))


async def test_a_group_is_named_and_its_suggestions_answered(
    api_client: AsyncClient,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    headers = await _headers(api_client, session_factory)
    group = await faces_in_a_photo(session, at(1.0), at(0.96))
    (maybe,) = await faces_in_a_photo(session, at(0.45, towards=5))

    overview = (await api_client.get("/people", headers=headers)).json()
    assert overview["persons"] == []
    (unnamed,) = overview["groups"]["items"]
    assert unnamed["size"] == 2
    assert {face["id"] for face in unnamed["faces"]} == {str(face_id) for face_id in group}

    named = await api_client.post(
        f"/people/groups/{unnamed['cluster']}/name", json={"name": "Lena"}, headers=headers
    )
    assert named.status_code == 200
    lena = named.json()
    # The background task is not running here; ask again by hand, as it would.
    from muninn.faces import people

    await people.reassess(session)

    suggestions = (await api_client.get("/people/suggestions", headers=headers)).json()
    (suggestion,) = suggestions["items"]
    assert suggestion["face"]["id"] == str(maybe)
    assert suggestion["person"] == lena
    assert 0.38 <= suggestion["face"]["suggested_similarity"] < 0.55

    assert (await api_client.post(f"/faces/{maybe}/confirm", headers=headers)).status_code == 204
    overview = (await api_client.get("/people", headers=headers)).json()
    (person,) = overview["persons"]
    assert (person["name"], person["faces"], person["media"]) == ("Lena", 3, 2)
    assert overview["suggestions"] == 0

    photos = (await api_client.get(f"/people/{lena['id']}/media", headers=headers)).json()
    assert len(photos["items"]) == 2


async def test_the_surest_suggestion_comes_first(
    api_client: AsyncClient,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    headers = await _headers(api_client, session_factory)
    await faces_in_a_photo(session, at(1.0), at(0.96))
    # The surer face is the older one: newest first would put it last.
    (surer,) = await faces_in_a_photo(session, at(0.48, towards=5))
    (weaker,) = await faces_in_a_photo(session, at(0.40, towards=6))
    (unnamed,) = (await api_client.get("/people", headers=headers)).json()["groups"]["items"]
    await api_client.post(
        f"/people/groups/{unnamed['cluster']}/name", json={"name": "Lena"}, headers=headers
    )
    from muninn.faces import people

    await people.reassess(session)

    items = (await api_client.get("/people/suggestions", headers=headers)).json()["items"]
    assert [item["face"]["id"] for item in items] == [str(surer), str(weaker)]
    scores = [item["face"]["suggested_similarity"] for item in items]
    assert scores == sorted(scores, reverse=True)


async def test_the_faces_of_a_medium_say_who_they_are(
    api_client: AsyncClient,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    headers = await _headers(api_client, session_factory)
    first, _ = await faces_in_a_photo(session, at(1.0), at(0.0, towards=3))
    face = await session.get(Face, first)
    assert face is not None

    await api_client.post(f"/faces/{first}/name", json={"name": "Oma"}, headers=headers)
    found = (await api_client.get(f"/media/{face.media_id}/faces", headers=headers)).json()

    assert [item["person"]["name"] if item["person"] else None for item in found] == ["Oma", None]
    assert found[0]["face"]["crop"].startswith(f"/api/v1/faces/{first}/crop?token=")


async def test_persons_are_renamed_hidden_and_merged(
    api_client: AsyncClient,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    headers = await _headers(api_client, session_factory)
    (child,) = await faces_in_a_photo(session, at(1.0, towards=1))
    (grown,) = await faces_in_a_photo(session, at(0.0, towards=2))
    small = (
        await api_client.post(f"/faces/{child}/name", json={"name": "Lena Kind"}, headers=headers)
    ).json()
    big = (
        await api_client.post(f"/faces/{grown}/name", json={"name": "Lena"}, headers=headers)
    ).json()

    taken = await api_client.patch(f"/people/{small['id']}", json={"name": "lena"}, headers=headers)
    assert taken.status_code == 409
    merged = await api_client.post(
        f"/people/{small['id']}/merge", json={"into": big["id"]}, headers=headers
    )
    assert merged.json()["faces"] == 2

    hidden = await api_client.patch(f"/people/{big['id']}", json={"hidden": True}, headers=headers)
    assert hidden.json()["hidden"] is True
    assert (await api_client.get("/people", headers=headers)).json()["persons"] == []
    shown = (await api_client.get("/people", params={"hidden": True}, headers=headers)).json()
    assert [person["name"] for person in shown["persons"]] == ["Lena"]


async def test_the_crop_needs_a_token_or_an_account(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    (face_id,) = await faces_in_a_photo(session, at(1.0))

    assert (await api_client.get(f"/faces/{face_id}/crop")).status_code == 401
    assert (await api_client.get(f"/faces/{face_id}/crop?token=forged")).status_code == 401


def test_a_crop_is_a_square_around_the_face(tmp_path: Path) -> None:
    picture = (pyvips.Image.black(800, 400, bands=3) + 90).cast("uchar")
    jpeg = bytes(picture.write_to_buffer(".jpg"))
    face = DetectedFace(box=(0.45, 0.4, 0.55, 0.6), score=0.9, embedding=[1.0], pixels=80)

    square = pyvips.Image.new_from_buffer(crop(jpeg, face), "")

    assert (square.width, square.height) == (CROP_PIXELS, CROP_PIXELS)


async def test_a_search_for_two_names_finds_the_photos_of_both(
    api_client: AsyncClient,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    headers = await _headers(api_client, session_factory)
    together = await faces_in_a_photo(session, at(1.0, towards=1), at(0.0, towards=2))
    (alone,) = await faces_in_a_photo(session, at(0.99, towards=1))
    await api_client.post(f"/faces/{together[0]}/name", json={"name": "Lena"}, headers=headers)
    await api_client.post(f"/faces/{together[1]}/name", json={"name": "Oma"}, headers=headers)
    await api_client.post(f"/faces/{alone}/name", json={"name": "Lena"}, headers=headers)
    photo = await session.get(Face, together[0])
    assert photo is not None

    both = (await api_client.post("/search", json={"q": "Oma und Lena"}, headers=headers)).json()
    lena = (await api_client.post("/search", json={"q": "lena"}, headers=headers)).json()

    assert [hit["media"]["id"] for hit in both["items"]] == [str(photo.media_id)]
    assert both["understood"]["persons"] == ["Oma", "Lena"]
    assert both["understood"]["text"] == ""
    assert len(lena["items"]) == 2


async def test_switched_off_nothing_about_faces_is_shown(
    api_client: AsyncClient,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    from muninn.settings import service as settings_service

    headers = await _headers(api_client, session_factory)
    (lena,) = await faces_in_a_photo(session, at(1.0))
    await api_client.post(f"/faces/{lena}/name", json={"name": "Lena"}, headers=headers)
    face = await session.get(Face, lena)
    assert face is not None
    await settings_service.update_settings(session, faces_enabled=False)

    overview = (await api_client.get("/people", headers=headers)).json()
    found = (await api_client.get(f"/media/{face.media_id}/faces", headers=headers)).json()
    search = (await api_client.post("/search", json={"q": "Lena"}, headers=headers)).json()

    assert (overview["enabled"], overview["persons"]) == (False, [])
    assert found == []
    assert search["understood"]["persons"] == []


async def test_an_admin_deletes_every_face_and_person(
    api_client: AsyncClient,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    from sqlalchemy import func, select

    from muninn.models.face import Person
    from muninn.models.media import Media
    from muninn.models.user import UserRole

    anna = await _headers(api_client, session_factory)
    (lena,) = await faces_in_a_photo(session, at(1.0))
    await api_client.post(f"/faces/{lena}/name", json={"name": "Lena"}, headers=anna)
    face = await session.get(Face, lena)
    assert face is not None
    media = await session.get(Media, face.media_id)
    assert media is not None
    media.face_version = 1
    await session.commit()
    await create_user(session_factory, username="admin", display_name="Admin", role=UserRole.ADMIN)
    admin = auth_header(await login(api_client, username="admin"))

    assert (await api_client.delete("/admin/faces", headers=anna)).status_code == 403
    response = await api_client.delete("/admin/faces", headers=admin)

    assert response.json() == {"faces": 1, "persons": 1}
    assert await session.scalar(select(func.count()).select_from(Face)) == 0
    assert await session.scalar(select(func.count()).select_from(Person)) == 0
    await session.refresh(media)
    assert media.face_version == 0


async def test_a_person_muninn_gave_is_confirmed_and_the_faces_filtered(
    api_client: AsyncClient,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    headers = await _headers(api_client, session_factory)
    group = await faces_in_a_photo(session, at(1.0), at(0.96, towards=6))
    unnamed = (await api_client.get("/people", headers=headers)).json()["groups"]["items"][0]
    lena = (
        await api_client.post(
            f"/people/groups/{unnamed['cluster']}/name", json={"name": "Lena"}, headers=headers
        )
    ).json()
    (auto,) = await faces_in_a_photo(session, at(0.9, towards=3))

    def ids(response: dict[str, list[dict[str, str]]]) -> list[str]:
        return [face["id"] for face in response["items"]]

    faces = f"/people/{lena['id']}/faces"
    automatic = (await api_client.get(faces, params={"only": "auto"}, headers=headers)).json()
    twice = (await api_client.get(faces, params={"only": "twice"}, headers=headers)).json()
    assert ids(automatic) == [str(auto)]
    assert sorted(ids(twice)) == sorted(str(face_id) for face_id in group)

    assert (await api_client.post(f"/faces/{auto}/confirm", headers=headers)).status_code == 204
    confirmed = await session.get(Face, auto, populate_existing=True)
    assert confirmed is not None
    assert (confirmed.person_id, confirmed.assigned_by) == (uuid.UUID(lena["id"]), "user")
    automatic = (await api_client.get(faces, params={"only": "auto"}, headers=headers)).json()
    assert ids(automatic) == []


async def test_saying_no_answers_at_once_and_hands_the_sorting_over(
    api_client: AsyncClient,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = await _headers(api_client, session_factory)
    group = await faces_in_a_photo(session, at(1.0), at(0.96, towards=6))
    unnamed = (await api_client.get("/people", headers=headers)).json()["groups"]["items"][0]
    await api_client.post(
        f"/people/groups/{unnamed['cluster']}/name", json={"name": "Lena"}, headers=headers
    )
    (mistaken,) = await faces_in_a_photo(session, at(0.9, towards=3))
    handed_over: list[uuid.UUID] = []
    monkeypatch.setattr("muninn.api.v1.people.queue_face_sorting", handed_over.append)

    response = await api_client.post(f"/faces/{mistaken}/reject", headers=headers)

    assert response.status_code == 204
    assert handed_over == [mistaken]
    refused = await session.get(Face, mistaken, populate_existing=True)
    assert refused is not None
    assert refused.person_id is None
    assert len(group) == 2
