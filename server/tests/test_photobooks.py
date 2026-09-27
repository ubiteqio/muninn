"""Fotobücher: making them, reading them, and who may do which."""

import hashlib
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from muninn.ai import service as ai_service
from muninn.ai.base import AiError
from muninn.analysis import service as analysis_service
from muninn.models.ai import AiKind, AiProfile
from muninn.models.album import Album
from muninn.models.media import Media
from muninn.models.photobook import (
    SIZE_LARGE,
    SIZE_SMALL,
    STATE_FAILED,
    STATE_READY,
    Photobook,
)
from muninn.models.user import UserRole
from muninn.photobooks import service, words
from tests.helpers import auth_header, create_user, login
from tests.test_search import described
from tests.test_timeline import a_medium, an_album

pytestmark = pytest.mark.usefixtures("api_client")

APRIL = datetime(2024, 4, 25, 10, 0, tzinfo=UTC)


def far(at: int) -> int:
    """A fingerprint of its own: two unrelated pictures differ in about half their bits."""
    digest = hashlib.md5(f"picture {at}".encode(), usedforsecurity=False).digest()[:8]
    return int.from_bytes(digest, signed=True)  # as the duplicate finder stores them: int64


async def a_picture(
    session: AsyncSession,
    album: Album,
    name: str,
    *,
    taken_at: datetime,
    caption: str = "",
    fingerprint: int | None = None,
) -> Media:
    medium = await a_medium(session, album, taken_at=taken_at, name=name)
    medium.width, medium.height = 4000, 3000
    medium.thumbnail_path = f"thumbs/{name}.jpg"
    medium.preview_path = f"previews/{name}.jpg"
    medium.fingerprint = fingerprint
    if caption:
        await analysis_service.store(
            session, medium.id, model="qwen", analysis=described(caption, "strand", scene="strand")
        )
    return medium


async def an_album_of(session: AsyncSession, name: str, pictures: int = 12) -> Album:
    album = await an_album(session, name)
    for index in range(pictures):
        await a_picture(
            session,
            album,
            f"{name}-{index}.jpg",
            taken_at=APRIL + timedelta(hours=index * 3),
            caption=f"Eine Aufnahme Nummer {index}.",
            fingerprint=far(index),
        )
    await session.commit()
    return album


class TestBuilding:
    async def test_a_book_is_built_from_the_album_with_pages_and_a_cover(
        self, session: AsyncSession
    ) -> None:
        album = await an_album_of(session, "Estland")
        (book,) = await service.create(session, album=album, size=SIZE_LARGE, max_media=150)

        await service.build(session, book)

        assert book.state == STATE_READY
        assert book.page_count > 2  # an opening page, a day, its moments and the map
        assert book.media_count > 0
        assert book.cover_media_id is not None
        assert book.from_at == APRIL
        assert book.pages[0]["kind"] == "auftakt"
        assert book.pages[-1]["kind"] == "schluss"

    async def test_the_analyzer_sentences_do_not_travel_into_the_book(
        self, session: AsyncSession
    ) -> None:
        album = await an_album_of(session, "Estland")
        (book,) = await service.create(session, album=album)

        await service.build(session, book)

        # No machine answered here, so the pages keep their plain facts - but never the raw
        # material the writing would have used.
        assert all("facts" not in page for page in book.pages)
        assert all("_pictures" not in page for page in book.pages)
        assert book.written is False

    async def test_the_ceiling_holds_a_large_album_to_a_readable_book(
        self, session: AsyncSession
    ) -> None:
        album = await an_album_of(session, "Viele", pictures=40)
        (book,) = await service.create(session, album=album, size=SIZE_LARGE, max_media=10)

        await service.build(session, book)

        assert book.media_count == 10

    async def test_two_books_of_one_album_are_two_different_books(
        self, session: AsyncSession
    ) -> None:
        album = await an_album_of(session, "Estland", pictures=40)
        first, second = await service.create(
            session, album=album, size=SIZE_SMALL, max_media=150, count=2
        )

        await service.build(session, first)
        await service.build(session, second)

        assert first.title.endswith("I")
        assert second.title.endswith("II")
        assert first.seed != second.seed
        assert _media_in(first) != _media_in(second)

    async def test_the_pictures_reach_from_the_first_to_the_last_of_the_album(
        self, session: AsyncSession
    ) -> None:
        album = await an_album_of(session, "Estland", pictures=40)
        (book,) = await service.create(session, album=album, size=SIZE_SMALL, max_media=150)

        await service.build(session, book)
        chosen = _media_in(book)
        first = await service.shots_of(session, album.id)

        assert first[0].id in chosen
        assert first[-1].id in chosen

    async def test_an_album_without_dates_makes_no_book_and_says_so(
        self, session: AsyncSession
    ) -> None:
        album = await an_album(session, "Leer")
        await session.commit()
        (book,) = await service.create(session, album=album)

        await service.build(session, book)

        assert book.state == STATE_FAILED
        assert "keine Aufnahme" in book.trouble

    async def test_the_words_of_the_machine_land_on_the_pages(
        self, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        album = await an_album_of(session, "Estland", pictures=6)
        (book,) = await service.create(session, album=album)

        async def wrote(_writer: object, pages: list[dict[str, object]], **_: object) -> int:
            for page in pages:
                page["headline"] = "Der Grill ist an"
                page["story"] = "Boris wendet das Fleisch."
            return len(pages)

        monkeypatch.setattr(words, "write_pages", wrote)
        monkeypatch.setattr(ai_service, "active_profile", _a_profile)

        await service.build(session, book)

        assert book.written is True
        assert any(page.get("headline") == "Der Grill ist an" for page in book.pages)

    async def test_a_machine_that_is_away_still_leaves_a_whole_book(
        self, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        album = await an_album_of(session, "Estland", pictures=6)
        (book,) = await service.create(session, album=album)

        async def refused(*_: object, **__: object) -> int:
            raise AiError("Die Maschine ist aus.")

        monkeypatch.setattr(words, "write_pages", refused)
        monkeypatch.setattr(ai_service, "active_profile", _a_profile)

        await service.build(session, book)

        assert book.state == STATE_READY
        assert book.written is False
        assert book.page_count > 0


def _media_in(book: Photobook) -> set[str]:
    found: set[str] = set()
    for page in book.pages:
        for held in page.values():
            for shown in held if isinstance(held, list) else [held]:
                if isinstance(shown, dict) and "variant" in shown:
                    found.add(str(shown["id"]))
    return found


async def _a_profile(*_: object, **__: object) -> AiProfile:
    """A profile that exists, so the service asks it to write. The writing itself is patched."""
    return AiProfile(
        kind=AiKind.ANALYZER,
        name="Prüfmaschine",
        base_url="http://example.invalid/v1",
        api_key="",
        model="qwen",
        concurrency=2,
        timeout_seconds=30,
        is_active=True,
    )


class TestApi:
    async def test_a_member_reads_the_shelf_and_the_pages(
        self,
        api_client: AsyncClient,
        session: AsyncSession,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        album = await an_album_of(session, "Estland")
        (book,) = await service.create(session, album=album)
        await service.build(session, book)
        await session.commit()
        await create_user(session_factory, username="anna", display_name="Anna")
        headers = auth_header(await login(api_client, username="anna"))

        shelf = (await api_client.get("/photobooks", headers=headers)).json()
        assert len(shelf["items"]) == 1
        assert shelf["items"][0]["album"] == "Estland"
        assert shelf["items"][0]["cover"].startswith(f"/api/v1/media/{book.cover_media_id}/thumb")

        read = (await api_client.get(f"/photobooks/{book.id}", headers=headers)).json()
        assert len(read["leaves"]) == book.page_count
        opening = read["leaves"][0]
        assert opening["hero"]["src"].startswith("/api/v1/media/")
        assert "token=" in opening["hero"]["src"]

    async def test_a_member_may_not_make_or_remove_books(
        self,
        api_client: AsyncClient,
        session: AsyncSession,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        album = await an_album_of(session, "Estland")
        (book,) = await service.create(session, album=album)
        await session.commit()
        await create_user(session_factory, username="anna", display_name="Anna")
        headers = auth_header(await login(api_client, username="anna"))

        made = await api_client.post(
            "/photobooks", json={"album_id": str(album.id)}, headers=headers
        )
        removed = await api_client.delete(f"/photobooks/{book.id}", headers=headers)

        assert made.status_code == 403
        assert removed.status_code == 403

    async def test_an_admin_orders_three_books_of_one_album(
        self,
        api_client: AsyncClient,
        session: AsyncSession,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        album = await an_album_of(session, "Estland")
        await create_user(
            session_factory, username="chef", display_name="Chef", role=UserRole.ADMIN
        )
        headers = auth_header(await login(api_client, username="chef"))

        answer = await api_client.post(
            "/photobooks",
            json={
                "album_id": str(album.id),
                "size": SIZE_SMALL,
                "max_media": 20,
                "count": 3,
            },
            headers=headers,
        )

        assert answer.status_code == 202
        made = answer.json()["items"]
        assert [one["title"] for one in made] == ["Estland I", "Estland II", "Estland III"]
        assert all(one["state"] == "building" for one in made)
        assert len(await service.listed(session)) == 3

    async def test_an_admin_removes_a_book_and_the_pictures_stay(
        self,
        api_client: AsyncClient,
        session: AsyncSession,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        album = await an_album_of(session, "Estland")
        (book,) = await service.create(session, album=album)
        await service.build(session, book)
        await session.commit()
        await create_user(
            session_factory, username="chef", display_name="Chef", role=UserRole.ADMIN
        )
        headers = auth_header(await login(api_client, username="chef"))

        gone = await api_client.delete(f"/photobooks/{book.id}", headers=headers)

        assert gone.status_code == 204
        assert await service.listed(session) == []
        assert len(await service.shots_of(session, album.id)) == 12

    async def test_a_book_nobody_made(
        self,
        api_client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        await create_user(session_factory, username="anna", display_name="Anna")
        headers = auth_header(await login(api_client, username="anna"))

        answer = await api_client.get(f"/photobooks/{uuid.uuid4()}", headers=headers)

        assert answer.status_code == 404
        assert answer.json()["title"] == "Dieses Fotobuch gibt es nicht."

    async def test_an_unknown_size_is_refused(
        self,
        api_client: AsyncClient,
        session: AsyncSession,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        album = await an_album_of(session, "Estland")
        await create_user(
            session_factory, username="chef", display_name="Chef", role=UserRole.ADMIN
        )
        headers = auth_header(await login(api_client, username="chef"))

        answer = await api_client.post(
            "/photobooks",
            json={"album_id": str(album.id), "size": "riesig"},
            headers=headers,
        )

        assert answer.status_code == 422
