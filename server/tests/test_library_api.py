"""The library over HTTP: published folders, albums and media."""

import os
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from muninn.api.v1 import albums as albums_router
from muninn.api.v1 import library as library_router
from muninn.huginn import jobs
from muninn.huginn.dispatch import WorkerUnreachableError
from muninn.library import service
from muninn.models.change_log import SyncTrigger
from muninn.models.user import UserRole
from muninn.settings import service as settings_service
from tests.helpers import auth_header, create_user, login

pytestmark = pytest.mark.usefixtures("api_client")

NOW = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)
LATER = NOW + timedelta(minutes=1)


def write(root: Path, relative_path: str, content: bytes = b"bild") -> Path:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    stamp = (NOW - timedelta(days=1)).timestamp()
    os.utime(path, (stamp, stamp))
    return path


@pytest.fixture
def library(tmp_path: Path, api_app: FastAPI) -> Path:
    """What the host mounts, with the app pointed at it."""
    base = tmp_path / "library"
    base.mkdir()
    api_app.state.settings = api_app.state.settings.model_copy(update={"library_path": base})
    return base


@pytest.fixture(autouse=True)
def no_worker(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Catches what the API would hand to Huginn.

    Always on: without it a test would put real tasks into whatever Redis the developer happens
    to be running, and wait for it.
    """
    queued: list[dict[str, Any]] = []

    def fake_queue(publication_id: uuid.UUID, **kwargs: Any) -> str:
        queued.append({"publication_id": publication_id, **kwargs})
        return "task-1"

    monkeypatch.setattr(library_router, "queue_sync", fake_queue)
    monkeypatch.setattr(albums_router, "queue_sync", fake_queue)
    return queued


async def admin_headers(
    api_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> dict[str, str]:
    await create_user(session_factory, username="admin", display_name="Admin", role=UserRole.ADMIN)
    return auth_header(await login(api_client, username="admin"))


async def user_headers(
    api_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> dict[str, str]:
    await create_user(session_factory, username="anna", display_name="Anna")
    return auth_header(await login(api_client, username="anna"))


async def published(session: AsyncSession, library: Path, relative_path: str) -> None:
    """A folder published and read, the way the worker would leave it."""
    publication = await service.publish(session, relative_path=relative_path, library_base=library)
    settings = await settings_service.get_settings(session)
    # Two listings, far enough apart: only then is a file taken, as the concept demands.
    await service.sync_publication(
        session, publication, settings=settings, library_base=library, now=NOW
    )
    report = await service.sync_publication(
        session, publication, settings=settings, library_base=library, now=LATER
    )
    for media_id in report.pending_metadata:
        await service.apply_metadata(session, media_id, library_base=library)


class TestPublishing:
    async def test_only_admins_may_look(
        self, api_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        headers = await user_headers(api_client, session_factory)

        response = await api_client.get("/admin/library/publications", headers=headers)

        assert response.status_code == 403
        assert (await api_client.get("/admin/library/publications")).status_code == 401

    async def test_an_admin_publishes_a_folder(
        self,
        api_client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
        library: Path,
        no_worker: list[dict[str, Any]],
    ) -> None:
        write(library, "Urlaub/Brasilien/IMG_1.jpg")
        headers = await admin_headers(api_client, session_factory)

        created = await api_client.post(
            "/admin/library/publications", json={"path": "Urlaub/Brasilien"}, headers=headers
        )

        assert created.status_code == 201
        # Reading starts at once: publishing is the moment somebody wants to see the folder.
        assert no_worker[0]["trigger"] is SyncTrigger.MANUAL
        assert created.json()["name"] == "Brasilien"
        assert created.json()["last_sync_status"] == "never"
        listed = await api_client.get("/admin/library/publications", headers=headers)
        assert [entry["relative_path"] for entry in listed.json()] == ["Urlaub/Brasilien"]

    async def test_the_mounted_folder_itself_can_be_published(
        self,
        api_client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
        library: Path,
    ) -> None:
        """Pictures often lie in the share itself; an empty path means exactly that folder."""
        write(library, "IMG_1.jpg")
        headers = await admin_headers(api_client, session_factory)

        response = await api_client.post(
            "/admin/library/publications", json={"path": ""}, headers=headers
        )

        assert response.status_code == 201
        assert response.json()["relative_path"] == ""

    async def test_publishing_twice_is_refused(
        self,
        api_client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
        library: Path,
    ) -> None:
        write(library, "Fotos/2009/IMG_1.jpg")
        headers = await admin_headers(api_client, session_factory)
        await api_client.post(
            "/admin/library/publications", json={"path": "Fotos"}, headers=headers
        )

        response = await api_client.post(
            "/admin/library/publications", json={"path": "Fotos/2009"}, headers=headers
        )

        assert response.status_code == 409
        assert response.json()["type"].endswith("already-published")

    async def test_a_folder_outside_the_library_is_refused(
        self,
        api_client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
        library: Path,
    ) -> None:
        headers = await admin_headers(api_client, session_factory)

        response = await api_client.post(
            "/admin/library/publications", json={"path": "../.."}, headers=headers
        )

        assert response.status_code == 400
        assert response.json()["type"].endswith("path-not-allowed")

    async def test_browsing_says_what_is_published_and_where_the_mount_is(
        self,
        api_client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
        library: Path,
    ) -> None:
        (library / "Fotos").mkdir()
        (library / "Videos").mkdir()
        headers = await admin_headers(api_client, session_factory)
        await api_client.post(
            "/admin/library/publications", json={"path": "Fotos"}, headers=headers
        )

        response = await api_client.get("/admin/library/browse", headers=headers)

        body = response.json()
        entries = {entry["name"]: entry for entry in body["items"]}
        assert entries["Fotos"]["published"] is True
        assert entries["Videos"]["published"] is False
        assert body["current"]["relative_path"] == ""
        assert body["library_path"].endswith("library")

    async def test_a_sync_is_handed_to_the_worker(
        self,
        api_client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
        session: AsyncSession,
        library: Path,
        no_worker: list[dict[str, Any]],
    ) -> None:
        write(library, "Fotos/IMG_1.jpg")
        await published(session, library, "Fotos")
        entry = (await service.list_publications(session))[0]
        headers = await admin_headers(api_client, session_factory)

        response = await api_client.post(
            f"/admin/library/publications/{entry.id}/sync", json={"quick": True}, headers=headers
        )

        assert response.status_code == 202
        assert no_worker[0]["publication_id"] == entry.id
        assert no_worker[0]["trigger"] is SyncTrigger.MANUAL

    async def test_without_a_worker_the_admin_is_told(
        self,
        api_client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
        session: AsyncSession,
        library: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        write(library, "Fotos/IMG_1.jpg")
        await published(session, library, "Fotos")
        entry = (await service.list_publications(session))[0]
        headers = await admin_headers(api_client, session_factory)

        def refuse(*_: object, **__: object) -> str:
            raise WorkerUnreachableError

        monkeypatch.setattr(library_router, "queue_sync", refuse)
        response = await api_client.post(
            f"/admin/library/publications/{entry.id}/sync", json={}, headers=headers
        )

        assert response.status_code == 503

    async def test_unpublishing_takes_the_albums_with_it(
        self,
        api_client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
        session: AsyncSession,
        library: Path,
    ) -> None:
        write(library, "Urlaub/Brasilien/IMG_1.jpg")
        await published(session, library, "Urlaub/Brasilien")
        entry = (await service.list_publications(session))[0]
        headers = await admin_headers(api_client, session_factory)

        response = await api_client.delete(
            f"/admin/library/publications/{entry.id}", headers=headers
        )

        assert response.status_code == 204
        tree = await api_client.get("/albums/tree", headers=headers)
        assert tree.json()["items"] == []

    async def test_the_status_counts_what_was_read(
        self,
        api_client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
        session: AsyncSession,
        library: Path,
    ) -> None:
        write(library, "Fotos/IMG_1.jpg")
        write(library, "Fotos/IMG_2.jpg", b"zwei")
        await published(session, library, "Fotos")
        headers = await admin_headers(api_client, session_factory)

        response = await api_client.get("/admin/index/status", headers=headers)

        body = response.json()
        assert body["media"] == 2
        assert body["albums"] == 1
        assert body["pending_metadata"] == 0
        assert body["publications"][0]["last_sync_status"] == "ok"


class TestExcludedFolders:
    async def test_a_subfolder_is_switched_off_and_on_again(
        self,
        api_client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
        session: AsyncSession,
        library: Path,
        no_worker: list[dict[str, Any]],
    ) -> None:
        write(library, "Events/FCB/IMG_1.jpg")
        write(library, "Events/FCB/2019/IMG_2.jpg", b"zwei")
        write(library, "Events/Hochzeit/IMG_3.jpg", b"drei")
        await published(session, library, "Events")
        entry = (await service.list_publications(session))[0]
        headers = await admin_headers(api_client, session_factory)

        # The published folder can be opened: its subfolders say where they belong.
        listing = (
            await api_client.get(
                "/admin/library/browse", params={"path": "Events"}, headers=headers
            )
        ).json()
        assert listing["current"]["is_publication"] is True
        assert {item["name"]: item["published"] for item in listing["items"]} == {
            "FCB": True,
            "Hochzeit": True,
        }
        assert {item["publication_id"] for item in listing["items"]} == {str(entry.id)}

        off = await api_client.post(
            f"/admin/library/publications/{entry.id}/exclusions",
            json={"relative_path": "Events/FCB"},
            headers=headers,
        )

        assert off.status_code == 200
        assert off.json()["excluded_paths"] == ["Events/FCB"]
        tree = (await api_client.get("/albums/tree", headers=headers)).json()["items"]
        assert sorted(album["relative_path"] for album in tree) == ["Events", "Events/Hochzeit"]
        listing = (
            await api_client.get(
                "/admin/library/browse", params={"path": "Events/FCB"}, headers=headers
            )
        ).json()
        assert (listing["current"]["published"], listing["current"]["excluded"]) == (False, True)
        assert [item["excluded"] for item in listing["items"]] == [True]

        # A read leaves it out.
        settings = await settings_service.get_settings(session)
        await session.refresh(entry)
        await service.sync_publication(
            session, entry, settings=settings, library_base=library, now=LATER
        )
        tree = (await api_client.get("/albums/tree", headers=headers)).json()["items"]
        assert "Events/FCB" not in [album["relative_path"] for album in tree]

        on = await api_client.delete(
            f"/admin/library/publications/{entry.id}/exclusions",
            params={"path": "Events/FCB"},
            headers=headers,
        )
        assert on.json()["excluded_paths"] == []
        assert no_worker[-1]["publication_id"] == entry.id

    async def test_only_folders_below_can_be_switched_off(
        self,
        api_client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
        session: AsyncSession,
        library: Path,
    ) -> None:
        write(library, "Events/FCB/IMG_1.jpg")
        write(library, "Andere/IMG_2.jpg", b"zwei")
        await published(session, library, "Events")
        entry = (await service.list_publications(session))[0]
        headers = await admin_headers(api_client, session_factory)

        for path in ("Events", "Andere"):
            response = await api_client.post(
                f"/admin/library/publications/{entry.id}/exclusions",
                json={"relative_path": path},
                headers=headers,
            )
            assert response.status_code == 422


class TestAlbums:
    async def test_the_tree_mirrors_the_folders(
        self,
        api_client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
        session: AsyncSession,
        library: Path,
    ) -> None:
        """The album sits where the original sits, so it is found where one expects."""
        write(library, "Urlaub/Brasilien 2026/Boris/IMG_1.jpg")
        write(library, "Urlaub/Brasilien 2026/Boris/Tag 2/IMG_2.jpg", b"zwei")
        await published(session, library, "Urlaub/Brasilien 2026/Boris")
        headers = await user_headers(api_client, session_factory)

        response = await api_client.get("/albums/tree", headers=headers)

        items = {item["relative_path"]: item for item in response.json()["items"]}
        assert set(items) == {
            "Urlaub",
            "Urlaub/Brasilien 2026",
            "Urlaub/Brasilien 2026/Boris",
            "Urlaub/Brasilien 2026/Boris/Tag 2",
        }
        assert items["Urlaub"]["is_source"] is False
        assert items["Urlaub"]["media_count"] == 0
        assert items["Urlaub/Brasilien 2026/Boris"]["is_source"] is True
        assert items["Urlaub/Brasilien 2026/Boris"]["media_count"] == 1

    async def test_an_album_can_be_given_its_own_title(
        self,
        api_client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
        session: AsyncSession,
        library: Path,
    ) -> None:
        write(library, "Fotos/IMG_1.jpg")
        await published(session, library, "Fotos")
        headers = await user_headers(api_client, session_factory)
        tree = await api_client.get("/albums/tree", headers=headers)
        album = tree.json()["items"][0]

        response = await api_client.patch(
            f"/albums/{album['id']}", json={"title": "Italien mit Oma"}, headers=headers
        )

        assert response.json()["title"] == "Italien mit Oma"
        assert response.json()["name"] == "Fotos"

    async def test_the_media_come_oldest_first_in_pages(
        self,
        api_client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
        session: AsyncSession,
        library: Path,
    ) -> None:
        write(library, "Fotos/IMG_20090714_120000.jpg", b"eins")
        write(library, "Fotos/IMG_20120814_120000.jpg", b"zwei")
        write(library, "Fotos/IMG_20150101_120000.jpg", b"drei")
        await published(session, library, "Fotos")
        headers = await user_headers(api_client, session_factory)
        tree = await api_client.get("/albums/tree", headers=headers)
        album = tree.json()["items"][0]

        first = await api_client.get(f"/albums/{album['id']}/media?limit=2", headers=headers)
        body = first.json()
        second = await api_client.get(
            f"/albums/{album['id']}/media?cursor={body['next_cursor']}", headers=headers
        )

        assert [item["taken_at"][:4] for item in body["items"]] == ["2009", "2012"]
        assert [item["taken_at"][:4] for item in second.json()["items"]] == ["2015"]
        assert body["prev_cursor"] is None

    async def test_a_page_leads_back_to_the_one_in_front_of_it(
        self,
        api_client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
        session: AsyncSession,
        library: Path,
    ) -> None:
        write(library, "Fotos/IMG_20090714_120000.jpg", b"eins")
        write(library, "Fotos/IMG_20120814_120000.jpg", b"zwei")
        write(library, "Fotos/IMG_20150101_120000.jpg", b"drei")
        write(library, "Fotos/IMG_20180101_120000.jpg", b"vier")
        await published(session, library, "Fotos")
        headers = await user_headers(api_client, session_factory)
        tree = await api_client.get("/albums/tree", headers=headers)
        album = tree.json()["items"][0]

        first = (
            await api_client.get(f"/albums/{album['id']}/media?limit=2", headers=headers)
        ).json()
        second = (
            await api_client.get(
                f"/albums/{album['id']}/media?limit=2&cursor={first['next_cursor']}",
                headers=headers,
            )
        ).json()
        back = (
            await api_client.get(
                f"/albums/{album['id']}/media?limit=2&before={second['prev_cursor']}",
                headers=headers,
            )
        ).json()

        assert [item["taken_at"][:4] for item in second["items"]] == ["2015", "2018"]
        # Back from the second page is the first page again, and it knows where forwards is.
        assert [item["id"] for item in back["items"]] == [item["id"] for item in first["items"]]
        assert back["prev_cursor"] is None
        assert back["next_cursor"] is not None

    async def test_only_one_direction_at_a_time(
        self,
        api_client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
        session: AsyncSession,
        library: Path,
    ) -> None:
        write(library, "Fotos/IMG_1.jpg")
        await published(session, library, "Fotos")
        headers = await user_headers(api_client, session_factory)
        tree = await api_client.get("/albums/tree", headers=headers)
        album = tree.json()["items"][0]
        page = (await api_client.get(f"/albums/{album['id']}/media", headers=headers)).json()

        response = await api_client.get(
            f"/albums/{album['id']}/media?cursor=a&before=b", headers=headers
        )

        assert page["next_cursor"] is None
        assert page["prev_cursor"] is None
        assert response.status_code == 400
        assert response.json()["type"] == "urn:muninn:problem:invalid-cursor"

    async def test_a_made_up_cursor_going_back_is_refused(
        self,
        api_client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
        session: AsyncSession,
        library: Path,
    ) -> None:
        write(library, "Fotos/IMG_1.jpg")
        await published(session, library, "Fotos")
        headers = await user_headers(api_client, session_factory)
        tree = await api_client.get("/albums/tree", headers=headers)
        album = tree.json()["items"][0]

        response = await api_client.get(
            f"/albums/{album['id']}/media?before=nonsense", headers=headers
        )

        assert response.status_code == 400

    async def test_an_unknown_album_is_a_problem_not_a_crash(
        self, api_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        headers = await user_headers(api_client, session_factory)

        response = await api_client.get(f"/albums/{uuid.uuid4()}", headers=headers)

        assert response.status_code == 404


class TestAlbumSync:
    async def test_everybody_signed_in_may_ask_for_a_sync(
        self,
        api_client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
        session: AsyncSession,
        library: Path,
        no_worker: list[dict[str, Any]],
    ) -> None:
        """It reads the NAS and changes nothing there, so it is not an admin's privilege."""
        write(library, "Urlaub/Brasilien/IMG_1.jpg")
        await published(session, library, "Urlaub/Brasilien")
        headers = await user_headers(api_client, session_factory)
        tree = await api_client.get("/albums/tree", headers=headers)
        album = next(
            item for item in tree.json()["items"] if item["relative_path"] == "Urlaub/Brasilien"
        )

        response = await api_client.post(
            f"/albums/{album['id']}/sync", json={"with_children": True}, headers=headers
        )

        assert response.status_code == 202
        assert no_worker[0]["scope_path"] == "Urlaub/Brasilien"
        assert no_worker[0]["with_children"] is True

    async def test_a_way_that_is_not_published_cannot_be_synced(
        self,
        api_client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
        session: AsyncSession,
        library: Path,
        no_worker: list[dict[str, Any]],
    ) -> None:
        """ "Urlaub" only leads to the published folder; there is nothing of its own to read."""
        write(library, "Urlaub/Brasilien/IMG_1.jpg")
        await published(session, library, "Urlaub/Brasilien")
        headers = await user_headers(api_client, session_factory)
        tree = await api_client.get("/albums/tree", headers=headers)
        album = next(item for item in tree.json()["items"] if item["relative_path"] == "Urlaub")

        response = await api_client.post(f"/albums/{album['id']}/sync", json={}, headers=headers)

        assert response.status_code == 409
        assert response.json()["type"].endswith("album-not-published")

    async def test_the_job_says_how_it_went(
        self,
        api_client: AsyncClient,
        api_app: FastAPI,
        session_factory: async_sessionmaker[AsyncSession],
        session: AsyncSession,
        library: Path,
    ) -> None:
        write(library, "Fotos/IMG_1.jpg")
        await published(session, library, "Fotos")
        headers = await user_headers(api_client, session_factory)
        tree = await api_client.get("/albums/tree", headers=headers)
        album = tree.json()["items"][0]
        await jobs.write_job(api_app.state.redis, "job-1", "done", {"added": 4, "missing": 2})

        response = await api_client.get(f"/albums/{album['id']}/sync/job-1", headers=headers)

        assert response.json()["state"] == "done"
        assert response.json()["result"] == {"added": 4, "missing": 2}


class TestChangeLog:
    async def test_an_admin_can_read_what_the_syncs_found(
        self,
        api_client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
        session: AsyncSession,
        library: Path,
    ) -> None:
        write(library, "Fotos/IMG_1.jpg")
        await published(session, library, "Fotos")
        headers = await admin_headers(api_client, session_factory)

        response = await api_client.get("/admin/index/changes", headers=headers)

        kinds = {entry["kind"] for entry in response.json()}
        assert "media_added" in kinds
        assert "album_added" in kinds

    async def test_a_plain_user_may_not(
        self, api_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        headers = await user_headers(api_client, session_factory)

        assert (await api_client.get("/admin/index/changes", headers=headers)).status_code == 403


class TestWatchingAReadRun:
    async def test_the_status_shows_how_far_a_running_read_got(
        self,
        api_client: AsyncClient,
        api_app: FastAPI,
        session_factory: async_sessionmaker[AsyncSession],
        session: AsyncSession,
        library: Path,
    ) -> None:
        write(library, "Fotos/IMG_1.jpg")
        await published(session, library, "Fotos")
        entry = (await service.list_publications(session))[0]
        await jobs.write_progress(
            api_app.state.redis,
            entry.id,
            {"files_total": 684, "files_done": 320, "current": "Fotos/Tag 2"},
        )
        headers = await admin_headers(api_client, session_factory)

        response = await api_client.get("/admin/index/status", headers=headers)

        progress = response.json()["publications"][0]["progress"]
        assert progress["files_done"] == 320
        assert progress["files_total"] == 684
        assert progress["current"] == "Fotos/Tag 2"

    async def test_it_says_when_the_clock_reads_again(
        self,
        api_client: AsyncClient,
        api_app: FastAPI,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Otherwise "not read yet" says nothing about when that will change."""
        await api_app.state.redis.set(jobs.LAST_QUICK_KEY, "2026-09-20T12:00:00+00:00")
        headers = await admin_headers(api_client, session_factory)

        response = await api_client.get("/admin/index/status", headers=headers)

        # Five minutes after the last one, as the settings say.
        assert response.json()["next_sync_at"].startswith("2026-09-20T12:05:00")

    async def test_it_says_how_many_files_are_still_being_copied(
        self,
        api_client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
        session: AsyncSession,
        library: Path,
    ) -> None:
        """A read that found only half-copied files must not look like a read that found none."""
        write(library, "Fotos/IMG_1.jpg")
        publication = await service.publish(session, relative_path="Fotos", library_base=library)
        settings = await settings_service.get_settings(session)
        # One listing only: the file was seen once and waits for the second look.
        report = await service.sync_publication(
            session, publication, settings=settings, library_base=library, now=NOW
        )
        headers = await admin_headers(api_client, session_factory)

        response = await api_client.get("/admin/index/status", headers=headers)

        assert report.waiting == 1
        assert response.json()["publications"][0]["waiting_files"] == 1
        assert response.json()["media"] == 0

    async def test_without_a_run_so_far_it_says_nothing_rather_than_guessing(
        self, api_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        headers = await admin_headers(api_client, session_factory)

        response = await api_client.get("/admin/index/status", headers=headers)

        assert response.json()["next_sync_at"] is None
