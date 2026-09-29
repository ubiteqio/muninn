"""Doppelgänger: media that are one picture, and which of them to keep.

Three ties make a group, from the tightest to the loosest:

- exact: the same file (content hash) in two places,
- near: the same picture made smaller or compressed again - a WhatsApp copy - by fingerprint,
- burst: shots taken within seconds whose pictures are nearly the same, by the picture model.

A job finds the groups again every quarter of an hour. The best of a group is the one with the
most pixels, then the most complete metadata, then the original format, then the largest file.
An admin may hide the others. Muninn never deletes: the paths of what was hidden can be
downloaded as a list, to delete on the NAS by hand.
"""

import asyncio
import math
import re
import uuid
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import ColumnElement, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from muninn.ai import service as ai_service
from muninn.duplicates import fingerprint as fingerprints
from muninn.models.ai import AiKind
from muninn.models.duplicate import DuplicateGroup, DuplicateMember
from muninn.models.media import IMPRECISE_DATE_SOURCES, Media, MediaFile, MediaFileRole, MediaStatus
from muninn.search import service as search_service

#: Raised when the fingerprint is computed differently; every medium is then read again.
FINGERPRINT_VERSION = 1

#: How many thumbnails are read in one go. A thumbnail takes a few milliseconds.
FINGERPRINT_BATCH = 1_000

#: Bits that may differ for two pictures to count as the same. Measured on the library: copies
#: shrunk to 40 % at JPEG quality 35 differed in at most 4 of 64 bits in 99 of 100 cases.
NEAR_MAX_BITS = 4

#: The fingerprint is split into this many parts for the search: two that differ in at most
#: NEAR_MAX_BITS bits share at least one part exactly.
_PARTS = NEAR_MAX_BITS + 1

#: A burst: taken within this many seconds, pictures this close by the picture model (cosine
#: distance, 0 is the same). Looked at on the library: up to 0.03 the same moment with another
#: face or a slightly moved frame; at 0.05 already another pose or angle, worth keeping both.
BURST_WINDOW_SECONDS = 10
BURST_MAX_DISTANCE = 0.03

KINDS = ("exact", "near", "burst")

#: File names that say a picture went through a messenger and lost its original on the way.
_MESSENGER = re.compile(r"(?:^IMG-\d{8}-WA\d+|^signal-|^PHOTO-\d{4}-\d{2}-\d{2})", re.IGNORECASE)


# --- fingerprints --------------------------------------------------------------------------------


async def fingerprint_media(
    session: AsyncSession, derived_root: Path, *, batch: int = FINGERPRINT_BATCH
) -> int:
    """Read the fingerprints of the next media whose thumbnail has none yet. Returns how many."""
    due = list(
        await session.execute(
            select(Media.id, Media.thumbnail_path)
            .where(
                Media.status == MediaStatus.ACTIVE,
                Media.thumbnail_path.is_not(None),
                Media.fingerprint_version < FINGERPRINT_VERSION,
            )
            .limit(batch)
        )
    )
    if not due:
        return 0

    def read_all() -> dict[uuid.UUID, int | None]:
        found: dict[uuid.UUID, int | None] = {}
        for media_id, thumbnail in due:
            try:
                found[media_id] = fingerprints.as_signed(
                    fingerprints.fingerprint(derived_root / thumbnail)
                )
            except Exception:
                found[media_id] = None
        return found

    for media_id, value in (await asyncio.to_thread(read_all)).items():
        await session.execute(
            update(Media)
            .where(Media.id == media_id)
            .values(fingerprint=value, fingerprint_version=FINGERPRINT_VERSION)
        )
    await session.commit()
    return len(due)


# --- finding the groups --------------------------------------------------------------------------


def near_pairs(prints: dict[uuid.UUID, int]) -> list[tuple[uuid.UUID, uuid.UUID]]:
    """Pairs whose fingerprints differ in at most NEAR_MAX_BITS.

    Comparing every picture with every other would be 10 billion comparisons for 150,000. Split
    into five parts of 12 or 13 bits, two fingerprints that differ in at most four bits share at
    least one part exactly - so only pictures that share a part are compared.
    """
    width = math.ceil(64 / _PARTS)
    buckets: dict[tuple[int, int], list[uuid.UUID]] = defaultdict(list)
    for media_id, value in prints.items():
        unsigned = fingerprints.as_unsigned(value)
        for part in range(_PARTS):
            buckets[(part, (unsigned >> (width * part)) & ((1 << width) - 1))].append(media_id)

    pairs: set[tuple[uuid.UUID, uuid.UUID]] = set()
    for members in buckets.values():
        if len(members) < 2:
            continue
        for index, first in enumerate(members):
            for second in members[index + 1 :]:
                pair = (first, second) if str(first) < str(second) else (second, first)
                if pair in pairs:
                    continue
                if fingerprints.distance(prints[first], prints[second]) <= NEAR_MAX_BITS:
                    pairs.add(pair)
    return sorted(pairs)


class _Groups:
    """Union-find: every pair joins two groups, and a group remembers its loosest tie."""

    def __init__(self) -> None:
        self.parent: dict[uuid.UUID, uuid.UUID] = {}
        self.kind: dict[uuid.UUID, int] = {}

    def root(self, item: uuid.UUID) -> uuid.UUID:
        self.parent.setdefault(item, item)
        while self.parent[item] != item:
            self.parent[item] = self.parent[self.parent[item]]
            item = self.parent[item]
        return item

    def join(self, pairs: Iterable[tuple[uuid.UUID, uuid.UUID]], kind: int) -> None:
        for first, second in pairs:
            a, b = self.root(first), self.root(second)
            # Two exact copies are near each other too; that tie adds nothing to the group.
            if a == b:
                continue
            self.parent[b] = a
            self.kind[a] = max(self.kind.get(a, kind), self.kind.get(b, kind), kind)

    def groups(self) -> list[tuple[str, list[uuid.UUID]]]:
        members: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
        for item in self.parent:
            members[self.root(item)].append(item)
        return [
            (KINDS[self.kind[root]], items) for root, items in members.items() if len(items) > 1
        ]


def best_first(media: list[Media]) -> list[Media]:
    """The one to keep first: most pixels, then the most complete metadata, then the original
    format rather than a messenger's copy, then the larger file."""

    def rank(medium: Media) -> tuple[int, int, int, int, str]:
        pixels = (medium.width or 0) * (medium.height or 0)
        metadata = sum(
            [
                medium.taken_at_source is not None
                and medium.taken_at_source not in IMPRECISE_DATE_SOURCES,
                medium.camera_model is not None,
                medium.latitude is not None,
            ]
        )
        original = 0 if _MESSENGER.search(medium.primary_file.filename) else 1
        return (-pixels, -metadata, -original, -medium.primary_file.byte_size, str(medium.id))

    return sorted(media, key=rank)


async def find_groups(session: AsyncSession) -> int:
    """Find every group again and replace the old ones. Returns how many there are."""
    exact: list[tuple[uuid.UUID, uuid.UUID]] = []
    by_hash: dict[str, list[uuid.UUID]] = defaultdict(list)
    prints: dict[uuid.UUID, int] = {}
    rows = await session.execute(
        select(Media.id, Media.content_hash, Media.fingerprint).where(
            Media.status == MediaStatus.ACTIVE
        )
    )
    for media_id, content_hash, value in rows:
        by_hash[content_hash].append(media_id)
        if value is not None:
            prints[media_id] = value
    for same in by_hash.values():
        exact.extend((same[0], other) for other in same[1:])

    groups = _Groups()
    groups.join(exact, KINDS.index("exact"))
    groups.join(near_pairs(prints), KINDS.index("near"))
    pictures = await ai_service.active_profile(session, AiKind.IMAGE_EMBEDDER)
    if pictures is not None:
        groups.join(
            await search_service.burst_pairs(
                session,
                model=pictures.model,
                window_seconds=BURST_WINDOW_SECONDS,
                max_distance=BURST_MAX_DISTANCE,
            ),
            KINDS.index("burst"),
        )
    found = groups.groups()

    await session.execute(delete(DuplicateGroup))
    for kind, members in found:
        media = list(
            await session.scalars(
                select(Media).where(Media.id.in_(members)).options(selectinload(Media.files))
            )
        )
        ordered = best_first(media)
        taken = [medium.taken_at for medium in media if medium.taken_at is not None]
        group = DuplicateGroup(kind=kind, size=len(media), newest=max(taken) if taken else None)
        session.add(group)
        await session.flush()
        session.add_all(
            DuplicateMember(
                group_id=group.id, media_id=medium.id, best=position == 0, position=position
            )
            for position, medium in enumerate(ordered)
        )
    await session.commit()
    return len(found)


# --- what the admin sees and decides -------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Group:
    id: int
    kind: str
    #: Best first. Hidden ones carry duplicate_of.
    media: list[Media]


#: How much disk a group holds altogether, for sorting the heaviest to the top.
def _bytes_of_group() -> ColumnElement[int]:
    """The size of a group's primary files added up.

    ``DuplicateGroup.size`` is how many media are in it, not how much room they take. Somebody
    working through copies to win back disk wants the heavy ones first, and two 4K videos are
    worth more than forty photographs of a birthday.
    """
    return (
        select(func.coalesce(func.sum(MediaFile.byte_size), 0))
        .select_from(DuplicateMember)
        .join(MediaFile, MediaFile.media_id == DuplicateMember.media_id)
        .where(
            DuplicateMember.group_id == DuplicateGroup.id,
            MediaFile.role == MediaFileRole.PRIMARY,
        )
        .scalar_subquery()
    )


async def list_groups(
    session: AsyncSession,
    *,
    open_only: bool,
    offset: int,
    limit: int,
    by_size: bool = False,
) -> tuple[list[Group], bool]:
    """Newest first, or heaviest first. "Open" groups are those nobody has decided on yet: none
    of their media is hidden. Keeping two shots of a burst is a decision as much as keeping
    one."""
    order = (
        (_bytes_of_group().desc(), DuplicateGroup.id)
        if by_size
        else (DuplicateGroup.newest.desc().nulls_last(), DuplicateGroup.id)
    )
    query = select(DuplicateGroup).order_by(*order)
    if open_only:
        decided = (
            select(DuplicateMember.group_id)
            .join(Media, Media.id == DuplicateMember.media_id)
            .where(DuplicateMember.group_id == DuplicateGroup.id, Media.duplicate_of.is_not(None))
            .exists()
        )
        query = query.where(~decided)
    rows = list(await session.scalars(query.offset(offset).limit(limit + 1)))
    page = rows[:limit]
    members = list(
        await session.execute(
            select(DuplicateMember.group_id, Media)
            .join(Media, Media.id == DuplicateMember.media_id)
            .where(DuplicateMember.group_id.in_([group.id for group in page]))
            .order_by(DuplicateMember.group_id, DuplicateMember.position)
            .options(selectinload(Media.files))
        )
    )
    by_group: dict[int, list[Media]] = defaultdict(list)
    for group_id, medium in members:
        by_group[group_id].append(medium)
    return (
        [Group(id=group.id, kind=group.kind, media=by_group[group.id]) for group in page],
        len(rows) > limit,
    )


async def count_open(session: AsyncSession) -> int:
    groups, _ = await list_groups(session, open_only=True, offset=0, limit=100_000)
    return len(groups)


class NotInGroupError(Exception):
    """The medium to keep is not part of that group."""


async def keep(session: AsyncSession, group_id: int, keep_ids: list[uuid.UUID]) -> list[uuid.UUID]:
    """Hide every medium of the group but these - one, or a few good shots of a burst. The
    hidden ones point at the first kept. Returns the hidden ones."""
    members = list(
        await session.scalars(
            select(DuplicateMember.media_id)
            .where(DuplicateMember.group_id == group_id)
            .order_by(DuplicateMember.position)
        )
    )
    if not keep_ids or any(media_id not in members for media_id in keep_ids):
        raise NotInGroupError
    first = next(media_id for media_id in members if media_id in keep_ids)
    hidden = [media_id for media_id in members if media_id not in keep_ids]
    await session.execute(update(Media).where(Media.id.in_(keep_ids)).values(duplicate_of=None))
    await session.execute(update(Media).where(Media.id.in_(hidden)).values(duplicate_of=first))
    await session.commit()
    return hidden


async def show_again(session: AsyncSession, media_id: uuid.UUID) -> bool:
    result = await session.execute(
        update(Media).where(Media.id == media_id).values(duplicate_of=None)
    )
    await session.commit()
    return bool(getattr(result, "rowcount", 0))


async def hidden_media(session: AsyncSession) -> list[tuple[Media, Media | None]]:
    """What was hidden, beside what it is a copy of: the list to delete on the NAS by hand."""
    hidden = list(
        await session.scalars(
            select(Media)
            .where(Media.duplicate_of.is_not(None))
            .options(selectinload(Media.files))
            .order_by(Media.duplicate_of, Media.id)
        )
    )
    kept_ids = {medium.duplicate_of for medium in hidden if medium.duplicate_of is not None}
    kept = {
        medium.id: medium
        for medium in await session.scalars(
            select(Media).where(Media.id.in_(kept_ids)).options(selectinload(Media.files))
        )
    }
    return [
        (medium, kept.get(medium.duplicate_of) if medium.duplicate_of else None)
        for medium in hidden
    ]
