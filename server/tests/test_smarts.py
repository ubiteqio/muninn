"""Smarts: what the library falls into when nobody sorted it."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from muninn.ai import service as ai_service
from muninn.analysis import service as analysis_service
from muninn.models.ai import AiKind
from muninn.models.album import Album
from muninn.models.face import Face, Person
from muninn.models.media import Media
from muninn.models.place import Place
from muninn.models.smart import KIND_DAY, KIND_TRIP
from muninn.models.user import UserRole
from muninn.search.service import FaceToStore, VectorKind, store
from muninn.search.service import store_faces as search_store_faces
from muninn.smarts import kinds as rules
from muninn.smarts import service
from tests.helpers import auth_header, create_user, login
from tests.test_search import described
from tests.test_timeline import a_medium, an_album

pytestmark = pytest.mark.usefixtures("api_client")

HOME = datetime(2018, 3, 24, 12, 0, tzinfo=UTC)


async def a_place(session: AsyncSession, geoname_id: int, name: str) -> Place:
    place = Place(
        id=geoname_id,
        name=name,
        country_code="DE",
        latitude=48.0,
        longitude=11.0,
        population=1000,
        keys=[name.lower()],
    )
    session.add(place)
    await session.flush()
    return place


async def a_picture(
    session: AsyncSession,
    album: Album,
    name: str,
    *,
    taken_at: datetime,
    place: Place | None = None,
    tag: str = "bild",
    vector: list[float] | None = None,
) -> Media:
    medium = await a_medium(session, album, taken_at=taken_at, name=name)
    if place is not None:
        medium.place_id = place.id
    await analysis_service.store(
        session, medium.id, model="qwen", analysis=described(f"Ein Bild von {tag}.", tag)
    )
    if vector is not None:
        await store(
            session,
            VectorKind.IMAGE,
            media_id=medium.id,
            model="siglip2",
            version=1,
            vector=vector,
        )
    return medium


async def a_profile(session: AsyncSession) -> None:
    await ai_service.create_profile(
        session, kind=AiKind.IMAGE_EMBEDDER, name="GPU", base_url="http://gpu/v1", model="siglip2"
    )


class TestTrips:
    async def test_days_in_a_row_away_from_home_are_a_journey(self, session: AsyncSession) -> None:
        album = await an_album(session, "Fotos")
        home = await a_place(session, 1, "Pullach")
        away = await a_place(session, 2, "Chessy")
        # Home is where most pictures were taken.
        for index in range(40):
            await a_picture(session, album, f"home-{index}.jpg", taken_at=HOME, place=home)
        for day in range(4):
            for index in range(6):
                await a_picture(
                    session,
                    album,
                    f"trip-{day}-{index}.jpg",
                    taken_at=datetime(2016, 10, 30, 10, tzinfo=UTC) + timedelta(days=day),
                    place=away,
                )
        await session.commit()

        journeys = await rules.trips(session, home=await rules.home_place(session))

        assert len(journeys) == 1
        assert journeys[0].title_args["place"] == "Chessy"
        assert journeys[0].title_args["days"] == 4
        assert len(journeys[0].media) == 24

    async def test_an_afternoon_out_is_not_a_journey(self, session: AsyncSession) -> None:
        album = await an_album(session, "Fotos")
        home = await a_place(session, 1, "Pullach")
        away = await a_place(session, 2, "München")
        for index in range(40):
            await a_picture(session, album, f"home-{index}.jpg", taken_at=HOME, place=home)
        for index in range(20):
            await a_picture(
                session, album, f"out-{index}.jpg", taken_at=HOME + timedelta(hours=2), place=away
            )
        await session.commit()

        assert await rules.trips(session, home=await rules.home_place(session)) == []

    async def test_a_journey_takes_the_pictures_without_a_place_with_it(
        self, session: AsyncSession
    ) -> None:
        """A phone knows where it was; a camera does not, and both were on the same trip."""
        album = await an_album(session, "Fotos")
        away = await a_place(session, 2, "Gázi")
        for day in range(3):
            when = datetime(2018, 8, 25, 10, tzinfo=UTC) + timedelta(days=day)
            for index in range(6):
                await a_picture(session, album, f"gps-{day}-{index}.jpg", taken_at=when, place=away)
            await a_picture(session, album, f"cam-{day}.jpg", taken_at=when + timedelta(hours=1))
        await session.commit()

        journeys = await rules.trips(session, home=None)

        assert len(journeys) == 1
        assert len(journeys[0].media) == 21


class TestDays:
    async def test_a_day_with_far_more_pictures_than_usual_is_its_own_chapter(
        self, session: AsyncSession
    ) -> None:
        album = await an_album(session, "Fotos")
        for index in range(45):
            await a_picture(
                session, album, f"fest-{index}.jpg", taken_at=datetime(2016, 5, 3, 14, tzinfo=UTC)
            )
        await session.commit()

        found = await rules.days(session)

        assert len(found) == 1
        assert found[0].title_args["day"] == "2016-05-03"
        assert len(found[0].media) == 45

    async def test_the_days_a_journey_already_tells_about_are_left_alone(
        self, session: AsyncSession
    ) -> None:
        album = await an_album(session, "Fotos")
        away = await a_place(session, 2, "Chessy")
        when = datetime(2016, 10, 30, 10, tzinfo=UTC)
        for day in range(2):
            for index in range(45):
                await a_picture(
                    session,
                    album,
                    f"trip-{day}-{index}.jpg",
                    taken_at=when + timedelta(days=day),
                    place=away,
                )
        await session.commit()
        journeys = await rules.trips(session, home=None)

        alone = await rules.days(session)
        with_trip = await rules.days(session, taken=service._days_of(journeys))

        assert len(alone) == 2
        assert with_trip == []


class TestPlaces:
    async def test_a_town_one_keeps_coming_back_to(self, session: AsyncSession) -> None:
        album = await an_album(session, "Fotos")
        town = await a_place(session, 3, "Köln")
        for day in range(4):
            for index in range(12):
                await a_picture(
                    session,
                    album,
                    f"koeln-{day}-{index}.jpg",
                    taken_at=datetime(2016 + day, 5, 9, 12, tzinfo=UTC),
                    place=town,
                )
        await session.commit()

        found = await rules.places(session)

        assert len(found) == 1
        assert found[0].title_args == {"place": "Köln", "from": 2016, "until": 2019}


class TestPersons:
    async def test_somebody_in_one_year(self, session: AsyncSession) -> None:
        album = await an_album(session, "Fotos")
        person = Person(name="Matteo")
        session.add(person)
        await session.flush()
        for index in range(35):
            medium = await a_picture(
                session, album, f"matteo-{index}.jpg", taken_at=datetime(2019, 7, 1, tzinfo=UTC)
            )
            (face_id,) = await search_store_faces(
                session,
                medium.id,
                model="insightface",
                faces=[
                    FaceToStore(
                        box=(0.1, 0.1, 0.4, 0.4),
                        score=0.99,
                        pixels=10_000,
                        second=None,
                        embedding=[0.1] * 8,
                    )
                ],
            )
            face = await session.get(Face, face_id)
            assert face is not None
            face.person_id = person.id
        await session.commit()

        found = await rules.persons(session)

        assert [one.title_args for one in found] == [{"name": "Matteo", "year": 2019}]


class TestMotifs:
    async def test_what_looks_alike_across_the_whole_library(self, session: AsyncSession) -> None:
        await a_profile(session)
        first = await an_album(session, "Ordner A")
        second = await an_album(session, "Ordner B")
        # Two things, each in both folders: the chapters must not care about folders.
        for index in range(10):
            await a_picture(
                session,
                first if index % 2 else second,
                f"katze-{index}.jpg",
                taken_at=HOME,
                tag="katze",
                vector=[1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, index * 0.001],
            )
        for index in range(10):
            await a_picture(
                session,
                first if index % 2 else second,
                f"auto-{index}.jpg",
                taken_at=HOME,
                tag="auto",
                vector=[0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, index * 0.001],
            )
        await session.commit()

        found = await rules.motifs(session, model="siglip2", distance=0.24, wanted=10, attempts=50)

        assert len(found) == 2
        assert {one.title_args["words"] for one in found} == {"Katze", "Auto"}
        assert all(len(one.media) == 10 for one in found)

    async def test_a_picture_lands_in_one_motif_only(self, session: AsyncSession) -> None:
        await a_profile(session)
        album = await an_album(session, "Fotos")
        for index in range(12):
            await a_picture(
                session,
                album,
                f"gleich-{index}.jpg",
                taken_at=HOME,
                tag="katze",
                vector=[1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, index * 0.001],
            )
        await session.commit()

        found = await rules.motifs(session, model="siglip2", distance=0.24, wanted=5, attempts=30)

        placed = [one for candidate in found for one in candidate.media]
        assert len(placed) == len(set(placed))


class TestRebuilding:
    async def test_the_kinds_take_turns_on_the_screen(self, session: AsyncSession) -> None:
        """A journey, then a day, then a motif: a wall of one kind is a report, not a browse."""
        album = await an_album(session, "Fotos")
        away = await a_place(session, 2, "Chessy")
        for day in range(3):
            for index in range(20):
                await a_picture(
                    session,
                    album,
                    f"trip-{day}-{index}.jpg",
                    taken_at=datetime(2016, 10, 30, 10, tzinfo=UTC) + timedelta(days=day),
                    place=away,
                )
        for index in range(45):
            await a_picture(
                session, album, f"fest-{index}.jpg", taken_at=datetime(2019, 5, 3, 14, tzinfo=UTC)
            )
        await session.commit()

        done = await service.rebuild(session)

        assert done.by_kind[KIND_TRIP] == 1
        assert done.by_kind[KIND_DAY] == 1
        chapters = await service.chapters_of(session)
        assert [one.kind for one in chapters[:2]] == [KIND_TRIP, KIND_DAY]

    async def test_a_chapter_holds_no_more_than_the_cap(self, session: AsyncSession) -> None:
        album = await an_album(session, "Fotos")
        for index in range(120):
            await a_picture(
                session, album, f"fest-{index}.jpg", taken_at=datetime(2019, 5, 3, 14, tzinfo=UTC)
            )
        await session.commit()

        done = await service.rebuild(session, max_media=50)

        assert done.media == 50
        chapters = await service.chapters_of(session)
        assert chapters[0].size == 50
        assert len(await service.media_of(session, chapters[0].id, limit=200)) == 50

    async def test_a_run_replaces_what_was_there(self, session: AsyncSession) -> None:
        album = await an_album(session, "Fotos")
        for index in range(45):
            await a_picture(
                session, album, f"fest-{index}.jpg", taken_at=datetime(2019, 5, 3, 14, tzinfo=UTC)
            )
        await session.commit()

        first = await service.rebuild(session)
        again = await service.rebuild(session)

        assert first.chapters == again.chapters
        assert (await service.state(session)).chapters == again.chapters

    async def test_a_chapter_says_how_many_folders_it_draws_from(
        self, session: AsyncSession
    ) -> None:
        one = await an_album(session, "Ordner A")
        other = await an_album(session, "Ordner B")
        for index in range(45):
            await a_picture(
                session,
                one if index % 2 else other,
                f"fest-{index}.jpg",
                taken_at=datetime(2019, 5, 3, 14, tzinfo=UTC),
            )
        await session.commit()

        await service.rebuild(session)

        chapters = await service.chapters_of(session)
        assert chapters[0].albums == 2
        assert chapters[0].album_id is None


async def test_the_api_hands_out_the_chapters_with_their_names(
    api_client: AsyncClient,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    album = await an_album(session, "Fotos")
    away = await a_place(session, 2, "Chessy")
    for day in range(3):
        for index in range(20):
            await a_picture(
                session,
                album,
                f"trip-{day}-{index}.jpg",
                taken_at=datetime(2016, 10, 30, 10, tzinfo=UTC) + timedelta(days=day),
                place=away,
            )
    await session.commit()
    await service.rebuild(session)
    await create_user(session_factory, username="anna", display_name="Anna")
    headers = auth_header(await login(api_client, username="anna"))

    body = (await api_client.get("/smarts", headers=headers)).json()

    (chapter, *_) = body["chapters"]
    assert chapter["kind"] == KIND_TRIP
    assert chapter["title_key"] == "trip"
    assert chapter["title_args"]["place"] == "Chessy"
    assert chapter["title_args"]["days"] == 3
    assert chapter["albums"] == 1
    assert len(chapter["cover"]) == 6

    opened = (await api_client.get(f"/smarts/chapters/{chapter['id']}", headers=headers)).json()
    assert len(opened["items"]) == 60
    assert opened["chapter"]["title_key"] == "trip"


async def test_the_button_builds_and_says_what_came_of_it(
    api_client: AsyncClient,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    album = await an_album(session, "Fotos")
    for index in range(45):
        await a_picture(
            session, album, f"fest-{index}.jpg", taken_at=datetime(2019, 5, 3, 14, tzinfo=UTC)
        )
    await session.commit()
    await create_user(session_factory, username="chef", display_name="Chef", role=UserRole.ADMIN)
    headers = auth_header(await login(api_client, username="chef"))

    answer = (
        await api_client.post(
            "/smarts/build", json={"chapters": 21, "max_media": 30}, headers=headers
        )
    ).json()

    assert answer["chapters"] == 1
    assert answer["media"] == 30
    assert answer["by_kind"] == {KIND_DAY: 1}

    state = (await api_client.get("/smarts/state", headers=headers)).json()
    assert state["chapters"] == 1
    assert state["media"] == 30
    assert state["wanted"] == 21
    assert state["max_media"] == 500


async def test_only_an_admin_may_build_or_read_the_state(
    api_client: AsyncClient,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await create_user(session_factory, username="anna", display_name="Anna")
    headers = auth_header(await login(api_client, username="anna"))

    assert (await api_client.get("/smarts/state", headers=headers)).status_code == 403
    assert (
        await api_client.post("/smarts/build", json={"chapters": 5}, headers=headers)
    ).status_code == 403


async def test_a_chapter_that_is_gone_says_so(
    api_client: AsyncClient,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await create_user(session_factory, username="anna", display_name="Anna")
    headers = auth_header(await login(api_client, username="anna"))

    answer = await api_client.get(f"/smarts/chapters/{uuid.uuid4()}", headers=headers)

    assert answer.status_code == 404
    assert answer.json()["type"].endswith("chapter-not-found")


async def test_a_shelf_hands_out_what_stands_on_it(
    api_client: AsyncClient,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The count on the pill and the list behind it come from the same condition."""
    album = await an_album(session, "Fotos")
    for index in range(8):
        medium = await a_picture(session, album, f"doc-{index}.jpg", taken_at=HOME)
        analysis = described("Ein Beleg.", "beleg").model_copy(
            update={"is_document": True, "people_count": 3}
        )
        await analysis_service.store(session, medium.id, model="qwen", analysis=analysis)
    await session.commit()
    await create_user(session_factory, username="anna", display_name="Anna")
    headers = auth_header(await login(api_client, username="anna"))

    shelves = (await api_client.get("/smarts", headers=headers)).json()["shelves"]
    counted = {shelf["key"]: shelf["count"] for shelf in shelves}

    assert counted == {"people": 8, "document": 8}
    for key, count in counted.items():
        listed = (await api_client.get(f"/smarts/shelves/{key}", headers=headers)).json()
        assert len(listed["items"]) == count, key


async def test_a_shelf_nobody_has_says_so(
    api_client: AsyncClient,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await create_user(session_factory, username="anna", display_name="Anna")
    headers = auth_header(await login(api_client, username="anna"))

    answer = await api_client.get("/smarts/shelves/quatsch", headers=headers)

    assert answer.status_code == 404
    assert answer.json()["type"].endswith("shelf-not-found")
