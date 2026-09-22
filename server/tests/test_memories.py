"""Rückblicke: the photos of this calendar day in earlier years."""

from datetime import UTC, date, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from muninn.analysis import service as analysis_service
from muninn.duplicates import service as duplicates_service
from muninn.memories import service
from muninn.models.album import Album
from muninn.models.media import DateSource, Media
from muninn.models.social import Like
from muninn.models.user import User
from tests.helpers import auth_header, create_user, login
from tests.test_search import described
from tests.test_timeline import a_medium, an_album

pytestmark = pytest.mark.usefixtures("api_client")

TODAY = date(2026, 9, 21)


async def _photo(
    session: AsyncSession,
    album: Album,
    name: str,
    when: datetime,
    source: DateSource = DateSource.EXIF,
) -> Media:
    medium = await a_medium(session, album, taken_at=when, name=name)
    medium.taken_at_source = source
    await session.commit()
    return medium


def _at(year: int, month: int = 9, day: int = 21, hour: int = 12) -> datetime:
    return datetime(year, month, day, hour, tzinfo=UTC)


async def _names(session: AsyncSession, day: date = TODAY) -> list[tuple[int, list[str]]]:
    return [
        (entry.memory.year, [medium.primary_file.filename for medium in entry.media])
        for entry in await service.of_day(session, day)
    ]


async def test_each_earlier_year_of_the_day_is_one_memory(session: AsyncSession) -> None:
    rome = await an_album(session, "Rom 2019")
    await _photo(session, rome, "rom.jpg", _at(2019))
    await _photo(session, await an_album(session, "Sommer 2015"), "see.jpg", _at(2015, hour=9))
    await _photo(session, rome, "gestern.jpg", _at(2019, day=20))
    await _photo(session, await an_album(session, "Heute"), "heute.jpg", _at(2026))
    # A date from the folder name or the file's own time is no date to remember by.
    await _photo(session, rome, "ordner.jpg", _at(2019), DateSource.FOLDER_NAME)

    found = await service.of_day(session, TODAY)

    assert [(entry.memory.year, entry.album.display_title if entry.album else None)
            for entry in found] == [(2019, "Rom 2019"), (2015, "Sommer 2015")]  # fmt: skip
    assert await _names(session) == [(2019, ["rom.jpg"]), (2015, ["see.jpg"])]


async def test_screenshots_copies_and_hidden_media_stay_out(session: AsyncSession) -> None:
    album = await an_album(session, "Urlaub")
    await _photo(session, album, "gut.jpg", _at(2020, hour=10))
    screenshot = await _photo(session, album, "screen.png", _at(2020, hour=11))
    await analysis_service.store(
        session,
        screenshot.id,
        model="qwen",
        analysis=described("Ein Chat.").model_copy(update={"is_screenshot": True}),
    )
    first = await _photo(session, album, "kopie-a.jpg", _at(2020, hour=13))
    second = await _photo(session, album, "kopie-b.jpg", _at(2020, hour=14))
    second.content_hash = first.content_hash
    first.width, first.height = 4000, 3000
    await session.commit()
    await duplicates_service.find_groups(session)

    assert await _names(session) == [(2020, ["gut.jpg", "kopie-a.jpg"])]


async def test_twelve_at_most_liked_first_then_in_the_order_taken(
    session: AsyncSession, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    album = await an_album(session, "Hochzeit")
    photos = [await _photo(session, album, f"{hour:02}.jpg", _at(2018, hour=hour))
              for hour in range(6, 22)]  # fmt: skip
    await create_user(session_factory, username="anna", display_name="Anna")
    anna = await session.scalar(select(User).where(User.username == "anna"))
    assert anna is not None
    session.add(Like(user_id=anna.id, media_id=photos[0].id))
    await session.commit()

    ((year, names),) = await _names(session)

    assert year == 2018
    assert len(names) == service.PER_YEAR
    assert names == sorted(names)
    assert "06.jpg" in names


async def test_without_anything_on_the_day_the_week_around_it_counts(
    session: AsyncSession,
) -> None:
    album = await an_album(session, "Herbst")
    await _photo(session, album, "zwei-tage-vorher.jpg", _at(2017, day=19))
    await _photo(session, album, "zu-weit.jpg", _at(2017, day=10))

    found = await service.of_day(session, TODAY)

    assert [entry.memory.from_week for entry in found] == [True]
    assert await _names(session) == [(2017, ["zwei-tage-vorher.jpg"])]


async def test_the_choice_of_a_day_stays_all_day(session: AsyncSession) -> None:
    album = await an_album(session, "Rom")
    await _photo(session, album, "rom.jpg", _at(2019))
    assert await service.prepare(session, TODAY) == 1

    await _photo(session, album, "später-kopiert.jpg", _at(2019, hour=18))

    assert await _names(session) == [(2019, ["rom.jpg"])]
    # Another day, far from it, has nothing.
    assert await _names(session, date(2026, 3, 1)) == []


async def test_the_api_names_the_years_ago_and_the_album(
    api_client: AsyncClient,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    album = await an_album(session, "Rom 2019")
    photo = await _photo(session, album, "rom.jpg", _at(2019))
    await create_user(session_factory, username="anna", display_name="Anna")
    headers = auth_header(await login(api_client, username="anna"))

    body = (
        await api_client.get("/memories", params={"day": TODAY.isoformat()}, headers=headers)
    ).json()

    (memory,) = body["items"]
    assert memory["years_ago"] == 7
    assert memory["title"] == "Rom 2019"
    assert memory["taken_on"] == "2019-09-21"
    assert [item["id"] for item in memory["media"]] == [str(photo.id)]
