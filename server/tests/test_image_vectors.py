"""Stage 4: the picture model looks at every thumbnail once, and the clock keeps it fed."""

import uuid
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from muninn.ai import service as ai_service
from muninn.ai.base import AiError, Check
from muninn.core.config import get_settings
from muninn.huginn import jobs, tasks
from muninn.models.ai import AiKind
from muninn.models.media import Media
from muninn.search import service
from tests.test_timeline import JULY, a_medium, an_album

pytestmark = pytest.mark.usefixtures("api_client")


class FakeEmbedder:
    """Answers with a fixed vector and remembers what it was shown."""

    def __init__(self, *, fails: bool = False) -> None:
        self.inputs: list[str] = []
        self.fails = fails
        self.asked = 0

    async def embed(self, inputs: Sequence[str]) -> list[list[float]]:
        self.asked += 1
        if self.fails:
            raise AiError("192.168.178.3 ist nicht erreichbar.")
        self.inputs.extend(inputs)
        return [[0.25] * 8 for _ in inputs]

    async def check(self) -> Check:
        return Check(ok=True, detail="", milliseconds=0, dimensions=8)


@pytest.fixture
def fake_redis_client() -> object:
    from fakeredis import FakeAsyncRedis

    return FakeAsyncRedis(decode_responses=True)


async def a_medium_with_thumbnail(session: AsyncSession, derived: Path) -> Media:
    album = await an_album(session, "Fotos")
    medium = await a_medium(session, album, taken_at=JULY, name="IMG_1.jpg")
    medium.thumbnail_path = f"{medium.id.hex[:2]}/{medium.id.hex}/thumb-1.webp"
    thumbnail = derived / medium.thumbnail_path
    thumbnail.parent.mkdir(parents=True)
    thumbnail.write_bytes(b"RIFF-not-really-a-webp")
    await session.commit()
    return medium


async def vectors(session: AsyncSession) -> int:
    return int(await session.scalar(text("SELECT count(*) FROM image_embeddings")) or 0)


async def test_the_thumbnail_is_what_the_model_sees(session: AsyncSession, tmp_path: Path) -> None:
    medium = await a_medium_with_thumbnail(session, tmp_path)
    embedder = FakeEmbedder()

    stored = await service.apply_image_vector(
        session, medium.id, embedder=embedder, model="siglip2", derived_root=tmp_path
    )

    assert stored is True
    assert embedder.inputs[0].startswith("data:image/webp;base64,")
    assert await vectors(session) == 1


async def test_a_medium_with_a_vector_is_not_asked_again(
    session: AsyncSession, tmp_path: Path
) -> None:
    medium = await a_medium_with_thumbnail(session, tmp_path)
    await service.apply_image_vector(
        session, medium.id, embedder=FakeEmbedder(), model="siglip2", derived_root=tmp_path
    )
    embedder = FakeEmbedder()

    stored = await service.apply_image_vector(
        session, medium.id, embedder=embedder, model="siglip2", derived_root=tmp_path
    )

    assert stored is False
    assert embedder.inputs == []


async def test_a_thumbnail_that_is_gone_is_left_to_stage_3(
    session: AsyncSession, tmp_path: Path
) -> None:
    medium = await a_medium_with_thumbnail(session, tmp_path)
    assert medium.thumbnail_path is not None
    (tmp_path / medium.thumbnail_path).unlink()

    stored = await service.apply_image_vector(
        session, medium.id, embedder=FakeEmbedder(), model="siglip2", derived_root=tmp_path
    )

    assert stored is False
    assert await vectors(session) == 0


@pytest.fixture
def worker_database(
    monkeypatch: pytest.MonkeyPatch,
    session_factory: async_sessionmaker[AsyncSession],
    fake_redis_client: object,
) -> list[str]:
    """The worker's database and Redis are the test's; returns what it put into the queue."""

    @asynccontextmanager
    async def scope() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    queued: list[str] = []
    monkeypatch.setattr(tasks, "session_scope", scope)
    monkeypatch.setattr(jobs, "connect", lambda: fake_redis_client)
    monkeypatch.setattr(tasks.embed_image, "delay", queued.append)
    return queued


async def a_picture_model(session: AsyncSession) -> None:
    await ai_service.create_profile(
        session,
        kind=AiKind.IMAGE_EMBEDDER,
        name="GPU",
        base_url="http://gpu.invalid/v1",
        model="siglip2",
    )


async def test_nothing_is_queued_without_a_picture_model(
    session: AsyncSession, tmp_path: Path, worker_database: list[str], fake_redis_client: object
) -> None:
    await a_medium_with_thumbnail(session, tmp_path)

    assert await tasks._queue_ai_work(fake_redis_client) == 0  # type: ignore[arg-type]
    assert worker_database == []


async def test_the_clock_queues_each_medium_once(
    session: AsyncSession, tmp_path: Path, worker_database: list[str], fake_redis_client: object
) -> None:
    """The backlog stays in the database while the queue works; a minute later it is not doubled."""
    medium = await a_medium_with_thumbnail(session, tmp_path)
    await a_picture_model(session)

    first = await tasks._queue_ai_work(fake_redis_client)  # type: ignore[arg-type]
    second = await tasks._queue_ai_work(fake_redis_client)  # type: ignore[arg-type]

    assert (first, second) == (1, 0)
    assert worker_database == [str(medium.id)]


async def test_a_machine_that_is_away_costs_one_line_and_comes_back(
    monkeypatch: pytest.MonkeyPatch,
    session: AsyncSession,
    tmp_path: Path,
    worker_database: list[str],
    fake_redis_client: object,
) -> None:
    """No vector, no traceback, and the claim is free so the next minute asks again."""
    medium = await a_medium_with_thumbnail(session, tmp_path)
    await a_picture_model(session)
    away = FakeEmbedder(fails=True)
    monkeypatch.setattr(ai_service, "embedder_for", lambda _profile: away)
    settings = get_settings().model_copy(update={"derived_path": tmp_path})
    monkeypatch.setattr(tasks, "get_settings", lambda: settings)
    await jobs.claim(fake_redis_client, jobs.IMAGE_VECTOR_STAGE, medium.id)  # type: ignore[arg-type]

    done = await tasks._embed_image(medium.id, task_id=str(uuid.uuid4()))

    assert done is False
    assert away.asked == 1
    assert await vectors(session) == 0
    assert await jobs.claim(fake_redis_client, jobs.IMAGE_VECTOR_STAGE, medium.id)  # type: ignore[arg-type]


async def test_a_machine_that_does_not_answer_at_all_pauses_its_stage(
    monkeypatch: pytest.MonkeyPatch,
    session: AsyncSession,
    tmp_path: Path,
    worker_database: list[str],
    fake_redis_client: object,
) -> None:
    """Instead of failing every medium within milliseconds, a thousand a minute."""
    from muninn.ai.base import AiUnreachableError

    medium = await a_medium_with_thumbnail(session, tmp_path)
    await a_picture_model(session)

    class Off:
        async def embed(self, inputs: Sequence[str]) -> list[list[float]]:
            raise AiUnreachableError("192.168.178.3 ist nicht erreichbar.")

    monkeypatch.setattr(ai_service, "embedder_for", lambda _profile: Off())
    settings = get_settings().model_copy(update={"derived_path": tmp_path})
    monkeypatch.setattr(tasks, "get_settings", lambda: settings)

    await tasks._embed_image(medium.id, task_id=str(uuid.uuid4()))

    assert await tasks._queue_ai_work(fake_redis_client) == 0  # type: ignore[arg-type]
    assert worker_database == []
    # Once the pause is over, the clock asks again.
    await fake_redis_client.delete(jobs.pause_key(jobs.IMAGE_VECTOR_STAGE))  # type: ignore[attr-defined]
    assert await tasks._queue_ai_work(fake_redis_client) == 1  # type: ignore[arg-type]


async def test_the_clock_hands_out_descriptions_once_a_describing_model_is_there(
    monkeypatch: pytest.MonkeyPatch,
    session: AsyncSession,
    tmp_path: Path,
    worker_database: list[str],
    fake_redis_client: object,
) -> None:
    medium = await a_medium_with_thumbnail(session, tmp_path)
    medium.preview_path = medium.thumbnail_path
    await session.commit()
    described: list[str] = []
    monkeypatch.setattr(tasks.analyze_media, "delay", described.append)

    await ai_service.create_profile(
        session, kind=AiKind.ANALYZER, name="GPU", base_url="http://gpu.invalid/v1", model="qwen"
    )
    await tasks._queue_ai_work(fake_redis_client)  # type: ignore[arg-type]

    assert described == [str(medium.id)]
    # No picture model set up: stage 4 waits, stage 5 does not wait for it.
    assert worker_database == []
