"""A folder that comes back after an outage has to say so, even when nothing in it changed."""

from datetime import timedelta
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from muninn.models.publication import ScanStatus
from muninn.models.settings import AppSettings
from tests.test_library_service import (  # noqa: F401 - library and settings are fixtures
    EVEN_LATER,
    albums_of,
    library,
    publish,
    settings,
    settle,
    sync,
    write,
)


async def test_an_unchanged_folder_that_is_there_again_is_no_longer_unreachable(
    session: AsyncSession,
    library: Path,  # noqa: F811
    settings: AppSettings,  # noqa: F811
) -> None:
    """The quick sync skips a folder whose signature did not change - and used to skip its
    status with it, so an album marked unreachable during an outage stayed that way until
    somebody added a picture."""
    write(library, "Fotos/IMG_1.jpg")
    publication = await publish(session, library, "Fotos")
    await settle(session, publication, library, settings)

    album = (await albums_of(session))["Fotos"]
    album.last_sync_status = ScanStatus.UNAVAILABLE
    album.last_sync_message = "This folder could not be listed."
    await session.commit()

    report = await sync(session, publication, library, settings, now=EVEN_LATER, quick=True)

    album = (await albums_of(session))["Fotos"]
    assert report.unchanged_folders >= 1
    assert album.last_sync_status is ScanStatus.OK
    assert album.last_sync_message is None


async def test_a_folder_that_is_fine_is_not_written_again_and_again(
    session: AsyncSession,
    library: Path,  # noqa: F811
    settings: AppSettings,  # noqa: F811
) -> None:
    """The quick sync runs every minute; touching every album on every run is a write per
    folder per minute for nothing."""
    write(library, "Fotos/IMG_1.jpg")
    publication = await publish(session, library, "Fotos")
    await settle(session, publication, library, settings)
    before = (await albums_of(session))["Fotos"].last_sync_at

    await sync(
        session, publication, library, settings, now=EVEN_LATER + timedelta(minutes=5), quick=True
    )

    assert (await albums_of(session))["Fotos"].last_sync_at == before
