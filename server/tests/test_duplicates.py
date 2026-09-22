"""Doppelgänger: fingerprints, groups of copies, the best of them, and hiding the rest."""

import uuid
from datetime import timedelta
from pathlib import Path

import pytest
import pyvips
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from muninn.duplicates import fingerprint as fingerprints
from muninn.duplicates import service
from muninn.models.duplicate import DuplicateGroup, DuplicateMember
from muninn.models.media import DateSource, Media
from muninn.models.user import UserRole
from muninn.search.service import VectorKind, store
from tests.helpers import auth_header, create_user, login
from tests.test_image_vectors import a_picture_model
from tests.test_timeline import JULY, a_medium, an_album

pytestmark = pytest.mark.usefixtures("api_client")


def _picture(path: Path, *, seed: int, width: int = 640, height: int = 480) -> Path:
    """A picture with some structure: shapes of grey from a fixed seed."""
    noise = pyvips.Image.gaussnoise(64, 48, sigma=60, mean=128, seed=seed)
    noise.resize(width / 64, vscale=height / 48, kernel="linear").cast("uchar").write_to_file(
        str(path)
    )
    return path


class TestFingerprint:
    def test_a_smaller_and_more_compressed_copy_keeps_its_fingerprint(self, tmp_path: Path) -> None:
        original = _picture(tmp_path / "original.png", seed=1)
        copy = tmp_path / "copy.jpg"
        pyvips.Image.new_from_file(str(original)).resize(0.4).write_to_file(f"{copy}[Q=35]")
        other = _picture(tmp_path / "other.png", seed=2)

        first = fingerprints.fingerprint(original)

        assert fingerprints.distance(first, fingerprints.fingerprint(copy)) <= 2
        assert fingerprints.distance(first, fingerprints.fingerprint(other)) > service.NEAR_MAX_BITS

    def test_the_bits_are_stored_signed_and_come_back(self) -> None:
        for bits in (0, 1, (1 << 63) - 1, 1 << 63, (1 << 64) - 1):
            signed = fingerprints.as_signed(bits)
            assert -(1 << 63) <= signed < 1 << 63
            assert fingerprints.as_unsigned(signed) == bits

    def test_near_pairs_find_what_differs_in_a_few_bits_only(self) -> None:
        a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        base = 0x0123_4567_89AB_CDEF
        prints = {
            a: fingerprints.as_signed(base),
            b: fingerprints.as_signed(base ^ 0b1011),
            c: fingerprints.as_signed(base ^ 0xFFFF_0000_FFFF_0000),
            # Four bits apart, one in each of four parts: still found.
            uuid.UUID(int=4): fingerprints.as_signed(base ^ (1 | 1 << 14 | 1 << 28 | 1 << 42)),
        }

        pairs = service.near_pairs(prints)

        assert set(pairs) == {
            tuple(sorted(pair, key=str))
            for pair in ((a, b), (a, uuid.UUID(int=4)), (b, uuid.UUID(int=4)))
            if fingerprints.distance(prints[pair[0]], prints[pair[1]]) <= 4
        }
        assert tuple(sorted((a, uuid.UUID(int=4)), key=str)) in pairs


async def _copy(
    session: AsyncSession,
    album: str,
    name: str,
    *,
    content_hash: str | None = None,
    fingerprint: int | None = None,
    size: tuple[int, int] = (4000, 3000),
    seconds: int = 0,
) -> Media:
    medium = await a_medium(
        session,
        await an_album(session, f"{album}-{uuid.uuid4().hex[:4]}"),
        taken_at=JULY,
        name=name,
    )
    medium.taken_at = JULY + timedelta(seconds=seconds)
    medium.taken_at_source = DateSource.EXIF
    medium.width, medium.height = size
    if content_hash is not None:
        medium.content_hash = content_hash
    if fingerprint is not None:
        medium.fingerprint = fingerprints.as_signed(fingerprint)
    await session.commit()
    return medium


async def _members(session: AsyncSession) -> dict[str, list[tuple[uuid.UUID, bool]]]:
    groups = {group.id: group.kind for group in await session.scalars(select(DuplicateGroup))}
    found: dict[str, list[tuple[uuid.UUID, bool]]] = {}
    for member in await session.scalars(
        select(DuplicateMember).order_by(DuplicateMember.group_id, DuplicateMember.position)
    ):
        found.setdefault(groups[member.group_id], []).append((member.media_id, member.best))
    return found


async def test_copies_are_grouped_and_the_best_comes_first(session: AsyncSession) -> None:
    same = "a" * 64
    # The same file twice has the same fingerprint too - still an exact group.
    first = await _copy(
        session, "Urlaub", "IMG_1.jpg", content_hash=same, fingerprint=0xABC, size=(4000, 3000)
    )
    again = await _copy(
        session, "Backup", "IMG_1.jpg", content_hash=same, fingerprint=0xABC, size=(4000, 3000)
    )
    whatsapp = await _copy(
        session, "Chat", "IMG-20090714-WA0001.jpg", fingerprint=0xF0F0, size=(1600, 1200)
    )
    camera = await _copy(session, "Kamera", "DSC_1.jpg", fingerprint=0xF0F1, size=(4000, 3000))
    await _copy(session, "Anders", "DSC_2.jpg", fingerprint=0x0F0F_0000_FFFF)
    await a_picture_model(session)
    shot = await _copy(session, "Serie", "B_1.jpg", seconds=100)
    next_shot = await _copy(session, "Serie", "B_2.jpg", seconds=104)
    much_later = await _copy(session, "Serie", "B_3.jpg", seconds=200)
    for medium, vector in ((shot, [1.0, 0.0, 0.0]), (next_shot, [0.999, 0.03, 0.0]),
                           (much_later, [1.0, 0.0, 0.0])):  # fmt: skip
        await store(
            session, VectorKind.IMAGE, media_id=medium.id, model="siglip2", version=1,
            vector=vector,
        )  # fmt: skip
    await session.commit()

    assert await service.find_groups(session) == 3

    groups = await _members(session)
    assert {media_id for media_id, _ in groups["exact"]} == {first.id, again.id}
    # The camera's file beats the messenger's smaller copy.
    assert groups["near"] == [(camera.id, True), (whatsapp.id, False)]
    assert {media_id for media_id, _ in groups["burst"]} == {shot.id, next_shot.id}


async def test_fingerprints_are_read_from_the_thumbnails(
    session: AsyncSession, tmp_path: Path
) -> None:
    medium = await _copy(session, "Urlaub", "IMG_1.jpg")
    medium.thumbnail_path = "t/thumb.png"
    (tmp_path / "t").mkdir()
    _picture(tmp_path / "t" / "thumb.png", seed=3, width=320, height=240)
    broken = await _copy(session, "Urlaub", "IMG_2.jpg")
    broken.thumbnail_path = "t/missing.png"
    await session.commit()

    assert await service.fingerprint_media(session, tmp_path) == 2
    assert await service.fingerprint_media(session, tmp_path) == 0

    await session.refresh(medium)
    await session.refresh(broken)
    assert medium.fingerprint is not None
    assert broken.fingerprint is None


async def _admin(
    api_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> dict[str, str]:
    await create_user(session_factory, username="admin", display_name="Admin", role=UserRole.ADMIN)
    return auth_header(await login(api_client, username="admin"))


async def test_an_admin_keeps_one_and_the_others_leave_the_albums(
    api_client: AsyncClient,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    same = "b" * 64
    keep = await _copy(session, "Urlaub", "IMG_1.jpg", content_hash=same)
    copy = await _copy(session, "Backup", "IMG_1.jpg", content_hash=same)
    await service.find_groups(session)
    headers = await _admin(api_client, session_factory)

    listed = (await api_client.get("/admin/duplicates", headers=headers)).json()
    (group,) = listed["items"]
    assert listed["open_count"] == 1
    assert group["kind"] == "exact"

    response = await api_client.post(
        f"/admin/duplicates/{group['id']}/keep", json={"media_ids": [str(keep.id)]}, headers=headers
    )

    assert response.status_code == 204
    assert (await api_client.get("/admin/duplicates", headers=headers)).json()["items"] == []
    everything = (
        await api_client.get("/admin/duplicates", params={"state": "all"}, headers=headers)
    ).json()["items"]
    assert [member["hidden"] for member in everything[0]["members"]] == [False, True] or [
        member["hidden"] for member in everything[0]["members"]
    ] == [True, False]
    album = (await api_client.get(f"/albums/{copy.album_id}/media", headers=headers)).json()
    assert album["items"] == []

    listing = await api_client.get("/admin/duplicates/hidden.csv", headers=headers)
    rows = listing.text.strip().splitlines()
    assert rows[0] == "path;copy_of"
    assert rows[1] == f"{copy.primary_file.relative_path};{keep.primary_file.relative_path}"

    await api_client.delete(f"/admin/duplicates/hidden/{copy.id}", headers=headers)
    album = (await api_client.get(f"/albums/{copy.album_id}/media", headers=headers)).json()
    assert [item["id"] for item in album["items"]] == [str(copy.id)]


async def test_only_admins_see_the_duplicates(
    api_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await create_user(session_factory, username="anna", display_name="Anna")
    headers = auth_header(await login(api_client, username="anna"))

    assert (await api_client.get("/admin/duplicates", headers=headers)).status_code == 403


async def test_keeping_a_medium_from_another_group_is_refused(
    api_client: AsyncClient,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    same = "c" * 64
    await _copy(session, "Urlaub", "IMG_1.jpg", content_hash=same)
    await _copy(session, "Backup", "IMG_1.jpg", content_hash=same)
    stranger = await _copy(session, "Anders", "IMG_9.jpg")
    await service.find_groups(session)
    headers = await _admin(api_client, session_factory)
    (group,) = (await api_client.get("/admin/duplicates", headers=headers)).json()["items"]

    response = await api_client.post(
        f"/admin/duplicates/{group['id']}/keep",
        json={"media_ids": [str(stranger.id)]},
        headers=headers,
    )

    assert response.status_code == 404


async def test_a_few_shots_of_a_burst_can_stay(session: AsyncSession) -> None:
    same = "d" * 64
    shots = [await _copy(session, "Serie", f"B_{n}.jpg", content_hash=same) for n in range(4)]
    await service.find_groups(session)
    group_id = await session.scalar(select(DuplicateGroup.id))
    assert group_id is not None

    hidden = await service.keep(session, group_id, [shots[1].id, shots[3].id])

    assert set(hidden) == {shots[0].id, shots[2].id}
    for shot in shots:
        await session.refresh(shot)
    assert [shot.duplicate_of is None for shot in shots] == [False, True, False, True]
    # Keeping two is a decision too: the group is no longer open.
    open_groups, _ = await service.list_groups(session, open_only=True, offset=0, limit=10)
    assert open_groups == []
    assert await service.count_open(session) == 0
