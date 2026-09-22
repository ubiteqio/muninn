"""The worker's own rules: locks that are always released, and a second look at waiting files."""

import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from muninn.huginn import jobs, tasks
from muninn.library import service
from muninn.models.change_log import SyncTrigger


@pytest.fixture
def fake_redis_client() -> object:
    from fakeredis import FakeAsyncRedis

    return FakeAsyncRedis(decode_responses=True)


async def test_a_failed_sync_frees_its_folder_again(
    monkeypatch: pytest.MonkeyPatch, fake_redis_client: object
) -> None:
    """A run that ends badly must not lock its folder away for an hour."""
    publication_id = uuid.uuid4()
    monkeypatch.setattr(jobs, "connect", lambda: fake_redis_client)

    async def explode(*_: object, **__: object) -> service.SyncReport:
        raise RuntimeError("the share went away mid-read")

    monkeypatch.setattr(tasks, "_run_sync", explode)

    with pytest.raises(RuntimeError):
        await tasks._sync(
            publication_id,
            quick=False,
            confirm_deletions=False,
            trigger=SyncTrigger.MANUAL,
            scope_path=None,
            with_children=True,
            job_id=None,
        )

    assert await fake_redis_client.get(jobs.lock_key(publication_id)) is None  # type: ignore[attr-defined]


async def test_a_second_request_is_folded_into_the_running_one(
    monkeypatch: pytest.MonkeyPatch, fake_redis_client: object
) -> None:
    publication_id = uuid.uuid4()
    monkeypatch.setattr(jobs, "connect", lambda: fake_redis_client)
    await jobs.acquire(fake_redis_client, publication_id)  # type: ignore[arg-type]

    answer = await tasks._sync(
        publication_id,
        quick=False,
        confirm_deletions=False,
        trigger=SyncTrigger.MANUAL,
        scope_path=None,
        with_children=True,
        job_id=None,
    )

    assert answer["status"] == "coalesced"
    assert await fake_redis_client.get(jobs.again_key(publication_id)) == "1"  # type: ignore[attr-defined]


async def test_a_medium_is_only_queued_once_per_stage(fake_redis_client: object) -> None:
    """A sync every minute must not re-queue a backlog the worker is still chewing on."""
    media_id = uuid.uuid4()

    first = await jobs.claim(fake_redis_client, "derive", media_id)  # type: ignore[arg-type]
    second = await jobs.claim(fake_redis_client, "derive", media_id)  # type: ignore[arg-type]

    assert (first, second) == (True, False)


async def test_a_finished_medium_can_be_queued_again(fake_redis_client: object) -> None:
    """Work that failed has to come back, so the claim goes when the task is done."""
    media_id = uuid.uuid4()
    await jobs.claim(fake_redis_client, "derive", media_id)  # type: ignore[arg-type]

    await jobs.release_claim(fake_redis_client, "derive", media_id)  # type: ignore[arg-type]

    assert await jobs.claim(fake_redis_client, "derive", media_id) is True  # type: ignore[arg-type]


async def test_the_stages_do_not_share_a_claim(fake_redis_client: object) -> None:
    media_id = uuid.uuid4()
    await jobs.claim(fake_redis_client, "derive", media_id)  # type: ignore[arg-type]

    assert await jobs.claim(fake_redis_client, "metadata", media_id) is True  # type: ignore[arg-type]


@pytest.mark.parametrize(("added", "announced"), [(1, True), (0, False)])
async def test_a_sync_that_changed_the_library_says_so_to_everybody(
    monkeypatch: pytest.MonkeyPatch, fake_redis_client: object, added: int, announced: bool
) -> None:
    """Albums and timeline reload on this; a sync that found nothing stays quiet."""
    from muninn.notify import events

    monkeypatch.setattr(jobs, "connect", lambda: fake_redis_client)
    heard: list[tuple[str, dict[str, object]]] = []

    async def publish(_redis: object, topic: str, **payload: object) -> None:
        heard.append((topic, payload))

    async def found(*_: object, **__: object) -> service.SyncReport:
        return service.SyncReport(added=added)

    monkeypatch.setattr(events, "publish", publish)
    monkeypatch.setattr(tasks, "_run_sync", found)

    await tasks._sync(
        uuid.uuid4(),
        quick=True,
        confirm_deletions=False,
        trigger=SyncTrigger.QUICK,
        scope_path=None,
        with_children=True,
        job_id=None,
    )

    assert (("library", {"kind": "changed"}) in heard) is announced
    # The admin-only topic never carries it: anybody signed in may hear "library".
    assert all(topic != "library" or payload == {"kind": "changed"} for topic, payload in heard)


async def test_a_starting_worker_frees_the_locks_a_stopped_one_left(
    fake_redis_client: object,
) -> None:
    """Otherwise every request for the folder is folded into a read that no longer exists."""
    stale = uuid.uuid4()
    await jobs.acquire(fake_redis_client, stale)  # type: ignore[arg-type]
    await jobs.request_again(fake_redis_client, stale)  # type: ignore[arg-type]

    await jobs.release_all(fake_redis_client)  # type: ignore[arg-type]

    assert await jobs.acquire(fake_redis_client, stale)  # type: ignore[arg-type]


@pytest.mark.usefixtures("api_client")
async def test_a_read_cut_off_by_a_restart_is_read_again(
    monkeypatch: pytest.MonkeyPatch,
    fake_redis_client: object,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    from contextlib import asynccontextmanager

    from muninn.models.publication import ScanStatus

    (tmp_path / "Fotos").mkdir()
    cut_off = await service.publish(session, relative_path="Fotos", library_base=tmp_path)
    cut_off.last_sync_status = ScanStatus.RUNNING
    await session.commit()
    await jobs.acquire(fake_redis_client, cut_off.id)  # type: ignore[arg-type]

    @asynccontextmanager
    async def scope() -> AsyncIterator[AsyncSession]:
        async with session_factory() as own:
            yield own

    queued: list[list[str]] = []
    monkeypatch.setattr(jobs, "connect", lambda: fake_redis_client)
    monkeypatch.setattr(tasks, "session_scope", scope)
    monkeypatch.setattr(
        tasks.sync_publication, "apply_async", lambda args, **_: queued.append(args)
    )

    await jobs.claim(fake_redis_client, "derive", cut_off.id)  # type: ignore[arg-type]
    assert await tasks.recover({"scan"}) == [str(cut_off.id)]
    assert queued == [[str(cut_off.id)]]
    assert await jobs.acquire(fake_redis_client, cut_off.id)  # type: ignore[arg-type]


async def test_a_starting_worker_frees_only_the_claims_of_its_own_queues(
    monkeypatch: pytest.MonkeyPatch, fake_redis_client: object
) -> None:
    """The preview worker must not hand out again what the AI worker is on right now."""
    media_id = uuid.uuid4()
    monkeypatch.setattr(jobs, "connect", lambda: fake_redis_client)
    await jobs.claim(fake_redis_client, "derive", media_id)  # type: ignore[arg-type]
    await jobs.claim(fake_redis_client, jobs.ANALYSIS_STAGE, media_id)  # type: ignore[arg-type]
    await jobs.acquire(fake_redis_client, media_id)  # type: ignore[arg-type]

    assert await tasks.recover({"derive"}) == []

    assert await jobs.claim(fake_redis_client, "derive", media_id)  # type: ignore[arg-type]
    assert not await jobs.claim(fake_redis_client, jobs.ANALYSIS_STAGE, media_id)  # type: ignore[arg-type]
    # Reads are the reading worker's business.
    assert not await jobs.acquire(fake_redis_client, media_id)  # type: ignore[arg-type]
