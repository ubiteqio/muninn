"""Media over HTTP: the previews, the originals, and who may load them."""

import os
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import pyvips
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from muninn.core.signing import sign_media
from muninn.huginn.derive import DERIVE_VERSION
from muninn.library import service as library_service
from muninn.media import service
from muninn.models.media import Media
from muninn.models.user import UserRole
from muninn.settings import service as settings_service
from tests.helpers import auth_header, create_user, login

pytestmark = pytest.mark.usefixtures("api_client")

NOW = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)
LATER = NOW + timedelta(minutes=1)


def an_image(path: Path, *, red: int = 200, width: int = 800, height: int = 600) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    canvas = pyvips.Image.black(width, height, bands=3)
    canvas.linear([1, 1, 1], [red, 40, 90]).cast("uchar").copy(interpretation="srgb").write_to_file(
        str(path)
    )
    stamp = (NOW - timedelta(days=1)).timestamp()
    os.utime(path, (stamp, stamp))
    return path


@pytest.fixture
def library(tmp_path: Path, api_app: FastAPI) -> Path:
    """What the host mounts, with the app pointed at it and at a folder for the previews."""
    base = tmp_path / "library"
    base.mkdir()

    api_app.state.settings = api_app.state.settings.model_copy(
        update={"library_path": base, "derived_path": tmp_path / "derived"}
    )
    return base


@pytest.fixture
def derived(api_app: FastAPI) -> Path:
    derived_root: Path = api_app.state.settings.derived_path
    derived_root.mkdir(parents=True, exist_ok=True)
    return derived_root


async def indexed_medium(session: AsyncSession, library: Path, derived: Path) -> Media:
    """One photo, read and with its previews made, as the worker would leave it."""
    an_image(library / "2009 Italien" / "IMG_1.jpg")
    publication = await library_service.publish(
        session, relative_path="2009 Italien", library_base=library
    )

    settings = await settings_service.get_settings(session)
    # Two listings, far enough apart: only then is a file taken.
    await library_service.sync_publication(
        session, publication, settings=settings, library_base=library, now=NOW
    )
    report = await library_service.sync_publication(
        session, publication, settings=settings, library_base=library, now=LATER
    )

    for media_id in report.pending_derivatives:
        await service.apply_derivatives(
            session, media_id, library_base=library, derived_root=derived, settings=settings
        )

    media = await session.get(Media, report.pending_derivatives[0])
    assert media is not None
    return media


async def user_headers(
    api_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> dict[str, str]:
    await create_user(session_factory, username="anna", display_name="Anna")
    return auth_header(await login(api_client, username="anna"))


class TestStages:
    """What the pipeline did to one medium, and asking for one step again."""

    async def test_an_admin_sees_every_step_and_what_it_did(
        self,
        api_client: AsyncClient,
        session: AsyncSession,
        library: Path,
        derived: Path,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        media = await indexed_medium(session, library, derived)
        await create_user(
            session_factory, username="odin", display_name="Odin", role=UserRole.ADMIN
        )
        headers = auth_header(await login(api_client, username="odin"))

        answer = await api_client.get(f"/media/{media.id}/stages", headers=headers)

        assert answer.status_code == 200, answer.text
        steps = {step["stage"]: step for step in answer.json()["stages"]}
        # The preview was made when the medium was indexed; a photo has nothing to transcribe.
        assert steps["derive"]["state"] == "done"
        assert steps["transcription"]["state"] == "not-for-this"
        assert steps["faces"]["state"] == "open"

    async def test_asking_for_a_step_again_drops_what_it_wrote(
        self,
        api_client: AsyncClient,
        session: AsyncSession,
        library: Path,
        derived: Path,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        media = await indexed_medium(session, library, derived)
        await create_user(
            session_factory, username="odin", display_name="Odin", role=UserRole.ADMIN
        )
        headers = auth_header(await login(api_client, username="odin"))

        answer = await api_client.post(f"/media/{media.id}/stages/derive", headers=headers)

        assert answer.status_code == 202
        steps = {step["stage"]: step for step in answer.json()["stages"]}
        assert steps["derive"]["state"] == "open"
        await session.refresh(media)
        assert media.derive_version == 0

    async def test_only_admins_may_ask(
        self,
        api_client: AsyncClient,
        session: AsyncSession,
        library: Path,
        derived: Path,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        media = await indexed_medium(session, library, derived)
        await create_user(session_factory, username="anna", display_name="Anna")
        headers = auth_header(await login(api_client, username="anna"))

        answer = await api_client.get(f"/media/{media.id}/stages", headers=headers)

        assert answer.status_code == 403

    async def test_a_step_nobody_knows_is_not_found(
        self,
        api_client: AsyncClient,
        session: AsyncSession,
        library: Path,
        derived: Path,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        media = await indexed_medium(session, library, derived)
        await create_user(
            session_factory, username="odin", display_name="Odin", role=UserRole.ADMIN
        )
        headers = auth_header(await login(api_client, username="odin"))

        answer = await api_client.post(f"/media/{media.id}/stages/telepathy", headers=headers)

        assert answer.status_code == 404


class TestDeriving:
    async def test_previews_are_written_and_written_down(
        self, session: AsyncSession, library: Path, derived: Path
    ) -> None:
        media = await indexed_medium(session, library, derived)

        assert media.derive_version == DERIVE_VERSION
        assert media.pixel_hash is not None
        assert media.thumbnail_path is not None
        assert (derived / media.thumbnail_path).exists()
        assert media.preview_path is not None
        assert (derived / media.preview_path).exists()
        # What the files take on the server, for the overview beside the originals.
        written = [derived / media.thumbnail_path, derived / media.preview_path]
        assert media.derived_bytes == sum(path.stat().st_size for path in written)

    async def test_running_it_again_changes_nothing(
        self, session: AsyncSession, library: Path, derived: Path
    ) -> None:
        media = await indexed_medium(session, library, derived)
        assert media.thumbnail_path is not None
        written_at = (derived / media.thumbnail_path).stat().st_mtime

        settings = await settings_service.get_settings(session)
        done = await service.apply_derivatives(
            session, media.id, library_base=library, derived_root=derived, settings=settings
        )

        assert done is True
        assert (derived / media.thumbnail_path).stat().st_mtime == written_at

    async def test_an_edited_picture_gets_new_files_and_the_old_ones_go(
        self, session: AsyncSession, library: Path, derived: Path
    ) -> None:
        """New previews are written under a new name; the old ones only go afterwards."""
        media = await indexed_medium(session, library, derived)
        old_thumb = media.thumbnail_path
        assert old_thumb is not None

        an_image(library / "2009 Italien" / "IMG_1.jpg", red=10, width=640, height=480)
        settings = await settings_service.get_settings(session)
        publication = (await library_service.list_publications(session))[0]
        await library_service.sync_publication(
            session, publication, settings=settings, library_base=library, now=LATER
        )
        report = await library_service.sync_publication(
            session,
            publication,
            settings=settings,
            library_base=library,
            now=LATER + timedelta(minutes=1),
        )
        for media_id in report.pending_derivatives:
            await service.apply_derivatives(
                session,
                media_id,
                library_base=library,
                derived_root=derived,
                settings=settings,
            )
        await session.refresh(media)

        new_thumb = media.thumbnail_path
        assert new_thumb is not None
        assert new_thumb != old_thumb
        assert (derived / new_thumb).exists()
        assert not (derived / old_thumb).exists()

    async def test_removing_a_medium_removes_what_was_derived_from_it(
        self, session: AsyncSession, library: Path, derived: Path
    ) -> None:
        media = await indexed_medium(session, library, derived)
        folder = service.folder_of(derived, media.id)
        assert folder.exists()

        removed = await service.remove_derivatives(derived, [media.id])

        assert removed == 1
        assert not folder.exists()

    async def test_a_medium_whose_original_is_gone_is_not_an_error(
        self, session: AsyncSession, library: Path, derived: Path
    ) -> None:
        media = await indexed_medium(session, library, derived)
        (library / "2009 Italien" / "IMG_1.jpg").unlink()
        media.derive_version = 0
        await session.commit()

        settings = await settings_service.get_settings(session)
        done = await service.apply_derivatives(
            session, media.id, library_base=library, derived_root=derived, settings=settings
        )

        assert done is False


class TestServing:
    async def test_a_signed_address_delivers_the_thumbnail(
        self,
        api_client: AsyncClient,
        api_app: FastAPI,
        session: AsyncSession,
        session_factory: async_sessionmaker[AsyncSession],
        library: Path,
        derived: Path,
    ) -> None:
        media = await indexed_medium(session, library, derived)
        headers = await user_headers(api_client, session_factory)
        detail = await api_client.get(f"/media/{media.id}", headers=headers)
        thumb_url = detail.json()["urls"]["thumb"]

        response = await api_client.get(thumb_url.replace("/api/v1", ""))

        assert response.status_code == 200
        assert response.headers["content-type"] == "image/webp"
        assert detail.json()["has_previews"] is True

    async def test_without_a_signature_or_a_token_nothing_is_delivered(
        self,
        api_client: AsyncClient,
        session: AsyncSession,
        library: Path,
        derived: Path,
    ) -> None:
        media = await indexed_medium(session, library, derived)

        response = await api_client.get(f"/media/{media.id}/thumb")

        assert response.status_code == 401

    async def test_a_signature_for_another_variant_does_not_open_this_one(
        self,
        api_client: AsyncClient,
        api_app: FastAPI,
        session: AsyncSession,
        library: Path,
        derived: Path,
    ) -> None:
        media = await indexed_medium(session, library, derived)
        token = sign_media(media.id, "thumb", secret=api_app.state.settings.jwt_secret)

        response = await api_client.get(f"/media/{media.id}/original?token={token}")

        assert response.status_code == 401

    async def test_the_app_may_use_its_bearer_token_instead(
        self,
        api_client: AsyncClient,
        session: AsyncSession,
        session_factory: async_sessionmaker[AsyncSession],
        library: Path,
        derived: Path,
    ) -> None:
        """On the phone Muninn sends the token in the header; cookies do not survive there."""
        media = await indexed_medium(session, library, derived)
        headers = await user_headers(api_client, session_factory)

        response = await api_client.get(f"/media/{media.id}/thumb", headers=headers)

        assert response.status_code == 200

    async def test_the_original_comes_from_the_nas(
        self,
        api_client: AsyncClient,
        session: AsyncSession,
        session_factory: async_sessionmaker[AsyncSession],
        library: Path,
        derived: Path,
    ) -> None:
        media = await indexed_medium(session, library, derived)
        headers = await user_headers(api_client, session_factory)

        response = await api_client.get(f"/media/{media.id}/original", headers=headers)

        assert response.status_code == 200
        assert int(response.headers["content-length"]) > 0

    async def test_the_original_can_be_asked_for_as_a_download(
        self,
        api_client: AsyncClient,
        session: AsyncSession,
        session_factory: async_sessionmaker[AsyncSession],
        library: Path,
        derived: Path,
    ) -> None:
        """With ``download`` it lands in the downloads folder under its name from the NAS."""
        media = await indexed_medium(session, library, derived)
        headers = await user_headers(api_client, session_factory)

        response = await api_client.get(f"/media/{media.id}/original?download=1", headers=headers)

        assert response.status_code == 200
        assert 'attachment; filename="IMG_1.jpg"' in response.headers["content-disposition"]

    async def test_without_asking_it_stays_in_the_tab(
        self,
        api_client: AsyncClient,
        session: AsyncSession,
        session_factory: async_sessionmaker[AsyncSession],
        library: Path,
        derived: Path,
    ) -> None:
        media = await indexed_medium(session, library, derived)
        headers = await user_headers(api_client, session_factory)

        response = await api_client.get(f"/media/{media.id}/original", headers=headers)

        assert "attachment" not in response.headers.get("content-disposition", "")

    async def test_a_derived_file_is_named_after_the_original(
        self,
        api_client: AsyncClient,
        session: AsyncSession,
        session_factory: async_sessionmaker[AsyncSession],
        library: Path,
        derived: Path,
    ) -> None:
        """The name on the SSD is a hash; nobody wants that in their downloads folder."""
        media = await indexed_medium(session, library, derived)
        headers = await user_headers(api_client, session_factory)

        response = await api_client.get(f"/media/{media.id}/preview?download=1", headers=headers)

        assert 'filename="IMG_1-preview.webp"' in response.headers["content-disposition"]

    async def test_a_variant_that_does_not_exist_says_so(
        self,
        api_client: AsyncClient,
        session: AsyncSession,
        session_factory: async_sessionmaker[AsyncSession],
        library: Path,
        derived: Path,
    ) -> None:
        media = await indexed_medium(session, library, derived)
        headers = await user_headers(api_client, session_factory)

        response = await api_client.get(f"/media/{media.id}/video", headers=headers)

        assert response.status_code == 404
        assert response.json()["type"].endswith("variant-not-ready")

    async def test_an_unknown_medium_is_a_problem(
        self, api_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        headers = await user_headers(api_client, session_factory)

        response = await api_client.get(f"/media/{uuid.uuid4()}/thumb", headers=headers)

        assert response.status_code == 404


class TestAlbumCovers:
    async def test_an_album_carries_a_cover_once_a_preview_exists(
        self,
        api_client: AsyncClient,
        session: AsyncSession,
        session_factory: async_sessionmaker[AsyncSession],
        library: Path,
        derived: Path,
    ) -> None:
        await indexed_medium(session, library, derived)
        headers = await user_headers(api_client, session_factory)

        tree = await api_client.get("/albums/tree", headers=headers)
        album = next(
            item for item in tree.json()["items"] if item["relative_path"] == "2009 Italien"
        )
        cover = await api_client.get(str(album["cover_urls"][0]).replace("/api/v1", ""))

        assert album["cover_urls"] != []
        assert cover.status_code == 200
        assert cover.headers["content-type"] == "image/webp"

    async def test_a_folder_of_folders_borrows_from_the_albums_below_it(
        self,
        api_client: AsyncClient,
        session: AsyncSession,
        session_factory: async_sessionmaker[AsyncSession],
        library: Path,
        derived: Path,
    ) -> None:
        an_image(library / "Urlaub" / "2009 Italien" / "IMG_1.jpg")
        publication = await library_service.publish(
            session, relative_path="Urlaub", library_base=library
        )
        settings = await settings_service.get_settings(session)
        await library_service.sync_publication(
            session, publication, settings=settings, library_base=library, now=NOW
        )
        report = await library_service.sync_publication(
            session, publication, settings=settings, library_base=library, now=LATER
        )
        for media_id in report.pending_derivatives:
            await service.apply_derivatives(
                session, media_id, library_base=library, derived_root=derived, settings=settings
            )
        headers = await user_headers(api_client, session_factory)

        items = (await api_client.get("/albums/tree", headers=headers)).json()["items"]
        parent = next(item for item in items if item["relative_path"] == "Urlaub")
        child = next(item for item in items if item["relative_path"] == "Urlaub/2009 Italien")

        # "Urlaub" holds no pictures itself, so its tile shows what lies below it.
        assert parent["media_count"] == 0
        assert child["cover_urls"] != []
        assert parent["cover_urls"] == child["cover_urls"]


def _age(folder: Path, *, hours: int) -> None:
    """Make a folder look as old as it needs to be for the sweep to consider it."""
    old = time.time() - hours * 3600
    os.utime(folder, (old, old))


class TestSweepingUpPreviews:
    """Folders under the derived path that belong to no medium any more."""

    async def test_a_forgotten_folder_is_swept_up(
        self, session: AsyncSession, library: Path, derived: Path
    ) -> None:
        media = await indexed_medium(session, library, derived)
        orphan = service.folder_of(derived, uuid.uuid4())
        orphan.mkdir(parents=True)
        (orphan / "thumb-abc.webp").write_bytes(b"left over")
        _age(orphan, hours=2)

        removed = await service.remove_orphans(session, derived)

        assert not orphan.exists()
        assert len(removed) == 1
        # The medium that is still there keeps its previews.
        assert service.folder_of(derived, media.id).exists()

    async def test_a_dry_run_only_says_what_it_would_do(
        self, session: AsyncSession, library: Path, derived: Path
    ) -> None:
        await indexed_medium(session, library, derived)
        orphan = service.folder_of(derived, uuid.uuid4())
        orphan.mkdir(parents=True)
        _age(orphan, hours=2)

        removed = await service.remove_orphans(session, derived, dry_run=True)

        assert len(removed) == 1
        assert orphan.exists()

    async def test_a_folder_that_may_still_be_written_is_left_alone(
        self, session: AsyncSession, library: Path, derived: Path
    ) -> None:
        """A derivation in progress looks exactly like a leftover, so age is the only guard."""
        await indexed_medium(session, library, derived)
        fresh = service.folder_of(derived, uuid.uuid4())
        fresh.mkdir(parents=True)

        removed = await service.remove_orphans(session, derived)

        assert removed == []
        assert fresh.exists()

    async def test_it_refuses_to_sweep_when_no_media_are_known(
        self, session: AsyncSession, library: Path, derived: Path
    ) -> None:
        """No media at all is what a database that cannot answer looks like from here."""
        orphan = service.folder_of(derived, uuid.uuid4())
        orphan.mkdir(parents=True)
        _age(orphan, hours=2)

        assert await service.remove_orphans(session, derived) == []
        assert orphan.exists()

        # Only when it is said out loud, because an installation can genuinely hold nothing.
        assert len(await service.remove_orphans(session, derived, allow_empty=True)) == 1
        assert not orphan.exists()

    async def test_something_muninn_did_not_write_is_not_touched(
        self, session: AsyncSession, library: Path, derived: Path
    ) -> None:
        await indexed_medium(session, library, derived)
        stranger = derived / "ab" / "not-a-media-id"
        stranger.mkdir(parents=True)
        _age(stranger, hours=2)

        removed = await service.remove_orphans(session, derived)

        assert removed == []
        assert stranger.exists()


class TestUnpublishing:
    async def test_the_previews_go_with_it(
        self,
        api_client: AsyncClient,
        session: AsyncSession,
        session_factory: async_sessionmaker[AsyncSession],
        library: Path,
        derived: Path,
    ) -> None:
        """The database forgets the rows; somebody has to remove the files on the SSD."""
        media = await indexed_medium(session, library, derived)
        folder = service.folder_of(derived, media.id)
        assert folder.exists()

        await create_user(
            session_factory, username="admin", display_name="Admin", role=UserRole.ADMIN
        )
        headers = auth_header(await login(api_client, username="admin"))
        publication = (await library_service.list_publications(session))[0]
        response = await api_client.delete(
            f"/admin/library/publications/{publication.id}", headers=headers
        )

        assert response.status_code == 204
        assert not folder.exists()
