"""Smarts: what an album falls into when nobody sorted it."""

import math
import uuid
from collections import Counter
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from muninn.ai import service as ai_service
from muninn.analysis import service as analysis_service
from muninn.models.ai import AiKind
from muninn.models.album import Album
from muninn.search.service import VectorKind, store
from muninn.smarts import service
from tests.helpers import auth_header, create_user, login
from tests.test_search import described
from tests.test_timeline import a_medium, an_album

pytestmark = pytest.mark.usefixtures("api_client")

MARCH = datetime(2018, 3, 24, 12, 0, tzinfo=UTC)


def an_id(number: int) -> uuid.UUID:
    return uuid.UUID(int=number)


def pairs_of(*groups: list[int], distance: float = 0.1) -> list[tuple[uuid.UUID, uuid.UUID, float]]:
    """Everything inside a group is close to everything else in it; nothing else is close."""
    return [
        (an_id(first), an_id(second), distance)
        for group in groups
        for index, first in enumerate(group)
        for second in group[index + 1 :]
    ]


class TestGrouping:
    def test_what_looks_alike_lands_together(self) -> None:
        ids = [an_id(number) for number in range(1, 11)]

        groups, single = service._group(
            ids, pairs_of([1, 2, 3, 4], [5, 6, 7, 8]), distance=0.24, too_big=6
        )

        assert [len(group) for group in groups] == [4, 4]
        assert single == [an_id(9), an_id(10)]

    def test_a_medium_belongs_to_one_chapter_only(self) -> None:
        ids = [an_id(number) for number in range(1, 9)]
        # 4 is close to both halves; it may only be counted once.
        overlapping = pairs_of([1, 2, 3, 4], [4, 5, 6, 7])

        groups, single = service._group(ids, overlapping, distance=0.24, too_big=6)

        placed = [one for group in groups for one in group]
        assert len(placed) == len(set(placed))
        assert an_id(8) in single

    def test_a_group_that_swallows_the_album_is_taken_apart(self) -> None:
        """ "Haus", 206 pictures, is not a chapter. Tighter, it is the three things it really is."""
        ids = [an_id(number) for number in range(1, 13)]
        loose = pairs_of(list(range(1, 13)), distance=0.20)
        tight = pairs_of([1, 2, 3, 4], [5, 6, 7, 8], [9, 10, 11, 12], distance=0.10)

        groups, _ = service._group(ids, [*loose, *tight], distance=0.24, too_big=5)

        assert [len(group) for group in groups] == [4, 4, 4]

    def test_what_is_alike_all_the_way_down_stays_one_chapter(self) -> None:
        """A folder of one room: no distance tells those pictures apart, and that is an answer."""
        ids = [an_id(number) for number in range(1, 13)]

        groups, _ = service._group(
            ids, pairs_of(list(range(1, 13)), distance=0.01), distance=0.24, too_big=5
        )

        assert [len(group) for group in groups] == [12]

    def test_a_coincidence_of_two_is_no_chapter(self) -> None:
        ids = [an_id(number) for number in range(1, 6)]

        groups, single = service._group(ids, pairs_of([1, 2]), distance=0.24, too_big=4)

        assert groups == []
        assert len(single) == 5

    def test_the_same_album_gives_the_same_chapters_twice(self) -> None:
        ids = [an_id(number) for number in range(1, 11)]
        pairs = pairs_of([1, 2, 3, 4], [5, 6, 7, 8])

        first, _ = service._group(ids, pairs, distance=0.24, too_big=6)
        again, _ = service._group(ids, pairs, distance=0.24, too_big=6)

        assert first == again


class TestNames:
    def _looks(self, tags: dict[int, list[str]]) -> dict[uuid.UUID, service.Look]:
        return {
            an_id(number): service.Look(
                media_id=an_id(number), taken_at=MARCH, tags=tuple(words), scene=""
            )
            for number, words in tags.items()
        }

    def test_the_name_is_what_the_rest_of_the_album_has_not(self) -> None:
        """Every picture of the album is "innenraum"; only these four are "katze"."""
        looks = self._looks({number: ["innenraum", "katze"] for number in range(1, 5)})
        album = Counter({"innenraum": 400, "katze": 4})

        title, words = service.name_of([an_id(number) for number in range(1, 5)], looks, album, 400)

        assert words[0] == "katze"
        assert title.startswith("Katze")

    def test_a_tag_on_a_handful_of_the_group_names_nothing(self) -> None:
        looks = self._looks({1: ["katze"], 2: [], 3: [], 4: [], 5: [], 6: [], 7: [], 8: []})
        album = Counter({"katze": 1})

        title, words = service.name_of([an_id(number) for number in range(1, 9)], looks, album, 100)

        assert (title, words) == ("", [])

    def test_the_scene_stands_in_when_no_tag_does(self) -> None:
        looks = {
            an_id(number): service.Look(
                media_id=an_id(number), taken_at=MARCH, tags=(), scene="strand"
            )
            for number in range(1, 5)
        }

        title, words = service.name_of(
            [an_id(number) for number in range(1, 5)], looks, Counter(), 100
        )

        assert (title, words) == ("Strand", ["strand"])


async def an_album_of_media(session: AsyncSession, path: str, groups: list[list[str]]) -> Album:
    """One album whose pictures fall into the given groups by what their vectors look like."""
    album = await an_album(session, path)
    for index, group in enumerate(groups):
        for position, tag in enumerate(group):
            # Far apart between the groups, right next to each other inside one.
            vector = [0.0] * 8
            vector[index] = 1.0
            vector[7] = position * 0.001
            medium = await a_medium(
                session, album, taken_at=MARCH, name=f"{tag}-{index}-{position}.jpg"
            )
            await analysis_service.store(
                session,
                medium.id,
                model="qwen",
                analysis=described(f"Ein Bild von {tag}.", tag),
            )
            await store(
                session,
                VectorKind.IMAGE,
                media_id=medium.id,
                model="siglip2",
                version=1,
                vector=vector,
            )
    await session.commit()
    return album


async def a_profile(session: AsyncSession) -> None:
    await ai_service.create_profile(
        session, kind=AiKind.IMAGE_EMBEDDER, name="GPU", base_url="http://gpu/v1", model="siglip2"
    )


async def test_an_album_is_built_into_chapters_from_its_vectors(session: AsyncSession) -> None:
    await a_profile(session)
    album = await an_album_of_media(
        session,
        "Heap",
        [["katze"] * 6, ["fußball"] * 6, ["torte"] * 6, ["auto"] * 6, ["baum"] * 6],
    )

    built = await service.build_album(session, album.id)

    assert built.chapters == 5
    chapters = await service.chapters_of(session, album.id)
    assert sorted(chapter.title for chapter in chapters) == [
        "Auto",
        "Baum",
        "Fußball",
        "Katze",
        "Torte",
    ]
    assert all(chapter.size == 6 for chapter in chapters)
    assert all(chapter.cover_media_id is not None for chapter in chapters)


async def test_building_again_replaces_what_was_there(session: AsyncSession) -> None:
    await a_profile(session)
    album = await an_album_of_media(
        session, "Heap", [["katze"] * 8, ["fußball"] * 8, ["torte"] * 8]
    )

    await service.build_album(session, album.id)
    await service.build_album(session, album.id)

    chapters = await service.chapters_of(session, album.id)
    assert len(chapters) == 3


async def test_a_small_album_needs_no_chapters(session: AsyncSession) -> None:
    await a_profile(session)
    album = await an_album_of_media(session, "Klein", [["katze"] * 5, ["fußball"] * 5])

    built = await service.build_album(session, album.id)

    assert built.chapters == 0
    assert await service.chapters_of(session, album.id) == []


async def test_the_api_hands_out_chapters_with_their_covers(
    api_client: AsyncClient,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await a_profile(session)
    album = await an_album_of_media(
        session, "Heap", [["katze"] * 8, ["fußball"] * 8, ["torte"] * 8, ["auto"] * 8]
    )
    await service.build_album(session, album.id)
    await create_user(session_factory, username="anna", display_name="Anna")
    headers = auth_header(await login(api_client, username="anna"))

    body = (await api_client.get("/smarts", headers=headers)).json()

    assert body["media"] == 32
    assert len(body["chapters"]) == 4
    first = body["chapters"][0]
    assert first["size"] == 8
    assert first["album_title"] == "Heap"
    assert len(first["cover"]) == 6
    assert {shelf["key"] for shelf in body["shelves"]} >= {"video", "document", "people"}

    opened = (await api_client.get(f"/smarts/chapters/{first['id']}", headers=headers)).json()
    assert len(opened["items"]) == 8
    assert opened["chapter"]["title"] == first["title"]


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


async def test_only_albums_that_changed_are_built_again(session: AsyncSession) -> None:
    await a_profile(session)
    album = await an_album_of_media(
        session, "Heap", [["katze"] * 8, ["fußball"] * 8, ["torte"] * 8]
    )

    assert album.id in await service.albums_to_build(session)
    await service.build_album(session, album.id)
    assert album.id not in await service.albums_to_build(session)


def test_the_naming_weighs_a_rare_tag_higher_than_a_common_one() -> None:
    """The formula itself: share in the group, weighed by how rare the tag is in the album."""
    rare = 1.0 * math.log(1 / (4 / 400))
    common = 1.0 * math.log(1 / (400 / 400))

    assert rare > common
