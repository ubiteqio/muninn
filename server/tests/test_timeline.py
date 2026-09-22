"""The timeline: every medium of the library in one run, newest first."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from muninn.models.album import Album
from muninn.models.media import Media, MediaFile, MediaFileRole, MediaKind, MediaStatus
from tests.helpers import auth_header, create_user, login

pytestmark = pytest.mark.usefixtures("api_client")

JULY = datetime(2009, 7, 14, 15, 30, tzinfo=UTC)


async def an_album(session: AsyncSession, path: str) -> Album:
    album = Album(relative_path=path, name=path.rsplit("/", 1)[-1], is_source=True)
    session.add(album)
    await session.flush()
    return album


async def a_medium(
    session: AsyncSession,
    album: Album,
    *,
    taken_at: datetime | None,
    name: str,
    status: MediaStatus = MediaStatus.ACTIVE,
) -> Media:
    content_hash = uuid.uuid4().hex * 2
    media = Media(
        album_id=album.id,
        kind=MediaKind.IMAGE,
        status=status,
        taken_at=taken_at,
        content_hash=content_hash[:64],
    )
    media.files.append(
        MediaFile(
            role=MediaFileRole.PRIMARY,
            relative_path=f"{album.relative_path}/{name}",
            filename=name,
            content_hash=content_hash[:64],
            byte_size=1024,
            modified_at=taken_at or JULY,
        )
    )
    session.add(media)
    await session.flush()
    return media


async def a_library(session: AsyncSession) -> list[Media]:
    """Five media in two albums, a month apart, newest last in this list."""
    italy = await an_album(session, "2009 Italien")
    cars = await an_album(session, "Autos")

    media = [
        await a_medium(session, italy, taken_at=JULY, name="IMG_1.jpg"),
        await a_medium(session, italy, taken_at=JULY + timedelta(days=1), name="IMG_2.jpg"),
        await a_medium(session, cars, taken_at=JULY + timedelta(days=40), name="IMG_3.jpg"),
        await a_medium(session, cars, taken_at=JULY + timedelta(days=41), name="IMG_4.jpg"),
        await a_medium(session, cars, taken_at=JULY + timedelta(days=400), name="IMG_5.jpg"),
    ]
    await session.commit()
    return media


async def headers(
    api_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> dict[str, str]:
    await create_user(session_factory, username="anna", display_name="Anna")
    return auth_header(await login(api_client, username="anna"))


class TestWalking:
    async def test_it_runs_across_albums_newest_first(
        self,
        api_client: AsyncClient,
        session: AsyncSession,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        await a_library(session)
        head = await headers(api_client, session_factory)

        body = (await api_client.get("/media", headers=head)).json()

        assert [item["origin"]["filename"] for item in body["items"]] == [
            "IMG_5.jpg",
            "IMG_4.jpg",
            "IMG_3.jpg",
            "IMG_2.jpg",
            "IMG_1.jpg",
        ]
        assert body["next_cursor"] is None
        assert body["prev_cursor"] is None

    async def test_a_cursor_walks_on_into_the_past_and_back_again(
        self,
        api_client: AsyncClient,
        session: AsyncSession,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        await a_library(session)
        head = await headers(api_client, session_factory)

        first = (await api_client.get("/media?limit=2", headers=head)).json()
        second = (
            await api_client.get(f"/media?limit=2&cursor={first['next_cursor']}", headers=head)
        ).json()
        back = (
            await api_client.get(f"/media?limit=2&before={second['prev_cursor']}", headers=head)
        ).json()

        assert [item["origin"]["filename"] for item in first["items"]] == [
            "IMG_5.jpg",
            "IMG_4.jpg",
        ]
        assert [item["origin"]["filename"] for item in second["items"]] == [
            "IMG_3.jpg",
            "IMG_2.jpg",
        ]
        # Walking back lands on the window it came from.
        assert [item["origin"]["filename"] for item in back["items"]] == [
            "IMG_5.jpg",
            "IMG_4.jpg",
        ]

    async def test_it_jumps_to_a_moment(
        self,
        api_client: AsyncClient,
        session: AsyncSession,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """What the scrubber does: land on a year without walking there."""
        await a_library(session)
        head = await headers(api_client, session_factory)

        body = (await api_client.get("/media?limit=2&at=2009-08-24T00:00:00Z", headers=head)).json()

        assert [item["origin"]["filename"] for item in body["items"]] == ["IMG_3.jpg", "IMG_2.jpg"]
        # There is something newer than the moment jumped to, so the window can walk back up.
        assert body["prev_cursor"] is not None

    async def test_one_month_stays_in_that_month(
        self,
        api_client: AsyncClient,
        session: AsyncSession,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Somebody who chose August 2014 wants August 2014, not the years before it."""
        await a_library(session)
        head = await headers(api_client, session_factory)

        body = (await api_client.get("/media?month=2009-08", headers=head)).json()

        assert [item["origin"]["filename"] for item in body["items"]] == [
            "IMG_4.jpg",
            "IMG_3.jpg",
        ]
        assert body["next_cursor"] is None
        assert body["prev_cursor"] is None

    async def test_a_month_holding_nothing_is_empty_rather_than_wrong(
        self,
        api_client: AsyncClient,
        session: AsyncSession,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        await a_library(session)
        head = await headers(api_client, session_factory)

        body = (await api_client.get("/media?month=2001-03", headers=head)).json()

        assert body["items"] == []

    async def test_a_month_that_is_not_a_month_is_refused(
        self,
        api_client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        head = await headers(api_client, session_factory)

        assert (await api_client.get("/media?month=2014", headers=head)).status_code == 422

    async def test_media_whose_files_are_gone_stay_out(
        self,
        api_client: AsyncClient,
        session: AsyncSession,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        album = await an_album(session, "2009 Italien")
        await a_medium(session, album, taken_at=JULY, name="IMG_1.jpg")
        await a_medium(session, album, taken_at=JULY, name="IMG_2.jpg", status=MediaStatus.MISSING)
        await session.commit()
        head = await headers(api_client, session_factory)

        body = (await api_client.get("/media", headers=head)).json()

        assert [item["origin"]["filename"] for item in body["items"]] == ["IMG_1.jpg"]

    async def test_a_medium_without_a_date_still_has_a_place(
        self,
        api_client: AsyncClient,
        session: AsyncSession,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Until stage 2 has read it, a medium stands where it was found."""
        album = await an_album(session, "2009 Italien")
        await a_medium(session, album, taken_at=None, name="IMG_1.jpg")
        await session.commit()
        head = await headers(api_client, session_factory)

        body = (await api_client.get("/media", headers=head)).json()

        assert len(body["items"]) == 1
        assert body["items"][0]["taken_at"] is None

    async def test_two_directions_at_once_are_a_problem(
        self,
        api_client: AsyncClient,
        session: AsyncSession,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        await a_library(session)
        head = await headers(api_client, session_factory)

        response = await api_client.get("/media?cursor=abc&at=2009-07-01T00:00:00Z", headers=head)

        assert response.status_code == 400
        assert response.json()["type"].endswith("invalid-cursor")

    async def test_a_cursor_we_never_handed_out_is_a_problem(
        self,
        api_client: AsyncClient,
        session: AsyncSession,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        head = await headers(api_client, session_factory)

        response = await api_client.get("/media?cursor=nonsense", headers=head)

        assert response.status_code == 400

    async def test_only_for_those_who_are_signed_in(self, api_client: AsyncClient) -> None:
        assert (await api_client.get("/media")).status_code == 401


class TestMarks:
    async def test_it_counts_every_month(
        self,
        api_client: AsyncClient,
        session: AsyncSession,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Every level is built from this, so the numbers have to add up to the whole."""
        await a_library(session)
        head = await headers(api_client, session_factory)

        body = (await api_client.get("/media/marks", headers=head)).json()

        assert body["by"] == "month"
        assert body["total"] == 5
        assert [(mark["start"], mark["count"]) for mark in body["marks"]] == [
            ("2010-08-01", 1),
            ("2009-08-01", 2),
            ("2009-07-01", 2),
        ]

    async def test_it_counts_years_as_well(
        self,
        api_client: AsyncClient,
        session: AsyncSession,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        await a_library(session)
        head = await headers(api_client, session_factory)

        body = (await api_client.get("/media/marks?by=year", headers=head)).json()

        assert [(mark["start"], mark["count"]) for mark in body["marks"]] == [
            ("2010-01-01", 1),
            ("2009-01-01", 4),
        ]

    async def test_days_are_asked_for_one_year_at_a_time(
        self,
        api_client: AsyncClient,
        session: AsyncSession,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Nine thousand days for 26 years is not something to hand over in one go."""
        await a_library(session)
        head = await headers(api_client, session_factory)

        body = (await api_client.get("/media/marks?by=day&year=2009", headers=head)).json()

        assert body["total"] == 4
        assert [(mark["start"], mark["count"]) for mark in body["marks"]] == [
            ("2009-08-24", 1),
            ("2009-08-23", 1),
            ("2009-07-15", 1),
            ("2009-07-14", 1),
        ]

    async def test_an_empty_library_has_no_marks(
        self,
        api_client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        head = await headers(api_client, session_factory)

        body = (await api_client.get("/media/marks", headers=head)).json()

        assert body == {"by": "month", "total": 0, "marks": []}


class TestPeriods:
    async def test_every_year_comes_with_a_few_pictures_out_of_it(
        self,
        api_client: AsyncClient,
        session: AsyncSession,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """What the overview shows: a card per year, newest first."""
        media = await a_library(session)
        for medium in media:
            medium.thumbnail_path = f"ab/{medium.id.hex}/thumb.webp"
        await session.commit()
        head = await headers(api_client, session_factory)

        body = (await api_client.get("/media/periods?by=year&covers=2", headers=head)).json()

        assert [(period["start"], period["count"]) for period in body] == [
            ("2010-01-01", 1),
            ("2009-01-01", 4),
        ]
        # Newest first inside the year as well, and never more than asked for.
        assert len(body[1]["covers"]) == 2
        assert body[1]["covers"][0]["thumb"].startswith("/api/v1/media/")
        assert "token=" in body[1]["covers"][0]["thumb"]

    async def test_a_year_without_previews_still_counts(
        self,
        api_client: AsyncClient,
        session: AsyncSession,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Huginn may not have made the previews yet; the year exists all the same."""
        await a_library(session)
        head = await headers(api_client, session_factory)

        body = (await api_client.get("/media/periods?by=year", headers=head)).json()

        assert [period["count"] for period in body] == [1, 4]
        assert all(period["covers"] == [] for period in body)

    async def test_the_months_of_one_year(
        self,
        api_client: AsyncClient,
        session: AsyncSession,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        await a_library(session)
        head = await headers(api_client, session_factory)

        body = (await api_client.get("/media/periods?by=month&year=2009", headers=head)).json()

        assert [(period["start"], period["count"]) for period in body] == [
            ("2009-08-01", 2),
            ("2009-07-01", 2),
        ]

    async def test_only_for_those_who_are_signed_in(self, api_client: AsyncClient) -> None:
        assert (await api_client.get("/media/periods")).status_code == 401
