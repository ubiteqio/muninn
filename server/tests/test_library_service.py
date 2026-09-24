"""Publishing folders of the library, and keeping their albums in step with the NAS."""

import os
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from muninn.library import service
from muninn.library.safety import MARKER_NAME, device_of
from muninn.models.album import Album
from muninn.models.change_log import ChangeKind, ChangeLogEntry, SyncTrigger
from muninn.models.media import Media, MediaFile, MediaFileRole, MediaKind, MediaStatus
from muninn.models.pending_file import PendingFile
from muninn.models.publication import Publication, ScanStatus
from muninn.models.settings import AppSettings
from muninn.settings import service as settings_service

NOW = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)
#: Far enough after NOW for the stability window to have passed.
LATER = NOW + timedelta(minutes=1)
EVEN_LATER = NOW + timedelta(minutes=2)


def write(root: Path, relative_path: str, content: bytes = b"bild", *, age_days: float = 1) -> Path:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    stamp = (NOW - timedelta(days=age_days)).timestamp()
    os.utime(path, (stamp, stamp))
    return path


@pytest.fixture
def library(tmp_path: Path) -> Path:
    """What the host mounts: the folder Muninn reads from and never writes to."""
    base = tmp_path / "library"
    base.mkdir()
    return base


@pytest.fixture
async def settings(session: AsyncSession) -> AppSettings:
    return await settings_service.get_settings(session)


def with_the_pause_on(settings: AppSettings) -> AppSettings:
    """The pause before many deletions is off by default; these tests are about it being on."""
    settings.deletion_share_percent = 5
    settings.deletion_count = 500
    return settings


async def publish(session: AsyncSession, library: Path, relative_path: str) -> Publication:
    return await service.publish(session, relative_path=relative_path, library_base=library)


async def sync(
    session: AsyncSession,
    publication: Publication,
    library: Path,
    settings: AppSettings,
    *,
    now: datetime = NOW,
    **kwargs: Any,
) -> service.SyncReport:
    return await service.sync_publication(
        session, publication, settings=settings, library_base=library, now=now, **kwargs
    )


async def settle(
    session: AsyncSession,
    publication: Publication,
    library: Path,
    settings: AppSettings,
    *,
    first: datetime = NOW,
    second: datetime = LATER,
    **kwargs: Any,
) -> service.SyncReport:
    """Two listings far enough apart: only then does a file count as fully copied."""
    await sync(session, publication, library, settings, now=first, **kwargs)
    return await sync(session, publication, library, settings, now=second, **kwargs)


async def albums_of(session: AsyncSession) -> dict[str, Album]:
    rows = await session.scalars(select(Album))
    return {album.relative_path: album for album in rows}


async def media_of(session: AsyncSession) -> list[Media]:
    rows = await session.scalars(select(Media).order_by(Media.created_at, Media.id))
    return list(rows)


async def log_of(session: AsyncSession) -> list[ChangeLogEntry]:
    rows = await session.scalars(select(ChangeLogEntry).order_by(ChangeLogEntry.occurred_at))
    return list(rows)


class TestPublishing:
    async def test_a_folder_is_published_where_it_sits(
        self, session: AsyncSession, library: Path, settings: AppSettings
    ) -> None:
        """The album appears in the place the original has, so it is found where one expects."""
        write(library, "Urlaub/Brasilien 2026/Boris/IMG_1.jpg")
        publication = await publish(session, library, "Urlaub/Brasilien 2026/Boris")

        await settle(session, publication, library, settings)

        albums = await albums_of(session)
        assert set(albums) == {"Urlaub", "Urlaub/Brasilien 2026", "Urlaub/Brasilien 2026/Boris"}
        assert albums["Urlaub"].parent_id is None
        assert albums["Urlaub/Brasilien 2026"].parent_id == albums["Urlaub"].id
        assert albums["Urlaub/Brasilien 2026/Boris"].parent_id == albums["Urlaub/Brasilien 2026"].id

    async def test_the_way_to_it_carries_no_media(
        self, session: AsyncSession, library: Path, settings: AppSettings
    ) -> None:
        write(library, "Urlaub/Brasilien 2026/Boris/IMG_1.jpg")
        # A picture beside the published folder must not appear: it was not published.
        write(library, "Urlaub/IMG_beside.jpg")
        publication = await publish(session, library, "Urlaub/Brasilien 2026/Boris")

        await settle(session, publication, library, settings)

        albums = await albums_of(session)
        assert albums["Urlaub"].is_source is False
        assert albums["Urlaub/Brasilien 2026/Boris"].is_source is True
        assert [media.primary_file.filename for media in await media_of(session)] == ["IMG_1.jpg"]

    async def test_everything_below_comes_with_it(
        self, session: AsyncSession, library: Path, settings: AppSettings
    ) -> None:
        write(library, "Fotos/IMG_1.jpg", b"eins")
        write(library, "Fotos/2009 Italien/IMG_2.jpg", b"zwei")
        write(library, "Fotos/2009 Italien/Tag 2/IMG_3.jpg", b"drei")
        publication = await publish(session, library, "Fotos")

        report = await settle(session, publication, library, settings)

        albums = await albums_of(session)
        assert set(albums) == {"Fotos", "Fotos/2009 Italien", "Fotos/2009 Italien/Tag 2"}
        assert all(album.is_source for album in albums.values())
        assert report.added == 3

    async def test_the_library_itself_can_be_published(
        self, session: AsyncSession, library: Path, settings: AppSettings
    ) -> None:
        """Pictures often lie directly in the mounted folder."""
        write(library, "IMG_1.jpg")
        write(library, "Sommer/IMG_2.jpg", b"zwei")
        publication = await publish(session, library, "")

        await settle(session, publication, library, settings)

        albums = await albums_of(session)
        assert set(albums) == {"", "Sommer"}
        assert len(await media_of(session)) == 2

    async def test_publishing_inside_a_published_folder_is_refused(
        self, session: AsyncSession, library: Path
    ) -> None:
        write(library, "Fotos/2009/IMG_1.jpg")
        await publish(session, library, "Fotos")

        with pytest.raises(service.AlreadyPublishedError):
            await publish(session, library, "Fotos/2009")

    async def test_publishing_above_one_takes_it_over(
        self, session: AsyncSession, library: Path, settings: AppSettings
    ) -> None:
        """The albums stay where they are; only the now redundant entry goes."""
        write(library, "Fotos/2009/IMG_1.jpg")
        inner = await publish(session, library, "Fotos/2009")
        await settle(session, inner, library, settings)
        media_id = (await media_of(session))[0].id

        outer = await publish(session, library, "Fotos")
        await settle(session, outer, library, settings, first=EVEN_LATER, second=EVEN_LATER)

        publications = await service.list_publications(session)
        assert [entry.relative_path for entry in publications] == ["Fotos"]
        assert [media.id for media in await media_of(session)] == [media_id]

    async def test_a_folder_outside_the_library_is_refused(
        self, session: AsyncSession, library: Path
    ) -> None:
        (library.parent / "geheim").mkdir(exist_ok=True)

        with pytest.raises(service.PathNotAllowedError):
            await publish(session, library, "../geheim")


class TestUnpublishing:
    async def test_the_albums_and_the_way_to_them_go(
        self, session: AsyncSession, library: Path, settings: AppSettings
    ) -> None:
        write(library, "Urlaub/Brasilien/Boris/IMG_1.jpg")
        publication = await publish(session, library, "Urlaub/Brasilien/Boris")
        await settle(session, publication, library, settings)

        forgotten = await service.unpublish(session, publication)

        assert len(forgotten) == 1
        assert await albums_of(session) == {}
        assert await media_of(session) == []

    async def test_a_way_that_still_leads_somewhere_stays(
        self, session: AsyncSession, library: Path, settings: AppSettings
    ) -> None:
        write(library, "Urlaub/Brasilien/IMG_1.jpg")
        write(library, "Urlaub/Italien/IMG_2.jpg", b"zwei")
        first = await publish(session, library, "Urlaub/Brasilien")
        second = await publish(session, library, "Urlaub/Italien")
        await settle(session, first, library, settings)
        await settle(session, second, library, settings)

        await service.unpublish(session, first)

        albums = await albums_of(session)
        assert set(albums) == {"Urlaub", "Urlaub/Italien"}


class TestHalfCopiedFiles:
    async def test_one_listing_is_not_enough(
        self, session: AsyncSession, library: Path, settings: AppSettings
    ) -> None:
        write(library, "Fotos/IMG_1.jpg")
        publication = await publish(session, library, "Fotos")

        report = await sync(session, publication, library, settings)

        assert report.waiting == 1
        assert report.added == 0
        assert await media_of(session) == []

    async def test_a_file_that_keeps_growing_keeps_waiting(
        self, session: AsyncSession, library: Path, settings: AppSettings
    ) -> None:
        write(library, "Fotos/IMG_1.jpg", b"anfang")
        publication = await publish(session, library, "Fotos")
        await sync(session, publication, library, settings)

        write(library, "Fotos/IMG_1.jpg", b"anfang und mehr", age_days=0)
        report = await sync(session, publication, library, settings, now=LATER)

        assert report.waiting == 1
        assert await media_of(session) == []


class TestChangedFiles:
    async def test_an_unchanged_library_stays_as_it_is(
        self, session: AsyncSession, library: Path, settings: AppSettings
    ) -> None:
        write(library, "Fotos/IMG_1.jpg")
        publication = await publish(session, library, "Fotos")
        await settle(session, publication, library, settings)
        before = [media.id for media in await media_of(session)]

        report = await sync(session, publication, library, settings, now=EVEN_LATER)

        assert (report.added, report.changed, report.touched, report.missing) == (0, 0, 0, 0)
        assert [media.id for media in await media_of(session)] == before

    async def test_a_file_that_was_only_touched_keeps_its_abbild(
        self, session: AsyncSession, library: Path, settings: AppSettings
    ) -> None:
        """A restored backup or a corrected timestamp must not cost a single derived byte."""
        path = write(library, "Fotos/IMG_1.jpg", b"derselbe inhalt")
        publication = await publish(session, library, "Fotos")
        await settle(session, publication, library, settings)
        media = (await media_of(session))[0]
        media.metadata_version = 1
        media.derive_version = 1
        await session.commit()

        stamp = (NOW - timedelta(hours=1)).timestamp()
        os.utime(path, (stamp, stamp))
        report = await settle(
            session,
            publication,
            library,
            settings,
            first=EVEN_LATER,
            second=EVEN_LATER + timedelta(minutes=1),
        )

        after = (await media_of(session))[0]
        assert report.touched == 1
        assert report.changed == 0
        assert (after.metadata_version, after.derive_version) == (1, 1)

    async def test_an_edited_file_keeps_its_id_and_is_built_again(
        self, session: AsyncSession, library: Path, settings: AppSettings
    ) -> None:
        write(library, "Fotos/IMG_1.jpg", b"alt")
        publication = await publish(session, library, "Fotos")
        await settle(session, publication, library, settings)
        media = (await media_of(session))[0]
        media.metadata_version = 1
        media.derive_version = 1
        await session.commit()
        old_hash = media.content_hash

        write(library, "Fotos/IMG_1.jpg", b"neu und laenger", age_days=0.5)
        report = await settle(
            session,
            publication,
            library,
            settings,
            first=EVEN_LATER,
            second=EVEN_LATER + timedelta(minutes=1),
        )

        after = (await media_of(session))[0]
        assert after.id == media.id
        assert after.content_hash != old_hash
        assert (after.metadata_version, after.derive_version) == (0, 0)
        assert report.changed == 1

    async def test_a_renamed_file_keeps_its_medium(
        self, session: AsyncSession, library: Path, settings: AppSettings
    ) -> None:
        """Likes and faces hang on the id, so a rename must not create a second medium."""
        path = write(library, "Fotos/IMG_1.jpg", b"derselbe inhalt")
        publication = await publish(session, library, "Fotos")
        await settle(session, publication, library, settings)
        media_id = (await media_of(session))[0].id

        path.rename(library / "Fotos" / "Italien 2009.jpg")
        report = await settle(
            session,
            publication,
            library,
            settings,
            first=EVEN_LATER,
            second=EVEN_LATER + timedelta(minutes=1),
        )

        media = await media_of(session)
        assert len(media) == 1
        assert media[0].id == media_id
        assert media[0].primary_file.relative_path == "Fotos/Italien 2009.jpg"
        assert (report.moved, report.added, report.missing) == (1, 0, 0)


class TestGrouping:
    async def test_raw_and_jpeg_become_one_medium(
        self, session: AsyncSession, library: Path, settings: AppSettings
    ) -> None:
        write(library, "Fotos/IMG_1.JPG", b"jpeg")
        write(library, "Fotos/IMG_1.CR2", b"raw")
        publication = await publish(session, library, "Fotos")

        await settle(session, publication, library, settings)

        media = await media_of(session)
        assert len(media) == 1
        assert {file.role for file in media[0].files} == {MediaFileRole.PRIMARY, MediaFileRole.RAW}
        assert media[0].kind is MediaKind.IMAGE


class TestQuickSync:
    async def test_folders_whose_signature_matches_are_not_read_again(
        self, session: AsyncSession, library: Path, settings: AppSettings
    ) -> None:
        write(library, "Fotos/IMG_1.jpg")
        publication = await publish(session, library, "Fotos")
        await settle(session, publication, library, settings)

        report = await sync(session, publication, library, settings, now=EVEN_LATER, quick=True)

        assert report.unchanged_folders == 1
        assert (report.added, report.changed, report.missing) == (0, 0, 0)

    async def test_a_new_file_changes_the_signature_and_is_found(
        self, session: AsyncSession, library: Path, settings: AppSettings
    ) -> None:
        write(library, "Fotos/IMG_1.jpg", b"eins")
        publication = await publish(session, library, "Fotos")
        await settle(session, publication, library, settings)

        write(library, "Fotos/IMG_2.jpg", b"zwei")
        report = await settle(
            session,
            publication,
            library,
            settings,
            first=EVEN_LATER,
            second=EVEN_LATER + timedelta(minutes=1),
            quick=True,
        )

        assert report.added == 1


class TestDisappearingFiles:
    async def test_a_deleted_file_is_marked_missing(
        self, session: AsyncSession, library: Path, settings: AppSettings
    ) -> None:
        for index in range(30):
            write(library, f"Fotos/IMG_{index}.jpg", f"bild {index}".encode())
        publication = await publish(session, library, "Fotos")
        await settle(session, publication, library, settings)

        (library / "Fotos" / "IMG_0.jpg").unlink()
        report = await sync(session, publication, library, settings, now=EVEN_LATER)

        missing = [
            media for media in await media_of(session) if media.status is MediaStatus.MISSING
        ]
        assert report.missing == 1
        assert len(missing) == 1

    async def test_a_deleted_file_leaves_even_a_small_folder_at_once(
        self, session: AsyncSession, library: Path, settings: AppSettings
    ) -> None:
        """One of two files is half the folder - and still simply a file somebody deleted."""
        write(library, "Fotos/IMG_1.jpg", b"bild 1")
        write(library, "Fotos/MOV_1.avi", b"film 1")
        publication = await publish(session, library, "Fotos")
        await settle(session, publication, library, settings, quick=True)

        (library / "Fotos" / "MOV_1.avi").unlink()
        report = await sync(session, publication, library, settings, now=EVEN_LATER, quick=True)

        assert report.status is ScanStatus.OK
        assert report.missing == 1
        assert publication.pending_deletions == 0

    async def test_too_many_deletions_pause_the_sync(
        self, session: AsyncSession, library: Path, settings: AppSettings
    ) -> None:
        """A share that fell out of the mount must not empty the library."""
        with_the_pause_on(settings)
        for index in range(10):
            write(library, f"Fotos/IMG_{index}.jpg", f"bild {index}".encode())
        publication = await publish(session, library, "Fotos")
        await settle(session, publication, library, settings)

        for index in range(5):
            (library / "Fotos" / f"IMG_{index}.jpg").unlink()
        report = await sync(session, publication, library, settings, now=EVEN_LATER)

        assert report.status is ScanStatus.PAUSED
        assert publication.pending_deletions == 5
        assert all(media.status is MediaStatus.ACTIVE for media in await media_of(session))

    async def test_a_pause_holds_until_the_admin_confirms(
        self, session: AsyncSession, library: Path, settings: AppSettings
    ) -> None:
        """The quick sync a minute later must not take the paused folder for unchanged.

        The paused read had already stored the folder's new listing, so every quick sync after
        it skipped the folder: the pause was gone without anybody confirming, and the deleted
        file stayed in the album for good.
        """
        with_the_pause_on(settings)
        write(library, "Fotos/IMG_1.jpg", b"bild 1")
        write(library, "Fotos/MOV_1.avi", b"film 1")
        publication = await publish(session, library, "Fotos")
        await settle(session, publication, library, settings, quick=True)

        (library / "Fotos" / "MOV_1.avi").unlink()
        first = await sync(session, publication, library, settings, now=EVEN_LATER, quick=True)
        again = await sync(session, publication, library, settings, now=EVEN_LATER, quick=True)

        assert (first.status, again.status) == (ScanStatus.PAUSED, ScanStatus.PAUSED)
        assert publication.pending_deletions == 1
        assert all(media.status is MediaStatus.ACTIVE for media in await media_of(session))

        confirmed = await sync(
            session,
            publication,
            library,
            settings,
            now=EVEN_LATER,
            quick=True,
            confirm_deletions=True,
        )

        assert confirmed.status is ScanStatus.OK
        assert confirmed.missing == 1

    async def test_the_admin_can_confirm_the_deletions(
        self, session: AsyncSession, library: Path, settings: AppSettings
    ) -> None:
        with_the_pause_on(settings)
        for index in range(10):
            write(library, f"Fotos/IMG_{index}.jpg", f"bild {index}".encode())
        publication = await publish(session, library, "Fotos")
        await settle(session, publication, library, settings)
        for index in range(5):
            (library / "Fotos" / f"IMG_{index}.jpg").unlink()
        await sync(session, publication, library, settings, now=EVEN_LATER)

        report = await sync(
            session, publication, library, settings, now=EVEN_LATER, confirm_deletions=True
        )

        assert report.status is ScanStatus.OK
        assert len([m for m in await media_of(session) if m.status is MediaStatus.MISSING]) == 5

    async def test_a_folder_that_cannot_be_listed_deletes_nothing(
        self, session: AsyncSession, library: Path, settings: AppSettings
    ) -> None:
        """An error while listing is never a deletion."""
        for index in range(30):
            write(library, f"Fotos/Tag 1/IMG_{index}.jpg", f"bild {index}".encode())
        publication = await publish(session, library, "Fotos")
        await settle(session, publication, library, settings)

        folder = library / "Fotos" / "Tag 1"
        folder.chmod(0o000)
        try:
            report = await sync(session, publication, library, settings, now=EVEN_LATER)
        finally:
            folder.chmod(0o755)

        assert report.failed_folders == 1
        assert report.missing == 0
        assert all(media.status is MediaStatus.ACTIVE for media in await media_of(session))


class TestSafetyNet:
    async def test_a_share_that_is_not_mounted_stops_the_sync(
        self, session: AsyncSession, library: Path, settings: AppSettings
    ) -> None:
        """An unmounted share looks like an empty folder - and must never empty the library."""
        write(library, "Fotos/IMG_1.jpg")
        publication = await publish(session, library, "Fotos")
        publication.device_id = (device_of(library / "Fotos") or 0) + 1
        await session.commit()

        report = await sync(session, publication, library, settings)

        assert report.status is ScanStatus.UNAVAILABLE
        assert "not mounted" in (report.message or "")
        assert await media_of(session) == []

    async def test_a_marker_file_also_counts_as_proof(
        self, session: AsyncSession, library: Path, settings: AppSettings
    ) -> None:
        """For setups whose device id changes on every mount, the old marker still works."""
        write(library, "Fotos/IMG_1.jpg")
        (library / "Fotos" / MARKER_NAME).touch()
        publication = await publish(session, library, "Fotos")
        publication.device_id = (publication.device_id or 0) + 1
        await session.commit()

        report = await settle(session, publication, library, settings)

        assert report.status is ScanStatus.OK
        assert report.added == 1


class TestWhileItRuns:
    async def test_a_sync_says_that_it_is_running(
        self,
        session: AsyncSession,
        library: Path,
        settings: AppSettings,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The admin area polls on this; without it a finished sync looks like nothing happened."""
        write(library, "Fotos/IMG_1.jpg")
        publication = await publish(session, library, "Fotos")
        seen: list[ScanStatus] = []
        original = service._sync_albums

        async def spy(*args: Any, **kwargs: Any) -> Any:
            seen.append(publication.last_sync_status)
            return await original(*args, **kwargs)

        monkeypatch.setattr(service, "_sync_albums", spy)
        await sync(session, publication, library, settings)

        assert seen == [ScanStatus.RUNNING]
        assert publication.last_sync_status is ScanStatus.OK


class TestChangeLog:
    async def test_every_finding_is_written_down(
        self, session: AsyncSession, library: Path, settings: AppSettings
    ) -> None:
        write(library, "Fotos/IMG_1.jpg")
        publication = await publish(session, library, "Fotos")
        await settle(session, publication, library, settings, trigger=SyncTrigger.MANUAL)

        entries = await log_of(session)

        kinds = [entry.kind for entry in entries]
        assert ChangeKind.ALBUM_ADDED in kinds
        assert ChangeKind.MEDIA_ADDED in kinds
        added = next(entry for entry in entries if entry.kind is ChangeKind.MEDIA_ADDED)
        assert added.path == "Fotos/IMG_1.jpg"

    async def test_old_lines_are_thrown_away(self, session: AsyncSession) -> None:
        session.add(
            ChangeLogEntry(
                occurred_at=NOW - timedelta(days=120),
                kind=ChangeKind.MEDIA_ADDED,
                trigger=SyncTrigger.FULL,
            )
        )
        session.add(
            ChangeLogEntry(
                occurred_at=NOW - timedelta(days=10),
                kind=ChangeKind.MEDIA_ADDED,
                trigger=SyncTrigger.FULL,
            )
        )
        await session.commit()

        removed = await service.prune_change_log(session, now=NOW)

        assert removed == 1
        assert len(await log_of(session)) == 1


class TestBrowsing:
    async def test_it_says_what_is_published_already(
        self, session: AsyncSession, library: Path
    ) -> None:
        (library / "Fotos").mkdir()
        (library / "Videos").mkdir()
        await publish(session, library, "Fotos")

        current, entries = await service.browse(session, library_base=library)

        by_name = {entry["name"]: entry for entry in entries}
        assert by_name["Fotos"]["published"] is True
        assert by_name["Videos"]["published"] is False
        assert current["relative_path"] == ""

    async def test_a_folder_inside_a_published_one_counts_as_published(
        self, session: AsyncSession, library: Path
    ) -> None:
        (library / "Fotos" / "2009").mkdir(parents=True)
        await publish(session, library, "Fotos")

        _, entries = await service.browse(session, library_base=library, relative_path="Fotos")

        assert entries[0]["published"] is True

    async def test_the_folder_itself_is_offered_with_its_media_count(
        self, session: AsyncSession, library: Path
    ) -> None:
        """Pictures often lie in the share itself, with no subfolder to pick at all."""
        write(library, "IMG_1.jpg")

        current, entries = await service.browse(session, library_base=library)

        assert entries == []
        assert current["media_files"] == 1


class TestMetadata:
    async def test_the_capture_date_falls_back_to_the_file_name(
        self, session: AsyncSession, library: Path, settings: AppSettings
    ) -> None:
        """Without exiftool installed this is what the concept's sources 3 to 5 deliver."""
        write(library, "2009-07 Italien/IMG_20090714_153012.jpg")
        publication = await publish(session, library, "2009-07 Italien")
        report = await settle(session, publication, library, settings)

        assert len(report.pending_metadata) == 1
        assert (
            await service.apply_metadata(session, report.pending_metadata[0], library_base=library)
            is True
        )

        media = (await media_of(session))[0]
        assert media.taken_at == datetime(2009, 7, 14, 15, 30, 12, tzinfo=UTC)

    async def test_metadata_for_a_medium_that_is_gone_is_not_an_error(
        self, session: AsyncSession, library: Path
    ) -> None:
        assert await service.apply_metadata(session, uuid.uuid4(), library_base=library) is False


class TestPendingRows:
    async def test_a_confirmed_file_leaves_no_observation_behind(
        self, session: AsyncSession, library: Path, settings: AppSettings
    ) -> None:
        write(library, "Fotos/IMG_1.jpg")
        publication = await publish(session, library, "Fotos")
        await settle(session, publication, library, settings)

        assert list(await session.scalars(select(PendingFile))) == []


class TestUnreadableRoot:
    async def test_a_published_folder_that_cannot_be_read_stops_the_sync(
        self, session: AsyncSession, library: Path, settings: AppSettings
    ) -> None:
        """Not readable is not empty: nothing is marked as missing."""
        for index in range(30):
            write(library, f"Fotos/IMG_{index}.jpg", f"bild {index}".encode())
        publication = await publish(session, library, "Fotos")
        await settle(session, publication, library, settings)

        folder = library / "Fotos"
        folder.chmod(0o000)
        try:
            report = await sync(session, publication, library, settings, now=EVEN_LATER)
        finally:
            folder.chmod(0o755)

        assert report.status is ScanStatus.UNAVAILABLE
        assert report.missing == 0
        assert all(media.status is MediaStatus.ACTIVE for media in await media_of(session))


class TestProgress:
    async def test_a_running_sync_reports_after_every_folder(
        self, session: AsyncSession, library: Path, settings: AppSettings
    ) -> None:
        """Without this a long read looks like nothing happening for an hour."""
        write(library, "Fotos/IMG_1.jpg")
        write(library, "Fotos/Tag 2/IMG_2.jpg", b"zwei")
        publication = await publish(session, library, "Fotos")
        seen: list[service.SyncProgress] = []

        async def collect(progress: service.SyncProgress) -> None:
            seen.append(progress)

        await settle(session, publication, library, settings, on_progress=collect)

        last = seen[-1]
        assert last.files_total == 2
        assert last.files_done == 2
        assert last.current == "Fotos/Tag 2"

    async def test_media_appear_while_the_sync_is_still_running(
        self, session: AsyncSession, library: Path, settings: AppSettings
    ) -> None:
        """Committing per folder is what makes pictures show up during a long read."""
        write(library, "Fotos/IMG_1.jpg")
        write(library, "Fotos/Tag 2/IMG_2.jpg", b"zwei")
        publication = await publish(session, library, "Fotos")
        await sync(session, publication, library, settings)
        counts: list[int] = []

        async def count(progress: service.SyncProgress) -> None:
            counts.append(len(await media_of(session)))

        await sync(session, publication, library, settings, now=LATER, on_progress=count)

        assert counts == [1, 2]


class TestSecondLook:
    async def test_the_clock_asks_again_once_a_file_has_settled(
        self, session: AsyncSession, library: Path, settings: AppSettings
    ) -> None:
        """The second listing must not depend on a task held in a worker's memory."""
        write(library, "Fotos/IMG_1.jpg")
        publication = await publish(session, library, "Fotos")
        await sync(session, publication, library, settings)

        too_early = await service.waiting_for_a_second_look(
            session, stability_seconds=settings.stability_seconds, now=NOW
        )
        due = await service.waiting_for_a_second_look(
            session, stability_seconds=settings.stability_seconds, now=LATER
        )

        assert too_early == []
        assert [entry.id for entry in due] == [publication.id]

    async def test_a_folder_with_nothing_waiting_is_left_alone(
        self, session: AsyncSession, library: Path, settings: AppSettings
    ) -> None:
        write(library, "Fotos/IMG_1.jpg")
        publication = await publish(session, library, "Fotos")
        await settle(session, publication, library, settings)

        due = await service.waiting_for_a_second_look(
            session, stability_seconds=settings.stability_seconds, now=EVEN_LATER
        )

        assert due == []

    async def test_a_paused_folder_is_not_read_again(
        self, session: AsyncSession, library: Path, settings: AppSettings
    ) -> None:
        write(library, "Fotos/IMG_1.jpg")
        publication = await publish(session, library, "Fotos")
        await sync(session, publication, library, settings)
        await service.update_publication(session, publication=publication, enabled=False)

        due = await service.waiting_for_a_second_look(
            session, stability_seconds=settings.stability_seconds, now=LATER
        )

        assert due == []


class TestProgressInsideAFolder:
    async def test_a_long_folder_reports_while_it_is_being_read(
        self, session: AsyncSession, library: Path, settings: AppSettings
    ) -> None:
        """One folder can hold a thousand files; counting only folders leaves the bar still."""
        for index in range(25):
            write(library, f"Fotos/IMG_{index}.jpg", f"bild {index}".encode())
        publication = await publish(session, library, "Fotos")
        await sync(session, publication, library, settings)
        seen: list[service.SyncProgress] = []

        async def collect(progress: service.SyncProgress) -> None:
            seen.append(progress)

        await sync(session, publication, library, settings, now=LATER, on_progress=collect)

        # Every ten files, and once more when the folder is through.
        assert [step.files_done for step in seen] == [10, 20, 25]
        assert all(step.files_total == 25 for step in seen)


async def test_a_file_nobody_may_read_is_walked_past_not_crashed_on(
    session: AsyncSession, library: Path, settings: AppSettings
) -> None:
    """One file with a permission that came with a copy took every reading down with it: the
    pass died on it, and no other file anywhere was confirmed again."""
    write(library, "Fest/gut.jpg")
    write(library, "Fest/auch-gut.jpg")
    locked = write(library, "Fest/gesperrt.jpg")
    locked.chmod(0o000)
    publication = await publish(session, library, "Fest")

    await sync(session, publication, library, settings)
    report = await sync(session, publication, library, settings, now=LATER)

    # The pass finished, and the two readable files are in.
    assert report.status is ScanStatus.OK
    assert [one.relative_path for one in report.unreadable] == ["Fest/gesperrt.jpg"]
    names = set(await session.scalars(select(MediaFile.relative_path)))
    assert {"Fest/gut.jpg", "Fest/auch-gut.jpg"} <= names

    # And it is written down where the engine room can show it.
    (walked_past,) = await service.unreadable_files(session)
    assert walked_past.relative_path == "Fest/gesperrt.jpg"
    assert await service.count_unreadable(session) == 1

    # Put right, it leaves by itself on the next reading.
    locked.chmod(0o644)
    await sync(session, publication, library, settings, now=EVEN_LATER)
    assert await service.unreadable_files(session) == []


async def test_a_file_deleted_while_it_was_still_waiting_is_forgotten(
    session: AsyncSession, library: Path, settings: AppSettings
) -> None:
    """It never settled, so nothing else would ever look at it again: the waiting are only
    compared against what a listing contains, and it is not in one any more."""
    write(library, "Autos/bleibt.jpg")
    copied = write(library, "Autos/DSC_0024 copy.JPG")
    publication = await publish(session, library, "Autos")

    # Seen once, and waiting for the listing that would confirm it.
    await sync(session, publication, library, settings)
    assert set(await session.scalars(select(PendingFile.relative_path))) == {
        "Autos/bleibt.jpg",
        "Autos/DSC_0024 copy.JPG",
    }

    copied.unlink()
    await sync(session, publication, library, settings, now=LATER)

    # The one that is still there became a medium; the one that went is forgotten, not counted.
    assert await session.scalars(select(PendingFile.relative_path)) is not None
    assert set(await session.scalars(select(PendingFile.relative_path))) == set()
    names = set(await session.scalars(select(MediaFile.relative_path)))
    assert names == {"Autos/bleibt.jpg"}


async def test_a_folder_that_cannot_be_listed_forgets_nothing(
    session: AsyncSession, library: Path, settings: AppSettings
) -> None:
    """A listing that failed proves nothing - least of all that a file is gone."""
    write(library, "Autos/warten.jpg")
    publication = await publish(session, library, "Autos")
    await sync(session, publication, library, settings)
    assert set(await session.scalars(select(PendingFile.relative_path))) == {"Autos/warten.jpg"}

    (library / "Autos").chmod(0o000)
    try:
        await sync(session, publication, library, settings, now=LATER)
    finally:
        (library / "Autos").chmod(0o755)

    assert set(await session.scalars(select(PendingFile.relative_path))) == {"Autos/warten.jpg"}
