"""What the admin area shows about the work in progress."""

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from muninn.huginn import jobs
from muninn.library import service
from muninn.models.user import UserRole
from tests.helpers import auth_header, create_user, login

pytestmark = pytest.mark.usefixtures("api_client")


@pytest.fixture
def library(tmp_path: Path, api_app: FastAPI) -> Path:
    base = tmp_path / "library"
    base.mkdir()
    api_app.state.settings = api_app.state.settings.model_copy(update={"library_path": base})
    return base


async def admin_headers(
    api_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> dict[str, str]:
    await create_user(session_factory, username="admin", display_name="Admin", role=UserRole.ADMIN)
    return auth_header(await login(api_client, username="admin"))


async def test_only_admins_may_look(
    api_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await create_user(session_factory, username="anna", display_name="Anna")
    headers = auth_header(await login(api_client, username="anna"))

    assert (await api_client.get("/admin/jobs", headers=headers)).status_code == 403
    assert (await api_client.get("/admin/jobs")).status_code == 401


async def test_an_idle_muninn_says_so(
    api_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    headers = await admin_headers(api_client, session_factory)

    response = await api_client.get("/admin/jobs", headers=headers)

    body = response.json()
    assert body["running"] == []
    assert {queue["name"] for queue in body["queues"]} == {"scan", "derive", "ai", "people"}
    assert all(queue["waiting"] == 0 for queue in body["queues"])
    assert body["pending_derivatives"] == 0
    # No picture model set up: there is no backlog to speak of, not an empty one.
    assert body["pending_image_vectors"] is None
    assert body["pending_transcripts"] is None
    assert body["pending_analyses"] is None
    assert body["pending_caption_vectors"] is None
    # Nothing has ever run, so there is nothing to report about it either.
    assert body["last_read_at"] is None
    assert body["media"] == 0


async def test_a_running_read_is_shown_with_its_progress(
    api_client: AsyncClient,
    api_app: FastAPI,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
    library: Path,
) -> None:
    (library / "Fotos").mkdir()
    publication = await service.publish(session, relative_path="Fotos", library_base=library)
    await jobs.acquire(api_app.state.redis, publication.id)
    await jobs.write_progress(
        api_app.state.redis,
        publication.id,
        {"files_total": 684, "files_done": 120, "current": "Fotos/Tag 1"},
    )
    headers = await admin_headers(api_client, session_factory)

    response = await api_client.get("/admin/jobs", headers=headers)

    running = response.json()["running"][0]
    assert running["name"] == "Fotos"
    assert running["progress"]["files_done"] == 120
    assert running["progress"]["current"] == "Fotos/Tag 1"


async def test_the_queues_say_how_much_is_left(
    api_client: AsyncClient,
    api_app: FastAPI,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Celery keeps one list per queue, which is what "how much is left" means."""
    await api_app.state.redis.rpush("derive", "a-task", "another-task")
    headers = await admin_headers(api_client, session_factory)

    response = await api_client.get("/admin/jobs", headers=headers)

    queues = {queue["name"]: queue["waiting"] for queue in response.json()["queues"]}
    assert queues["derive"] == 2
    assert queues["scan"] == 0


async def test_it_says_when_the_clock_comes_around(
    api_client: AsyncClient,
    api_app: FastAPI,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await api_app.state.redis.set(jobs.LAST_QUICK_KEY, "2026-09-20T12:00:00+00:00")
    headers = await admin_headers(api_client, session_factory)

    response = await api_client.get("/admin/jobs", headers=headers)

    schedule = response.json()["schedule"]
    assert schedule["next_quick_sync_at"].startswith("2026-09-20T12:05:00")
    assert schedule["stability_seconds"] == 30

    # The nightly read is due at the configured hour in the installation's own time zone, and
    # always in the future - whatever day the test runs on.
    next_full = datetime.fromisoformat(schedule["next_full_sync_at"])
    assert next_full.hour == 3
    assert next_full > datetime.now().astimezone()


async def test_waiting_files_are_counted(
    api_client: AsyncClient,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
    library: Path,
) -> None:
    from muninn.models.pending_file import PendingFile

    (library / "Fotos").mkdir()
    await service.publish(session, relative_path="Fotos", library_base=library)
    session.add(
        PendingFile(
            relative_path="Fotos/IMG_1.jpg",
            byte_size=10,
            modified_at=datetime.now(UTC),
            first_seen_at=datetime.now(UTC),
        )
    )
    await session.commit()
    headers = await admin_headers(api_client, session_factory)

    response = await api_client.get("/admin/jobs", headers=headers)

    assert response.json()["waiting_files"] == 1


async def test_work_too_quick_to_catch_is_still_shown(
    api_client: AsyncClient,
    api_app: FastAPI,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A preview takes about a tenth of a second, so only what was just finished proves it ran."""
    redis = api_app.state.redis
    await jobs.note_finished(redis, "task-1", "metadata", uuid.uuid4())
    await jobs.note_finished(redis, "task-2", "derive", uuid.uuid4())
    headers = await admin_headers(api_client, session_factory)

    body = (await api_client.get("/admin/jobs", headers=headers)).json()

    # Newest first, and counted per stage for the minute behind us.
    assert [task["stage"] for task in body["finished"]] == ["derive", "metadata"]
    assert body["done_last_minute"] == {
        "metadata": 1,
        "derive": 1,
        "image_vector": 0,
        "transcription": 0,
        "analysis": 0,
        "caption_vector": 0,
        "faces": 0,
    }


async def test_a_failure_is_listed_as_one_and_not_counted_as_done(
    api_client: AsyncClient,
    api_app: FastAPI,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A description that ran into the AI server's time limit is no description."""
    from tests.test_timeline import JULY, a_medium, an_album

    album = await an_album(session, "Events/Konzert")
    medium = await a_medium(session, album, taken_at=JULY, name="IMG_1.jpg")
    await session.commit()
    redis = api_app.state.redis
    await jobs.note_finished(redis, "task-1", jobs.ANALYSIS_STAGE, medium.id, failed=True)
    headers = await admin_headers(api_client, session_factory)

    body = (await api_client.get("/admin/jobs", headers=headers)).json()

    (entry,) = body["finished"]
    assert entry["failed"] is True
    assert entry["label"] == "IMG_1.jpg"
    # Enough to lead to the picture and its album.
    assert entry["media"] == {
        "id": str(medium.id),
        "kind": "image",
        "album_id": str(album.id),
        "album_path": "Events/Konzert",
    }
    assert body["done_last_minute"][jobs.ANALYSIS_STAGE] == 0


async def test_only_the_last_few_finished_pieces_are_kept(
    api_client: AsyncClient,
    api_app: FastAPI,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    redis = api_app.state.redis
    for number in range(jobs.FINISHED_KEEP + 5):
        await jobs.note_finished(redis, f"task-{number}", "derive")
    headers = await admin_headers(api_client, session_factory)

    body = (await api_client.get("/admin/jobs", headers=headers)).json()

    assert len(body["finished"]) == jobs.FINISHED_KEEP
    # Every one of them still counts towards the minute, however few are kept by name.
    assert body["done_last_minute"]["derive"] == jobs.FINISHED_KEEP + 5


async def test_what_fell_out_of_the_window_is_not_counted(
    api_client: AsyncClient,
    api_app: FastAPI,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    redis = api_app.state.redis
    long_ago = (datetime.now(UTC) - timedelta(minutes=5)).timestamp()
    await redis.zadd(jobs.done_key("derive"), {"task-old": long_ago})
    headers = await admin_headers(api_client, session_factory)

    body = (await api_client.get("/admin/jobs", headers=headers)).json()

    assert body["done_last_minute"]["derive"] == 0


async def test_an_unknown_publication_does_not_break_the_answer(
    api_client: AsyncClient,
    api_app: FastAPI,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A lock left behind by a folder that is gone must not show up as work."""
    await jobs.acquire(api_app.state.redis, uuid.uuid4())
    headers = await admin_headers(api_client, session_factory)

    response = await api_client.get("/admin/jobs", headers=headers)

    assert response.json()["running"] == []


async def test_an_idle_engine_room_still_says_what_just_happened(
    api_client: AsyncClient,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
    library: Path,
) -> None:
    """Work can be over before somebody looks; "nothing running" must not mean "nothing ever"."""
    (library / "Fotos").mkdir()
    publication = await service.publish(session, relative_path="Fotos", library_base=library)
    publication.last_sync_at = datetime(2026, 9, 20, 19, 23, tzinfo=UTC)
    await session.commit()
    headers = await admin_headers(api_client, session_factory)

    response = await api_client.get("/admin/jobs", headers=headers)

    assert response.json()["last_read_at"].startswith("2026-09-20T19:23:00")


class TestStopping:
    async def test_an_admin_can_stop_a_running_read(
        self,
        api_client: AsyncClient,
        api_app: FastAPI,
        session: AsyncSession,
        session_factory: async_sessionmaker[AsyncSession],
        library: Path,
    ) -> None:
        """The read stops between folders, so what it already read is kept."""
        (library / "Fotos").mkdir()
        publication = await service.publish(session, relative_path="Fotos", library_base=library)
        headers = await admin_headers(api_client, session_factory)

        response = await api_client.delete(f"/admin/jobs/reads/{publication.id}", headers=headers)

        assert response.status_code == 202
        assert await jobs.cancel_requested(api_app.state.redis, publication.id) is True

    async def test_a_stopped_read_keeps_what_it_read(
        self, session: AsyncSession, library: Path
    ) -> None:
        from muninn.settings import service as settings_service

        (library / "Fotos").mkdir()
        (library / "Fotos" / "IMG_1.jpg").write_bytes(b"bild")
        publication = await service.publish(session, relative_path="Fotos", library_base=library)
        settings = await settings_service.get_settings(session)

        async def stop_now() -> bool:
            return True

        report = await service.sync_publication(
            session,
            publication,
            settings=settings,
            library_base=library,
            should_stop=stop_now,
        )

        assert report.status.value == "cancelled"
        assert publication.last_sync_status.value == "cancelled"
        assert "Stopped by an admin" in (report.message or "")

    async def test_emptying_a_queue_says_what_it_threw_away(
        self,
        api_client: AsyncClient,
        api_app: FastAPI,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        await api_app.state.redis.rpush("derive", "a", "b", "c")
        media_id = uuid.uuid4()
        await jobs.claim(api_app.state.redis, "derive", media_id)
        headers = await admin_headers(api_client, session_factory)

        response = await api_client.delete("/admin/jobs/queues/derive", headers=headers)

        assert response.json() == {"name": "derive", "removed": 3}
        # The media may be queued again straight away; nothing is lost for good.
        assert await jobs.claim(api_app.state.redis, "derive", media_id) is True

    async def test_an_unknown_queue_is_a_problem(
        self, api_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        headers = await admin_headers(api_client, session_factory)

        response = await api_client.delete("/admin/jobs/queues/nonsense", headers=headers)

        assert response.status_code == 404
        assert response.json()["type"].endswith("queue-not-found")

    async def test_a_plain_user_may_not_stop_anything(
        self, api_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        await create_user(session_factory, username="anna", display_name="Anna")
        headers = auth_header(await login(api_client, username="anna"))

        assert (
            await api_client.delete(f"/admin/jobs/reads/{uuid.uuid4()}", headers=headers)
        ).status_code == 403
        assert (
            await api_client.delete("/admin/jobs/queues/derive", headers=headers)
        ).status_code == 403


class TestUnpublishing:
    """Taking a folder out of the albums also takes the work on it out of the queues."""

    async def test_it_asks_a_running_read_to_stop(
        self,
        api_client: AsyncClient,
        api_app: FastAPI,
        session: AsyncSession,
        session_factory: async_sessionmaker[AsyncSession],
        library: Path,
    ) -> None:
        (library / "Fotos").mkdir()
        publication = await service.publish(session, relative_path="Fotos", library_base=library)
        await jobs.write_progress(
            api_app.state.redis,
            publication.id,
            {"files_total": 40, "files_done": 12, "current": "IMG_1.jpg"},
        )
        headers = await admin_headers(api_client, session_factory)

        response = await api_client.delete(
            f"/admin/library/publications/{publication.id}", headers=headers
        )

        assert response.status_code == 204
        assert await jobs.cancel_requested(api_app.state.redis, publication.id) is True
        # Nothing is running any more, so nothing should be shown as running either.
        assert await jobs.read_progress(api_app.state.redis, publication.id) is None

    async def test_a_read_stops_when_its_folder_is_taken_out(
        self, session: AsyncSession, library: Path
    ) -> None:
        """Between folders the read looks whether its folder is still published."""
        from sqlalchemy import delete

        from muninn.models.publication import Publication
        from muninn.settings import service as settings_service

        for name in ("A", "B"):
            (library / "Fotos" / name).mkdir(parents=True)
            (library / "Fotos" / name / "IMG.jpg").write_bytes(b"bild")
        publication = await service.publish(session, relative_path="Fotos", library_base=library)
        publication_id = publication.id
        settings = await settings_service.get_settings(session)

        async def unpublish_meanwhile(progress: service.SyncProgress) -> None:
            await session.execute(delete(Publication).where(Publication.id == publication_id))
            await session.commit()

        report = await service.sync_publication(
            session,
            publication,
            settings=settings,
            library_base=library,
            on_progress=unpublish_meanwhile,
        )

        assert report.status.value == "cancelled"
        assert "no longer published" in (report.message or "")

    async def test_the_media_are_not_left_claimed(
        self,
        api_client: AsyncClient,
        api_app: FastAPI,
        session: AsyncSession,
        session_factory: async_sessionmaker[AsyncSession],
        library: Path,
    ) -> None:
        """A claim says 'already queued'. For media that are gone it would say so for an hour."""
        from muninn.settings import service as settings_service

        (library / "Fotos").mkdir()
        (library / "Fotos" / "IMG_1.jpg").write_bytes(b"bild")
        publication = await service.publish(session, relative_path="Fotos", library_base=library)
        settings = await settings_service.get_settings(session)
        # Two listings, far enough apart: only then is a file taken.
        first = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)
        await service.sync_publication(
            session, publication, settings=settings, library_base=library, now=first
        )
        report = await service.sync_publication(
            session,
            publication,
            settings=settings,
            library_base=library,
            now=first + timedelta(minutes=1),
        )
        media_id = report.pending_derivatives[0]
        await jobs.claim(api_app.state.redis, "derive", media_id)
        headers = await admin_headers(api_client, session_factory)

        response = await api_client.delete(
            f"/admin/library/publications/{publication.id}", headers=headers
        )

        assert response.status_code == 204
        assert await jobs.claim(api_app.state.redis, "derive", media_id) is True
