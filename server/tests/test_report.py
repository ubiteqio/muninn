"""Überblick: the library at a glance, the same for everybody."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from muninn.analysis import service as analysis_service
from muninn.faces import people
from muninn.models.face import Face
from muninn.models.user import User, UserRole
from tests.helpers import auth_header, create_user, login
from tests.test_people import at, faces_in_a_photo
from tests.test_search import described
from tests.test_timeline import JULY, a_medium, an_album

pytestmark = pytest.mark.usefixtures("api_client")


async def test_the_report_counts_what_the_albums_show(
    api_client: AsyncClient,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    album = await an_album(session, "Urlaub")
    photo = await a_medium(session, album, taken_at=JULY, name="a.jpg")
    photo.derived_bytes = 1500
    await analysis_service.store(
        session, photo.id, model="qwen", analysis=described("Ein Strand.", "strand", "meer")
    )
    await session.commit()
    face_ids = await faces_in_a_photo(session, at(1.0), at(0.97))
    await create_user(session_factory, username="admin", display_name="Admin", role=UserRole.ADMIN)
    admin = await session.scalar(select(User).where(User.username == "admin"))
    assert admin is not None
    face = await session.get(Face, face_ids[0])
    assert face is not None
    assert face.cluster is not None
    await people.name_group(session, face.cluster, "Lena", admin)
    headers = auth_header(await login(api_client, username="admin"))

    report = (await api_client.get("/overview", headers=headers)).json()

    assert report["totals"]["media"] == 2
    assert report["totals"]["photos"] == 2
    # The previews beside the originals; a medium without them adds nothing.
    assert report["totals"]["derived_bytes"] == 1500
    assert report["years"] == [{"year": 2009, "photos": 2, "videos": 0}]
    descriptions = next(step for step in report["pipeline"] if step["step"] == "descriptions")
    assert (descriptions["done"], descriptions["of"]) == (1, 2)
    assert {tag["name"] for tag in report["tags"]} == {"strand", "meer"}
    assert report["people"]["named"] == 2
    assert [(person["name"], person["media"]) for person in report["persons"]] == [("Lena", 1)]
    assert report["persons"][0]["crop"].startswith("/api/v1/faces/")


async def test_everybody_sees_the_same_overview(
    api_client: AsyncClient,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await a_medium(session, await an_album(session, "Urlaub"), taken_at=JULY, name="a.jpg")
    await session.commit()
    await create_user(session_factory, username="anna", display_name="Anna")
    headers = auth_header(await login(api_client, username="anna"))

    overview = (await api_client.get("/overview", headers=headers)).json()

    assert overview["totals"]["media"] == 1
    assert overview["pipeline"] is not None
    assert overview["duplicates"]["groups"] == 0
    assert overview["date_sources"] == [{"name": "unknown", "count": 1}]
    assert overview["social"]["users"] == 1


async def test_the_overview_needs_an_account(api_client: AsyncClient) -> None:
    assert (await api_client.get("/overview")).status_code == 401
