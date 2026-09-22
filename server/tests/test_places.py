"""Midgard: clusters that dissolve when zooming in, and the media of a part of the map."""

from datetime import timedelta
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from muninn.models.media import Media, MediaStatus
from muninn.models.place import Place
from muninn.places import gazetteer
from muninn.places import service as places_service
from tests.helpers import auth_header, create_user, login
from tests.test_timeline import JULY, a_medium, an_album

pytestmark = pytest.mark.usefixtures("api_client")

EUROPE = {"west": -15.0, "south": 34.0, "east": 40.0, "north": 72.0}
#: Two pictures a few hundred metres apart in Florence, one in Hamburg.
DUOMO = (43.7731, 11.2560)
PONTE_VECCHIO = (43.7680, 11.2531)
HAMBURG = (53.5511, 9.9937)


async def _placed(
    session: AsyncSession,
    where: tuple[float, float] | None,
    *,
    days: int = 0,
    status: MediaStatus = MediaStatus.ACTIVE,
) -> Media:
    album = await an_album(session, f"Reise-{days}-{status.value}-{where}")
    medium = await a_medium(
        session, album, taken_at=JULY + timedelta(days=days), name="IMG.jpg", status=status
    )
    if where is not None:
        medium.latitude, medium.longitude = where
    await session.commit()
    return medium


async def _headers(
    api_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> dict[str, str]:
    await create_user(session_factory, username="anna", display_name="Anna")
    return auth_header(await login(api_client, username="anna"))


async def test_close_pictures_are_one_cluster_far_out_and_apart_close_in(
    api_client: AsyncClient,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    duomo = await _placed(session, DUOMO, days=2)
    await _placed(session, PONTE_VECCHIO, days=1)
    hamburg = await _placed(session, HAMBURG)
    await _placed(session, None)
    await _placed(session, HAMBURG, status=MediaStatus.MISSING)
    headers = await _headers(api_client, session_factory)

    far = (
        await api_client.get("/map/clusters", params={**EUROPE, "zoom": 4}, headers=headers)
    ).json()["items"]
    near = (
        await api_client.get("/map/clusters", params={**EUROPE, "zoom": 17}, headers=headers)
    ).json()["items"]

    assert sorted(cluster["count"] for cluster in far) == [1, 2]
    florence = next(cluster for cluster in far if cluster["count"] == 2)
    # The newest picture stands for the cluster, and the box spans both.
    assert florence["cover_id"] == str(duomo.id)
    assert florence["bounds"]["south"] == pytest.approx(PONTE_VECCHIO[0])
    assert florence["bounds"]["north"] == pytest.approx(DUOMO[0])
    alone = next(cluster for cluster in far if cluster["count"] == 1)
    assert alone["cover_id"] == str(hamburg.id)
    assert (alone["latitude"], alone["longitude"]) == pytest.approx(HAMBURG)
    assert [cluster["count"] for cluster in near] == [1, 1, 1]


async def test_only_the_visible_part_is_asked_for(
    api_client: AsyncClient,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _placed(session, DUOMO)
    await _placed(session, HAMBURG)
    headers = await _headers(api_client, session_factory)
    italy = {"west": 6.0, "south": 36.0, "east": 19.0, "north": 47.0}

    found = (
        await api_client.get("/map/clusters", params={**italy, "zoom": 6}, headers=headers)
    ).json()["items"]

    assert [cluster["count"] for cluster in found] == [1]


async def test_the_media_of_a_part_come_newest_first_page_by_page(
    api_client: AsyncClient,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    older = await _placed(session, PONTE_VECCHIO, days=1)
    newer = await _placed(session, DUOMO, days=2)
    await _placed(session, HAMBURG, days=3)
    headers = await _headers(api_client, session_factory)
    florence = {"west": 11.2, "south": 43.7, "east": 11.3, "north": 43.8}

    first = (
        await api_client.get("/map/media", params={**florence, "limit": 1}, headers=headers)
    ).json()
    second = (
        await api_client.get(
            "/map/media",
            params={**florence, "limit": 1, "cursor": first["next_cursor"]},
            headers=headers,
        )
    ).json()

    assert [item["id"] for item in first["items"]] == [str(newer.id)]
    assert [item["id"] for item in second["items"]] == [str(older.id)]
    assert second["next_cursor"] is None


async def test_an_upside_down_area_is_refused(
    api_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    headers = await _headers(api_client, session_factory)

    response = await api_client.get(
        "/map/clusters",
        params={"west": 20, "south": 30, "east": 10, "north": 40, "zoom": 3},
        headers=headers,
    )

    assert response.status_code == 422


async def test_the_map_needs_an_account(api_client: AsyncClient) -> None:
    response = await api_client.get("/map/clusters", params={**EUROPE, "zoom": 3})

    assert response.status_code == 401


# --- the gazetteer -----------------------------------------------------------------------------


def _tsv(path: Path, rows: list[list[object]]) -> None:
    path.write_text("".join("\t".join(str(cell) for cell in row) + "\n" for row in rows))


def _city(
    geoname: int, name: str, alternates: str, lat: float, lon: float, **extra: str
) -> list[object]:
    feature = extra.get("feature", "PPLA")
    return [geoname, name, name, alternates, lat, lon, "P", feature, "IT", "", "16", "", "", "",
            extra.get("population", "360000"), "", "", "Europe/Rome", "2024-01-01"]  # fmt: skip


def test_the_gazetteer_names_places_in_german_and_knows_them_in_every_language(
    tmp_path: Path,
) -> None:
    _tsv(
        tmp_path / "countryInfo.txt",
        [["#ISO"], ["IT", "ITA", "380", "IT", "Italy", "Rome", "1", "1", "EU", ".it", "EUR",
                    "Euro", "39", "", "", "it-IT", 3175395]],
    )  # fmt: skip
    _tsv(tmp_path / "admin1CodesASCII.txt", [["IT.16", "Tuscany", "Tuscany", 3165361]])
    _tsv(
        tmp_path / "cities1000.txt",
        [
            _city(3176959, "Florence", "Firenze,Florenz,Флоренция", *DUOMO),
            _city(6545158, "Oltrarno", "", *PONTE_VECCHIO, feature="PPLX"),
        ],
    )
    _tsv(
        tmp_path / "alternateNamesV2.txt",
        [
            [1, 3176959, "de", "Florenz", "1", "", "", ""],
            [2, 3165361, "de", "Toskana", "", "", "", ""],
            [3, 3175395, "de", "Italienische Republik", "1", "", "", ""],
            [4, 3175395, "de", "Italien", "", "1", "", ""],
            [5, 3175395, "de", "Welschland", "", "1", "", "1"],
        ],
    )

    places = list(gazetteer.prepare(tmp_path))

    # Parts of a town are no places of their own.
    assert [place.name for place in places] == ["Florenz"]
    (florence,) = places
    assert (florence.region, florence.country) == ("Toskana", "Italien")
    assert {"florence", "firenze", "florenz", "toskana", "tuscany", "italien", "italy"} <= set(
        florence.keys
    )
    assert "флоренция" not in florence.keys
    # Written and read back, nothing is lost.
    gazetteer.write(places, tmp_path / "places.tsv.gz")
    assert list(gazetteer.read(tmp_path / "places.tsv.gz")) == places


FLORENCE = Place(
    id=3176959,
    name="Florenz",
    region="Toskana",
    country="Italien",
    country_code="IT",
    population=367150,
    latitude=43.77925,
    longitude=11.24626,
    keys=["firenze", "florence", "florenz", "italien", "italy", "toskana", "tuscany"],
)
HAMBURG_PLACE = Place(
    id=2911298,
    name="Hamburg",
    region="Hamburg",
    country="Deutschland",
    country_code="DE",
    population=1973896,
    latitude=53.55073,
    longitude=9.99302,
    keys=["deutschland", "germany", "hamburg"],
)


async def _with_places(session: AsyncSession) -> None:
    session.add_all(
        [
            Place(**{column: getattr(place, column) for column in COLUMNS})
            for place in (FLORENCE, HAMBURG_PLACE)
        ]
    )
    await session.commit()


COLUMNS = (
    "id",
    "name",
    "region",
    "country",
    "country_code",
    "population",
    "latitude",
    "longitude",
    "keys",
)


async def test_media_are_placed_in_the_nearest_town_and_again_when_they_move(
    session: AsyncSession,
) -> None:
    await _with_places(session)
    florence = await _placed(session, DUOMO)
    at_sea = await _placed(session, (40.0, 5.0), days=1)
    nowhere = await _placed(session, None, days=2)

    placed = await places_service.place_media(session)

    # The one without coordinates is looked at too: its album has no place to lend.
    assert placed == 3
    await session.refresh(florence)
    await session.refresh(at_sea)
    await session.refresh(nowhere)
    assert florence.place_id == FLORENCE.id
    assert at_sea.place_id is None
    assert (nowhere.place_id, nowhere.place_version) == (None, gazetteer.GAZETTEER_VERSION)
    # Nothing is left to do until something moves.
    assert await places_service.place_media(session) == 0

    florence.latitude, florence.longitude = HAMBURG
    await session.commit()
    assert await places_service.place_media(session) == 1
    await session.refresh(florence)
    assert florence.place_id == HAMBURG_PLACE.id

    florence.latitude = florence.longitude = None
    await session.commit()
    assert await places_service.place_media(session) == 1
    await session.refresh(florence)
    assert florence.place_id is None


async def test_places_are_taken_out_of_the_words_only_where_the_library_has_photos(
    session: AsyncSession,
) -> None:
    await _with_places(session)
    await _placed(session, DUOMO)
    await places_service.place_media(session)

    tuscany = await places_service.places_in(session, "Hund in Toskana")
    hamburg = await places_service.places_in(session, "Hafen Hamburg")

    assert (tuscany.text, tuscany.phrases, tuscany.keys) == ("Hund", ("Toskana",), ("toskana",))
    # Hamburg is a place, but there are no photos from there: the word stays a word.
    assert (hamburg.text, hamburg.phrases) == ("Hafen Hamburg", ())


async def test_a_search_for_a_place_finds_the_photos_from_there_and_says_so(
    api_client: AsyncClient,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _with_places(session)
    florence = await _placed(session, DUOMO)
    await _placed(session, HAMBURG, days=1)
    await places_service.place_media(session)
    headers = await _headers(api_client, session_factory)

    found = (await api_client.post("/search", json={"q": "Italien"}, headers=headers)).json()
    detail = (await api_client.get(f"/media/{florence.id}", headers=headers)).json()

    assert [hit["media"]["id"] for hit in found["items"]] == [str(florence.id)]
    assert found["understood"]["places"] == ["Italien"]
    assert found["understood"]["text"] == ""
    assert detail["place"] == {
        "id": FLORENCE.id,
        "name": "Florenz",
        "region": "Toskana",
        "country": "Italien",
        "estimated": False,
    }


async def test_the_places_are_loaded_once_from_the_prepared_file(
    session: AsyncSession, tmp_path: Path
) -> None:
    source = tmp_path / "places.tsv.gz"
    gazetteer.write(
        [
            gazetteer.Place(
                **{column: getattr(FLORENCE, column) for column in COLUMNS[:-1]},
                keys=tuple(FLORENCE.keys),
            )
        ],
        source,
    )

    assert await places_service.load_gazetteer(session, tmp_path / "missing.tsv.gz") == 0
    assert await places_service.load_gazetteer(session, source) == 1
    assert await places_service.load_gazetteer(session, source) == 0
    loaded = await session.get(Place, FLORENCE.id)
    assert loaded is not None
    assert loaded.keys == FLORENCE.keys


async def test_an_albums_place_goes_to_its_media_without_coordinates_and_below(
    api_client: AsyncClient,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _with_places(session)
    trip = await an_album(session, "Italien 1999")
    day = await an_album(session, "Italien 1999/Tag 1")
    elsewhere = await an_album(session, "Italien 1999/Hamburg")
    scanned = await a_medium(session, trip, taken_at=JULY, name="scan.jpg")
    later = await a_medium(session, day, taken_at=JULY, name="tag1.jpg")
    own = await a_medium(session, elsewhere, taken_at=JULY, name="hh.jpg")
    with_gps = await a_medium(session, trip, taken_at=JULY, name="gps.jpg")
    with_gps.latitude, with_gps.longitude = HAMBURG
    elsewhere.place_id = HAMBURG_PLACE.id
    await session.commit()
    headers = await _headers(api_client, session_factory)

    response = await api_client.put(
        f"/albums/{trip.id}/place", json={"place_id": FLORENCE.id}, headers=headers
    )

    assert response.status_code == 200
    assert response.json()["place"]["name"] == "Florenz"
    places = {
        medium.id: (medium.place_id, medium.place_estimated)
        for medium in await session.scalars(select(Media).execution_options(populate_existing=True))
    }
    assert places[scanned.id] == (FLORENCE.id, True)
    assert places[later.id] == (FLORENCE.id, True)
    # A place of its own below wins, and coordinates always do.
    assert places[own.id] == (HAMBURG_PLACE.id, True)
    assert places[with_gps.id] == (HAMBURG_PLACE.id, False)

    detail = (await api_client.get(f"/media/{scanned.id}", headers=headers)).json()
    assert detail["place"]["estimated"] is True
    # On the map they stand where Florence is.
    florence = {"west": 11.2, "south": 43.7, "east": 11.3, "north": 43.8}
    found = (
        await api_client.get("/map/clusters", params={**florence, "zoom": 12}, headers=headers)
    ).json()["items"]
    assert [cluster["count"] for cluster in found] == [2]
    listed = (await api_client.get("/map/media", params=florence, headers=headers)).json()
    assert {item["id"] for item in listed["items"]} == {str(scanned.id), str(later.id)}

    await api_client.put(f"/albums/{trip.id}/place", json={"place_id": None}, headers=headers)
    cleared = await session.get(Media, scanned.id, populate_existing=True)
    assert cleared is not None
    assert (cleared.place_id, cleared.place_estimated) == (None, False)


async def test_an_unknown_place_is_refused(
    api_client: AsyncClient,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    album = await an_album(session, "Irgendwo")
    await session.commit()
    headers = await _headers(api_client, session_factory)

    response = await api_client.put(
        f"/albums/{album.id}/place", json={"place_id": 42}, headers=headers
    )

    assert response.status_code == 422


async def test_places_are_suggested_by_the_start_of_their_name_or_any_full_name(
    api_client: AsyncClient,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _with_places(session)
    headers = await _headers(api_client, session_factory)

    async def names(q: str) -> list[str]:
        response = await api_client.get("/places", params={"q": q}, headers=headers)
        return [place["name"] for place in response.json()["items"]]

    assert await names("flo") == ["Florenz"]
    assert await names("Firenze") == ["Florenz"]
    assert await names("ha") == ["Hamburg"]
    assert await names("100%") == []
    assert await names("  ") == []
