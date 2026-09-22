"""Mímir: every way into the library, and how the ways are weighed against each other."""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from muninn.ai import service as ai_service
from muninn.ai.analysis import Analysis
from muninn.ai.base import AiError, Check, SpokenPart, Transcript
from muninn.analysis import service as analysis_service
from muninn.analysis import transcripts
from muninn.models.ai import AiKind
from muninn.models.album import Album
from muninn.models.analysis import VideoFrame
from muninn.models.media import Media, MediaKind, MediaStatus
from muninn.models.user import UserRole
from muninn.search import engine
from muninn.search.service import VectorKind, store
from tests.helpers import auth_header, create_user, login
from tests.test_timeline import a_medium, an_album

pytestmark = pytest.mark.usefixtures("api_client")

SUMMER_2012 = datetime(2012, 7, 14, 12, 0, tzinfo=UTC)
WINTER_2015 = datetime(2015, 1, 20, 12, 0, tzinfo=UTC)

#: Three-dimensional stand-ins for the models' vectors: a beach, a dog, a document.
BEACH = [1.0, 0.1, 0.0]
DOG = [0.0, 1.0, 0.1]
PAPER = [0.1, 0.0, 1.0]


def described(caption: str, *tags: str, scene: str = "", time_of_day: str = "tag") -> Analysis:
    return Analysis.model_validate(
        {
            "caption": caption,
            "tags": list(tags),
            "scene": scene,
            "ocr_text": "",
            "people_count": 0,
            "time_of_day": time_of_day,
            "is_screenshot": False,
            "is_document": False,
            "quality": "gut",
        }
    )


async def a_described(
    session: AsyncSession,
    album_path: str,
    name: str,
    *,
    caption: str,
    picture: list[float] | None = None,
    meaning: list[float] | None = None,
    taken_at: datetime = SUMMER_2012,
    kind: MediaKind = MediaKind.IMAGE,
    **analysis: Any,
) -> Media:
    album = await session.scalar(select(Album).where(Album.relative_path == album_path))
    if album is None:
        album = await an_album(session, album_path)
    medium = await a_medium(session, album, taken_at=taken_at, name=name)
    medium.kind = kind
    await analysis_service.store(
        session, medium.id, model="qwen", analysis=described(caption, **analysis)
    )
    if picture is not None:
        await store(
            session, VectorKind.IMAGE, media_id=medium.id, model="siglip2", version=1,
            vector=picture,
        )  # fmt: skip
    if meaning is not None:
        await store(
            session, VectorKind.CAPTION, media_id=medium.id, model="bge-m3", version=1,
            vector=meaning,
        )  # fmt: skip
    await session.commit()
    return medium


async def found(session: AsyncSession, words: str, **filters: Any) -> list[str]:
    hits = await engine.search(session, words=words, filters=engine.Filters(**filters))
    names = {}
    for hit in hits:
        medium = await session.get(Media, hit.media_id)
        assert medium is not None
        await session.refresh(medium, ["files"])
        names[hit.media_id] = medium.files[0].filename
    return [names[hit.media_id] for hit in hits]


class TestWords:
    async def test_a_word_finds_its_stem_in_the_description(self, session: AsyncSession) -> None:
        await a_described(session, "Urlaub", "IMG_1.jpg", caption="Kinder bauen Sandburgen.")
        await a_described(session, "Urlaub", "IMG_2.jpg", caption="Ein Hund im Garten.")

        assert await found(session, "Sandburg") == ["IMG_1.jpg"]

    async def test_scene_and_time_of_day_are_words_too(self, session: AsyncSession) -> None:
        await a_described(
            session, "Urlaub", "IMG_1.jpg", caption="Lichter am Himmel.", scene="strand",
            time_of_day="nacht",
        )  # fmt: skip

        assert await found(session, "Strand") == ["IMG_1.jpg"]
        assert await found(session, "Nacht") == ["IMG_1.jpg"]

    async def test_what_the_file_says_about_itself_is_found(self, session: AsyncSession) -> None:
        medium = await a_described(session, "Urlaub", "IMG_1.jpg", caption="Ein Baum.")
        medium.camera_make = "Canon"
        medium.camera_model = "EOS 400D"
        await session.commit()

        assert await found(session, "Canon") == ["IMG_1.jpg"]
        assert await found(session, "400D") == ["IMG_1.jpg"]

    async def test_album_and_file_names_are_found_despite_a_typo(
        self, session: AsyncSession
    ) -> None:
        await a_described(session, "Urlaub/2012 Italien", "IMG_1.jpg", caption="Ein Baum.")
        await a_described(session, "Urlaub/2014 Norwegen", "IMG_2.jpg", caption="Ein Fjord.")

        assert await found(session, "Italen") == ["IMG_1.jpg"]


class TestVideos:
    async def test_a_frame_leads_to_its_second(self, session: AsyncSession) -> None:
        video = await a_described(
            session, "Filme", "MOV_1.mov", caption="Ein Kindergeburtstag.", kind=MediaKind.VIDEO
        )
        session.add(
            VideoFrame(
                media_id=video.id, second=42, caption="Eine Torte mit Kerzen.", tags=["torte"],
                ocr_text="", people_count=0, search_tsv="'kerz':4 'tort':2",
            )
        )  # fmt: skip
        await session.commit()

        hits = await engine.search(session, words="Torte", filters=engine.Filters())

        assert [(hit.media_id, hit.moment) for hit in hits] == [(video.id, 42.0)]

    async def test_something_said_leads_to_its_second(self, session: AsyncSession) -> None:
        video = await a_described(
            session, "Filme", "MOV_1.mov", caption="Ein Garten.", kind=MediaKind.VIDEO
        )
        await transcripts.store(
            session,
            video.id,
            model="whisper",
            transcript=Transcript(
                language="de",
                parts=[
                    SpokenPart(1.0, 2.0, "Hallo zusammen."),
                    SpokenPart(12.5, 14.0, "Wer möchte Kuchen?"),
                ],
            ),
        )
        await session.commit()

        hits = await engine.search(session, words="Kuchen", filters=engine.Filters())

        assert [(hit.media_id, hit.moment) for hit in hits] == [(video.id, 12.5)]


class TestVectors:
    async def test_a_picture_without_a_description_is_found_by_how_it_looks(
        self, session: AsyncSession
    ) -> None:
        """Before stage 5 has described it, the picture model is all there is to go by."""
        album = await an_album(session, "A")
        beach = await a_medium(session, album, taken_at=SUMMER_2012, name="IMG_beach.jpg")
        far = await a_medium(session, album, taken_at=SUMMER_2012, name="IMG_far.jpg")
        for medium, vector in ((beach, BEACH), (far, [0.0, 0.0, 1.0])):
            await store(
                session, VectorKind.IMAGE, media_id=medium.id, model="siglip2", version=1,
                vector=vector,
            )  # fmt: skip
        await session.commit()

        hits = await engine.search(
            session,
            words="Meer",
            filters=engine.Filters(),
            image=engine.Probe(vector=[1.0, 0.0, 0.0], model="siglip2"),
        )

        # The far one lies beyond the bound; the near one needs nothing else.
        assert [hit.media_id for hit in hits] == [beach.id]

    async def test_a_described_picture_needs_its_description_to_agree(
        self, session: AsyncSession
    ) -> None:
        """The picture model cannot say that nothing fits - "Hund" in a library without dogs
        would bring the nearest concert. A description that does not fit keeps it out."""
        await a_described(session, "A", "IMG_1.jpg", caption="Ein Konzert.", picture=BEACH)

        hits = await engine.search(
            session,
            words="Hund",
            filters=engine.Filters(),
            image=engine.Probe(vector=BEACH, model="siglip2"),
        )

        assert hits == []

    async def test_several_ways_agreeing_beat_one(self, session: AsyncSession) -> None:
        """Found by its picture and its words, a medium outranks one found only by its words."""
        both = await a_described(
            session, "A", "IMG_1.jpg", caption="Ein Hund am Strand.", picture=BEACH, meaning=BEACH
        )
        await a_described(session, "A", "IMG_2.jpg", caption="Der Strand im Regen.", picture=PAPER)

        hits = await engine.search(
            session,
            words="Strand",
            filters=engine.Filters(),
            image=engine.Probe(vector=BEACH, model="siglip2"),
            caption=engine.Probe(vector=BEACH, model="bge-m3"),
        )

        assert hits[0].media_id == both.id


class TestFilters:
    async def test_a_period_kind_and_album_narrow_every_way(self, session: AsyncSession) -> None:
        await a_described(session, "Urlaub/Italien", "IMG_1.jpg", caption="Strand am Mittag.")
        await a_described(
            session, "Urlaub/Italien/Rom", "IMG_2.jpg", caption="Strand bei Rom.",
            taken_at=WINTER_2015,
        )  # fmt: skip
        await a_described(session, "Urlaub/Norwegen", "IMG_3.jpg", caption="Strand am Fjord.")
        await a_described(
            session, "Urlaub/Italien", "MOV_1.mov", caption="Strand im Film.",
            kind=MediaKind.VIDEO,
        )  # fmt: skip

        assert set(await found(session, "Strand", album_path="Urlaub/Italien")) == {
            "IMG_1.jpg", "IMG_2.jpg", "MOV_1.mov",
        }  # fmt: skip
        assert await found(session, "Strand", date_from=datetime(2015, 1, 1).date()) == [
            "IMG_2.jpg"
        ]
        assert await found(session, "Strand", kind=MediaKind.VIDEO) == ["MOV_1.mov"]

    async def test_a_missing_medium_is_never_found(self, session: AsyncSession) -> None:
        medium = await a_described(session, "A", "IMG_1.jpg", caption="Ein Strand.")
        medium.status = MediaStatus.MISSING
        await session.commit()

        assert await found(session, "Strand") == []

    async def test_only_a_period_is_a_walk_through_it(self, session: AsyncSession) -> None:
        await a_described(session, "A", "IMG_old.jpg", caption="x", taken_at=SUMMER_2012)
        await a_described(session, "A", "IMG_new.jpg", caption="y", taken_at=WINTER_2015)

        assert await found(session, "", date_from=datetime(2012, 1, 1).date()) == [
            "IMG_new.jpg", "IMG_old.jpg",
        ]  # fmt: skip


async def test_similar_pictures_leave_the_picture_itself_out(session: AsyncSession) -> None:
    beach = await a_described(session, "A", "IMG_1.jpg", caption="a", picture=BEACH)
    near = await a_described(session, "A", "IMG_2.jpg", caption="b", picture=[1.0, 0.2, 0.0])
    far = await a_described(session, "A", "IMG_3.jpg", caption="c", picture=PAPER)

    hits = await engine.similar(session, beach.id, model="siglip2")

    assert [hit.media_id for hit in hits] == [near.id, far.id]


class WordModel:
    """Answers every text with the beach vector - or not at all."""

    def __init__(self, *, away: bool = False) -> None:
        self.away = away

    async def embed(self, inputs: Sequence[str]) -> list[list[float]]:
        if self.away:
            raise AiError("192.168.178.3 ist nicht erreichbar.")
        return [BEACH for _ in inputs]

    async def check(self) -> Check:
        return Check(ok=True, detail="", milliseconds=0)


async def signed_in(
    api_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> dict[str, str]:
    await create_user(session_factory, username="anna", display_name="Anna", role=UserRole.USER)
    return auth_header(await login(api_client, username="anna"))


async def machines(session: AsyncSession) -> None:
    for kind, model in ((AiKind.IMAGE_EMBEDDER, "siglip2"), (AiKind.TEXT_EMBEDDER, "bge-m3")):
        await ai_service.create_profile(
            session, kind=kind, name="GPU", base_url="http://gpu.invalid/v1", model=model
        )


@pytest.mark.parametrize("away", [False, True])
async def test_the_api_searches_and_says_what_it_understood(
    monkeypatch: pytest.MonkeyPatch,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
    api_client: AsyncClient,
    away: bool,
) -> None:
    await machines(session)
    await a_described(session, "A", "IMG_1.jpg", caption="Ein Strand.", picture=BEACH)
    limits: list[object] = []

    def embedder_for(_profile: object, **options: object) -> WordModel:
        limits.append(options.get("timeout_seconds"))
        return WordModel(away=away)

    monkeypatch.setattr(ai_service, "embedder_for", embedder_for)
    headers = await signed_in(api_client, session_factory)

    response = await api_client.post(
        "/search", json={"q": "Strand im Sommer 2012"}, headers=headers
    )

    body = response.json()
    assert response.status_code == 200
    assert body["understood"] == {
        "text": "Strand",
        "date_from": "2012-06-01",
        "date_until": "2012-09-01",
        "kind": None,
        "places": [],
        "persons": [],
    }
    assert [item["media"]["origin"]["filename"] for item in body["items"]] == ["IMG_1.jpg"]
    # Without the AI server the words still find it; the answer says the pictures were not asked.
    assert body["degraded"] is away
    # Somebody is waiting: the words become vectors quickly or not at all.
    assert limits == [engine.PROBE_TIMEOUT_SECONDS, engine.PROBE_TIMEOUT_SECONDS]


async def test_the_api_hands_out_pages(
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
    api_client: AsyncClient,
) -> None:
    for index in range(5):
        await a_described(session, "A", f"IMG_{index}.jpg", caption="Ein Strand.")
    headers = await signed_in(api_client, session_factory)

    first = (
        await api_client.post("/search", json={"q": "Strand", "limit": 3}, headers=headers)
    ).json()
    second = (
        await api_client.post(
            "/search",
            json={"q": "Strand", "limit": 3, "cursor": first["next_cursor"]},
            headers=headers,
        )
    ).json()

    assert len(first["items"]) == 3
    assert len(second["items"]) == 2
    assert second["next_cursor"] is None
    bad = await api_client.post("/search", json={"q": "x", "cursor": "nonsense"}, headers=headers)
    assert bad.status_code == 400


async def test_similar_pictures_through_the_api(
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
    api_client: AsyncClient,
) -> None:
    await machines(session)
    beach = await a_described(session, "A", "IMG_1.jpg", caption="a", picture=BEACH)
    await a_described(session, "A", "IMG_2.jpg", caption="b", picture=[1.0, 0.2, 0.0])
    headers = await signed_in(api_client, session_factory)

    body = (await api_client.get(f"/media/{beach.id}/similar", headers=headers)).json()

    assert [item["media"]["origin"]["filename"] for item in body["items"]] == ["IMG_2.jpg"]


async def test_the_app_learns_what_the_search_can_look_into(
    api_client: AsyncClient,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Without models only names, places and periods are searched; the app says so up front."""
    headers = await signed_in(api_client, session_factory)

    none = (await api_client.get("/search/abilities", headers=headers)).json()
    await ai_service.create_profile(
        session,
        kind=AiKind.IMAGE_EMBEDDER,
        name="GPU",
        base_url="http://gpu.invalid/v1",
        model="siglip2",
    )
    pictures = (await api_client.get("/search/abilities", headers=headers)).json()

    assert none == {"pictures": False, "meanings": False}
    assert pictures == {"pictures": True, "meanings": False}
    assert (await api_client.get("/search/abilities")).status_code == 401
