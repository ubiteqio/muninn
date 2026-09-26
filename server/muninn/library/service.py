"""The library domain: which folders are published, and keeping them in step with the NAS.

The folder the host mounts is the library. Muninn never chooses it and never writes into it; it
reads. What is chosen here is which folders below it appear under Albums - with everything
beneath them, and in the place the original has, so an album is found where one expects it.

Only this module talks to the database. The listing, the grouping, the hashes and the metadata
reader below it are pure; what they find is turned into rows here.
"""

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import NamedTuple

from sqlalchemy import delete, func, or_, select, true
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from muninn.huginn import attempts
from muninn.huginn.derive import DERIVE_VERSION
from muninn.library import safety
from muninn.library.formats import kind_of
from muninn.library.grouping import MediaGroup, group_files
from muninn.library.hashing import hash_file, quick_hash_file
from muninn.library.metadata import METADATA_VERSION, read_metadata
from muninn.library.scanner import ScannedFile, ScannedFolder, is_ignored, walk
from muninn.media import service as media_service
from muninn.models.album import Album
from muninn.models.change_log import RETENTION_DAYS, ChangeKind, ChangeLogEntry, SyncTrigger
from muninn.models.media import (
    Media,
    MediaFile,
    MediaFileRole,
    MediaKind,
    MediaStatus,
    shown,
)
from muninn.models.pending_file import PendingFile
from muninn.models.publication import Publication, ScanStatus
from muninn.models.settings import AppSettings
from muninn.models.unreadable import UnreadableFile


class PublicationNotFoundError(Exception):
    pass


class PathNotAllowedError(Exception):
    """The folder is outside the mounted library, or does not exist."""


class AlreadyPublishedError(Exception):
    """This folder, or a folder above it, is published already."""


#: How often a running read reports itself, in files. Often enough to move visibly, rarely
#: enough that the reporting costs nothing worth measuring.
PROGRESS_EVERY = 10


@dataclass(frozen=True, slots=True)
class SyncProgress:
    """Where a running sync stands, counted in files.

    Folders are the wrong unit: one of them can hold a thousand pictures and take minutes, while
    another holds three. What somebody watching wants to know is how many files of how many.
    """

    #: Files this read found in the folders it actually reads.
    files_total: int
    #: Files it has handled so far.
    files_done: int
    #: The folder being read right now, as context.
    current: str


#: Called after every folder. The service knows no Redis; the worker does the reporting.
ProgressCallback = Callable[[SyncProgress], Awaitable[None]]

#: Asked between folders. True means an admin wants this read to stop.
StopCheck = Callable[[], Awaitable[bool]]

_logger = logging.getLogger(__name__)


class Unreadable(NamedTuple):
    """A file the reading could not open, and what the operating system said about it."""

    relative_path: str
    reason: str


@dataclass(slots=True)
class SyncReport:
    """What one sync found. Also what the admin area and the album show afterwards."""

    status: ScanStatus = ScanStatus.OK
    albums: int = 0
    added: int = 0
    #: The file changed; everything derived from it has to be built again.
    changed: int = 0
    #: Only size or time changed while the content stayed the same.
    touched: int = 0
    moved: int = 0
    missing: int = 0
    restored: int = 0
    removed: int = 0
    #: Files that are still being written and wait for the next sync.
    waiting: int = 0
    unchanged_folders: int = 0
    #: Folders that could not be listed. They prove nothing and are left as they are.
    failed_folders: int = 0
    #: Files that could not be read. Skipped, never treated as gone, and reported.
    unreadable: list["Unreadable"] = field(default_factory=list)
    #: Media whose metadata still have to be read; the caller queues them.
    pending_metadata: list[uuid.UUID] = field(default_factory=list)
    #: Media whose previews still have to be made.
    pending_derivatives: list[uuid.UUID] = field(default_factory=list)
    #: Media that were removed for good; the caller throws their derivatives away.
    removed_media: list[uuid.UUID] = field(default_factory=list)
    #: How many new media each album got, by album id as text; the caller tells everybody.
    added_by_album: dict[str, int] = field(default_factory=dict)
    message: str | None = None


# --- the library --------------------------------------------------------------


def resolve_inside(library_base: Path, relative_path: str | Path) -> Path:
    """A folder below the mounted library, or an error.

    Folders are chosen by an admin in the browser, so the path has to be checked rather than
    trusted: nothing outside the mount may ever be read.
    """
    base = library_base.resolve()
    candidate = Path(relative_path)
    resolved = (base / candidate).resolve() if not candidate.is_absolute() else candidate.resolve()

    if resolved != base and base not in resolved.parents:
        raise PathNotAllowedError(str(relative_path))
    if not resolved.is_dir():
        raise PathNotAllowedError(str(relative_path))
    return resolved


def relative_to(library_base: Path, folder: Path) -> str:
    """The path below the library, as it is stored everywhere."""
    relative = folder.relative_to(library_base.resolve())
    return "" if str(relative) == "." else str(relative)


async def browse(
    session: AsyncSession, *, library_base: Path, relative_path: str = ""
) -> tuple[dict[str, object], list[dict[str, object]]]:
    """The folder one is looking at, and the folders below it.

    The folder itself is part of the answer because pictures often lie directly in the mounted
    library, with no subfolder to choose at all.
    """
    folder = resolve_inside(library_base, relative_path)
    publications = await list_publications(session)
    return await asyncio.to_thread(_describe, folder, library_base, publications)


def _describe(
    folder: Path, base: Path, published: list[Publication]
) -> tuple[dict[str, object], list[dict[str, object]]]:
    """One listing of this folder: what it holds, and which folders lie in it.

    Counting the media of every subfolder as well would mean one listing per subfolder, and over
    SMB that costs seconds each. The count is therefore only given for the folder one is standing
    in; stepping into a folder answers the question for that one.
    """
    entries = sorted(_safe_iterdir(folder), key=lambda item: item.name.casefold())

    media_files = sum(
        1
        for child in entries
        if child.is_file() and not is_ignored(child.name, ()) and kind_of(child.name)
    )
    children = [
        _entry_of(child, base, published)
        for child in entries
        if child.is_dir() and not is_ignored(child.name, ())
    ]

    return _entry_of(folder, base, published, media_files=media_files), children


def _safe_iterdir(folder: Path) -> list[Path]:
    try:
        return list(folder.iterdir())
    except OSError:
        return []


def _entry_of(
    folder: Path, base: Path, published: list[Publication], media_files: int | None = None
) -> dict[str, object]:
    relative = relative_to(base, folder)
    covering = next(
        (publication for publication in published if _covers(publication.relative_path, relative)),
        None,
    )
    excluded = covering is not None and any(
        _covers(path, relative) for path in covering.excluded_paths
    )

    return {
        "name": folder.name,
        "path": str(folder),
        "relative_path": relative,
        "is_mount": _is_mount(folder),
        #: Published itself, or covered by a folder above it - and not switched off again.
        "published": covering is not None and not excluded,
        #: Inside a published folder, but switched off: by itself or by a folder above it.
        "excluded": excluded,
        #: The published folder it lies in, to switch it off or on again.
        "publication_id": covering.id if covering is not None else None,
        #: Whether it is the published folder itself, which cannot be switched off from inside.
        "is_publication": covering is not None and covering.relative_path == relative,
        #: Media lying directly in it, counted only where it costs nothing: the folder that was
        #: listed. Null means "not counted", not "empty".
        "media_files": media_files,
    }


def _is_mount(folder: Path) -> bool:
    """Whether this folder is a mount of its own - a share, rather than a folder inside one."""
    try:
        return folder.is_mount()
    except OSError:
        return False


def _covers(publication_path: str, relative_path: str) -> bool:
    """Whether a published folder holds this path - itself or anywhere below it."""
    if publication_path == "":
        return True
    return relative_path == publication_path or relative_path.startswith(f"{publication_path}/")


# --- published folders --------------------------------------------------------


async def list_publications(session: AsyncSession) -> list[Publication]:
    query = select(Publication).order_by(Publication.relative_path)
    return list(await session.scalars(query))


async def get_publication(session: AsyncSession, publication_id: uuid.UUID) -> Publication:
    publication = await session.get(Publication, publication_id)
    if publication is None:
        raise PublicationNotFoundError
    return publication


async def waiting_files(session: AsyncSession, relative_path: str) -> int:
    """Files below this folder that were seen once and wait for the second look.

    Without this a read that found only half-copied files looks exactly like a read that found
    nothing at all.
    """
    query = select(func.count()).select_from(PendingFile)
    if relative_path:
        query = query.where(PendingFile.relative_path.startswith(f"{relative_path}/"))
    return int(await session.scalar(query) or 0)


async def waiting_for_a_second_look(
    session: AsyncSession, *, stability_seconds: int, now: datetime
) -> list[Publication]:
    """Published folders whose waiting files are old enough to be looked at again.

    A file is taken once two listings a stability window apart agree. The second listing is due
    here, and the clock asks for it: a task held back in a worker's memory would be lost with
    that worker, and Redis hands such a task back only after an hour.
    """
    cutoff = now - timedelta(seconds=stability_seconds)
    rows = await session.scalars(
        select(PendingFile.relative_path).where(PendingFile.first_seen_at <= cutoff)
    )
    paths = list(rows)
    if not paths:
        return []

    return [
        publication
        for publication in await list_publications(session)
        if publication.enabled and any(_covers(publication.relative_path, path) for path in paths)
    ]


async def files_waiting(session: AsyncSession, *, limit: int = 200) -> list[PendingFile]:
    """The files seen once and waiting for the listing that confirms them, oldest first.

    A number alone ("33 Dateien warten") cannot be acted on. Named, they can: they were all in
    one folder the day a permission stopped the scan from reading it.
    """
    rows = await session.scalars(
        select(PendingFile).order_by(PendingFile.first_seen_at).limit(limit)
    )
    return list(rows)


async def unreadable_files(session: AsyncSession, *, limit: int = 200) -> list[UnreadableFile]:
    """The files the reading had to walk past, worst first by nothing but age."""
    rows = await session.scalars(
        select(UnreadableFile).order_by(UnreadableFile.relative_path).limit(limit)
    )
    return list(rows)


async def count_unreadable(session: AsyncSession) -> int:
    found = await session.scalar(select(func.count()).select_from(UnreadableFile))
    return int(found or 0)


async def covering_publication(session: AsyncSession, relative_path: str) -> Publication | None:
    """The published folder this path belongs to, if there is one."""
    for publication in await list_publications(session):
        if _covers(publication.relative_path, relative_path):
            return publication
    return None


async def publish(session: AsyncSession, *, relative_path: str, library_base: Path) -> Publication:
    """Publish a folder as an album, with everything below it.

    Publishing a folder that already lies inside a published one is refused - it is there
    already. Publishing a folder above existing ones takes them over: their albums stay exactly
    where they are, the now redundant entries go.
    """
    folder = resolve_inside(library_base, relative_path)
    path = relative_to(library_base, folder)

    existing = await list_publications(session)
    if any(_covers(other.relative_path, path) for other in existing):
        raise AlreadyPublishedError(path)

    for other in existing:
        if _covers(path, other.relative_path):
            await session.delete(other)

    publication = Publication(relative_path=path, enabled=True, device_id=safety.device_of(folder))
    session.add(publication)
    try:
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise AlreadyPublishedError(path) from error

    await session.refresh(publication)
    return publication


async def update_publication(
    session: AsyncSession, *, publication: Publication, enabled: bool | None = None
) -> Publication:
    if enabled is not None:
        publication.enabled = enabled
    await session.commit()
    await session.refresh(publication)
    return publication


async def unpublish(session: AsyncSession, publication: Publication) -> list[uuid.UUID]:
    """Take a folder out of the albums again.

    The albums and media below it are forgotten, and the ways that led to them are cleared up
    when nothing else uses them. The originals on the NAS are untouched, as always.
    """
    albums = await _albums_below(session, publication.relative_path)
    media_ids = list(
        await session.scalars(
            select(Media.id).where(Media.album_id.in_([album.id for album in albums]))
        )
    )

    for album in albums:
        await session.delete(album)
    await session.delete(publication)
    await session.flush()

    await _prune_ways(session)
    await session.commit()
    return media_ids


class NotInsideError(Exception):
    """The folder is not below this published folder, or is the published folder itself."""


async def exclude(
    session: AsyncSession, publication: Publication, relative_path: str
) -> list[uuid.UUID]:
    """Switch a subfolder of a published folder off: it is not read any more, and its albums and
    media leave Muninn. Returns the media that went. The NAS is not touched."""
    path = relative_path.strip("/")
    if path == publication.relative_path or not _covers(publication.relative_path, path):
        raise NotInsideError(path)

    albums = await _albums_below(session, path)
    media_ids = list(
        await session.scalars(
            select(Media.id).where(Media.album_id.in_([album.id for album in albums]))
        )
    )
    for album in albums:
        await session.delete(album)
    # A folder switched off takes the ones already switched off below it along.
    publication.excluded_paths = sorted(
        {other for other in publication.excluded_paths if not _covers(path, other)} | {path}
    )
    await session.flush()
    await _prune_ways(session)
    await session.commit()
    return media_ids


async def include(session: AsyncSession, publication: Publication, relative_path: str) -> None:
    """Switch a subfolder on again. The next read brings its albums back."""
    path = relative_path.strip("/")
    if path not in publication.excluded_paths:
        raise NotInsideError(path)
    publication.excluded_paths = [other for other in publication.excluded_paths if other != path]
    await session.commit()


async def _albums_below(session: AsyncSession, relative_path: str) -> list[Album]:
    query = select(Album)
    if relative_path:
        query = query.where(
            (Album.relative_path == relative_path)
            | Album.relative_path.startswith(f"{relative_path}/")
        )
    return list(await session.scalars(query))


async def _prune_ways(session: AsyncSession) -> None:
    """Remove albums that only led somewhere and now lead nowhere."""
    publications = [publication.relative_path for publication in await list_publications(session)]

    for album in list(await session.scalars(select(Album).where(Album.is_source.is_(False)))):
        leads_somewhere = any(
            _covers(album.relative_path, path) or _covers(path, album.relative_path)
            for path in publications
        )
        if not leads_somewhere:
            await session.delete(album)
    await session.flush()


# --- syncing ------------------------------------------------------------------


async def sync_publication(
    session: AsyncSession,
    publication: Publication,
    *,
    settings: AppSettings,
    library_base: Path,
    trigger: SyncTrigger = SyncTrigger.FULL,
    quick: bool = False,
    scope_path: str | None = None,
    with_children: bool = True,
    now: datetime | None = None,
    confirm_deletions: bool = False,
    on_progress: ProgressCallback | None = None,
    should_stop: StopCheck | None = None,
) -> SyncReport:
    """Bring the albums of a published folder in line with what lies on the NAS.

    A quick sync compares the signature of every folder and reads only the ones that changed. A
    full sync looks at every file. ``scope_path`` narrows the run to one album below the
    publication; that album is then what the sync is responsible for, and only there may it
    decide that something is gone.
    """
    now = now or datetime.now(UTC)
    # Held as a plain id: the row can be deleted under the read, and then the object no longer
    # answers for itself.
    publication_id = publication.id
    base = scope_path if scope_path is not None else publication.relative_path
    folder = library_base / base if base else library_base

    try:
        await asyncio.to_thread(
            safety.check_available, folder, expected_device=publication.device_id
        )
    except safety.RootUnavailableError:
        return await _stop(
            session, publication, now, ScanStatus.UNAVAILABLE, f"{folder} is not reachable."
        )
    except safety.NotMountedError:
        return await _stop(
            session,
            publication,
            now,
            ScanStatus.UNAVAILABLE,
            f"{folder} is not mounted: it sits on a different file system than when it was "
            "published. Mount the share and try again.",
        )

    # Say out loud that this is running: the admin area polls while it is, and stops when the
    # status changes - otherwise a finished sync looks like nothing happened until a reload.
    publication.last_sync_status = ScanStatus.RUNNING
    publication.last_sync_message = None
    await session.commit()

    report = SyncReport()
    await _ensure_way_to(session, publication.relative_path, trigger=trigger, now=now)

    existing_albums = await _load_albums(session)
    signatures = (
        {
            relative_path: album.entry_signature
            for relative_path, album in existing_albums.items()
            if album.entry_signature is not None
        }
        if quick
        else {}
    )

    ignored = list(settings.ignored_names)
    folders = await asyncio.to_thread(
        lambda: list(
            walk(
                library_base,
                ignored_names=ignored,
                known_signatures=signatures,
                base_relative=base,
                with_children=with_children,
                excluded_paths=publication.excluded_paths,
            )
        )
    )

    albums = await _sync_albums(
        session,
        folders,
        existing_albums,
        scope_path=base,
        with_children=with_children,
        trigger=trigger,
        now=now,
        report=report,
    )
    report.albums = len(albums)

    files = await _load_files(session, base)
    pending = await _load_pending(session, base)
    withdrawn = await media_service.withdrawn_paths(session, base)
    by_quick: dict[tuple[int, str], MediaFile] = {
        (file.byte_size, file.quick_hash): file
        for file in files.values()
        if file.quick_hash is not None
    }

    seen: set[str] = set()
    judged_folders: set[str] = set()
    # What this read is about to go through. Folders it skips hold no files to count.
    files_total = sum(len(scanned.files) for scanned in folders)
    files_done = 0

    for scanned in folders:
        album = albums.get(scanned.relative_path)
        if album is None:
            continue

        if should_stop is not None and await should_stop():
            # Stopping between folders keeps what was read: every folder is committed on its
            # own, and the report says what came of it before the stop.
            report.status = ScanStatus.CANCELLED
            report.message = "Stopped by an admin."
            await _finish(session, publication, now, ScanStatus.CANCELLED, report.message)
            return report

        if not await _still_published(session, publication_id):
            # The folder was taken out of the albums while this read was going through it.
            # There is nothing left to write to, so the read ends here and says so.
            report.status = ScanStatus.CANCELLED
            report.message = "The folder is no longer published."
            return report

        if scanned.listing_failed:
            # A folder that could not be listed proves nothing: its files stay as they are.
            report.failed_folders += 1
            seen |= _files_in(files, scanned.relative_path)
            _finish_album(album, now, ScanStatus.UNAVAILABLE, "This folder could not be listed.")
            continue

        if scanned.skipped:
            report.unchanged_folders += 1
            seen |= _files_in(files, scanned.relative_path)
            # Unchanged, but listed - otherwise nobody would know it is unchanged. So the folder
            # is there, and an album still marked unreachable from an earlier outage says so no
            # longer. Only then: writing every album on every quick sync would be a write per
            # folder per minute for nothing.
            if album.last_sync_status is not ScanStatus.OK:
                _finish_album(album, now, ScanStatus.OK)
            continue

        judged_folders.add(scanned.relative_path)
        # A file that was waiting and is no longer in the folder was deleted before it ever
        # settled. Nothing else would ever look at it again - the waiting are only compared
        # against what a listing contains - so the observation would wait for ever, and the
        # engine room would go on counting a file that is not there.
        await _forget_vanished(session, pending, folder=scanned.relative_path, listed=scanned.files)
        ready, waiting = await _split_by_stability(
            session, scanned.files, known=files, pending=pending, settings=settings, now=now
        )
        report.waiting += len(waiting)
        # A file that is still being copied never counts as deleted.
        seen |= waiting

        for group in group_files(ready):
            if group.primary.relative_path in withdrawn:
                # Taken down by an admin. The file is still on the NAS - originals are never
                # written to - so it counts as seen and nothing treats it as gone; it simply
                # never becomes a medium again.
                seen |= {file.relative_path for _, file in group.files}
                continue
            try:
                await _sync_group(
                    session,
                    library_base=library_base,
                    album=album,
                    group=group,
                    known=files,
                    by_quick=by_quick,
                    seen=seen,
                    trigger=trigger,
                    now=now,
                    report=report,
                )
            except WithdrawnError:
                seen |= {file.relative_path for _, file in group.files}
                continue
            except OSError as error:
                # One file nobody may read must not take the whole library's reading down with
                # it. A permission that came with a copy did exactly that: every pass died on
                # the same file, and no other file anywhere was ever confirmed again.
                #
                # It is left exactly as it is - the file counts as seen, so nothing treats it
                # as gone - and the reason is written down where the engine room can show it.
                seen |= {file.relative_path for _, file in group.files}
                report.unreadable.append(Unreadable(str(group.primary.relative_path), str(error)))
                _logger.warning("Skipped %s: %s", group.primary.relative_path, error)
            files_done += len(group.files)

            # Hashing a thousand pictures takes minutes; say so while it happens rather than
            # once the folder is through.
            if on_progress is not None and files_done % PROGRESS_EVERY < len(group.files):
                await session.commit()
                await on_progress(
                    SyncProgress(
                        files_total=files_total,
                        files_done=files_done,
                        current=scanned.relative_path,
                    )
                )

        # The signature is only stored once everything in the folder has arrived; otherwise the
        # next quick sync would skip the folder and never pick the waiting file up.
        album.entry_signature = scanned.signature if not waiting else None
        _finish_album(album, now, ScanStatus.OK)

        # One folder is one unit of work: committing here lets the albums and pictures appear in
        # the app while a long read is still going, instead of all at once at the very end.
        await session.commit()
        # Files that wait for their second look are through as far as this read is concerned.
        files_done += len(waiting)
        if on_progress is not None:
            await on_progress(
                SyncProgress(
                    files_total=files_total,
                    files_done=files_done,
                    current=scanned.relative_path,
                )
            )

    await session.flush()

    vanished = [
        file
        for relative_path, file in files.items()
        if relative_path not in seen and _folder_of(relative_path) in judged_folders
    ]
    in_scope = sum(1 for path_key in files if _folder_of(path_key) in judged_folders)

    suspicious = safety.deletions_are_suspicious(
        missing=len(vanished),
        known=in_scope,
        share_percent=settings.deletion_share_percent,
        count=settings.deletion_count,
    )
    if suspicious and not confirm_deletions:
        # The folders were committed one by one with their new listing, so the next quick sync
        # would take them for unchanged and never judge them again: the pause would be gone
        # without anybody confirming it. Forgetting their signatures makes every sync look again
        # - and stop again - until an admin confirms.
        for parent in {_folder_of(file.relative_path) for file in vanished}:
            album = albums.get(parent)
            if album is not None:
                album.entry_signature = None
        publication.pending_deletions = len(vanished)
        report.missing = len(vanished)
        return await _stop(
            session,
            publication,
            now,
            ScanStatus.PAUSED,
            f"{len(vanished)} of {in_scope} files would be marked as missing. "
            "Check whether the share is mounted, then confirm the sync.",
        )

    report.missing = await _mark_missing(session, vanished, trigger, now)
    report.removed_media = await _purge_expired(session, settings, trigger, now, albums)
    report.removed = len(report.removed_media)
    publication.pending_deletions = 0

    report.pending_metadata = await _media_without_metadata(session, albums)
    report.pending_derivatives = await _media_without_derivatives(session, albums)
    await _note_unreadable(session, publication, report.unreadable, now)
    await _finish(session, publication, now, ScanStatus.OK)
    return report


async def _note_unreadable(
    session: AsyncSession,
    publication: Publication,
    found: Sequence[Unreadable],
    now: datetime,
) -> None:
    """What this reading of the folder had to walk past, in place of what the last one did.

    Replaced rather than added to, and only under this published folder: a permission put right
    is read on the next pass, is not among the findings, and so leaves the engine room by
    itself. Nobody has to remember to clear it.
    """
    under = publication.relative_path
    await session.execute(
        delete(UnreadableFile).where(
            or_(
                UnreadableFile.relative_path == under,
                UnreadableFile.relative_path.startswith(f"{under}/"),
            )
            if under
            else true()
        )
    )
    for one in found:
        session.add(
            UnreadableFile(relative_path=one.relative_path, reason=one.reason[:500], last_at=now)
        )
    await session.flush()


def _files_in(files: dict[str, MediaFile], folder: str) -> set[str]:
    return {path_key for path_key in files if _folder_of(path_key) == folder}


def _folder_of(relative_path: str) -> str:
    """The folder a file lies in, as the album's relative path spells it."""
    return relative_path.rsplit("/", 1)[0] if "/" in relative_path else ""


# --- albums -------------------------------------------------------------------


async def _load_albums(session: AsyncSession) -> dict[str, Album]:
    return {album.relative_path: album for album in await session.scalars(select(Album))}


async def _ensure_way_to(
    session: AsyncSession, relative_path: str, *, trigger: SyncTrigger, now: datetime
) -> None:
    """Create the albums that lead to a published folder.

    They carry no media and are never read; they exist so the album sits where the original
    sits, which is how anybody finds it again.
    """
    if not relative_path:
        return

    parts = relative_path.split("/")
    known = await _load_albums(session)
    parent: Album | None = None

    for depth in range(1, len(parts)):
        path = "/".join(parts[:depth])
        album = known.get(path)
        if album is None:
            album = Album(
                relative_path=path,
                name=parts[depth - 1],
                parent_id=parent.id if parent else None,
                is_source=False,
            )
            session.add(album)
            await session.flush()
            _log(session, now, ChangeKind.ALBUM_ADDED, trigger, album=album)
        parent = album

    await session.commit()


async def _sync_albums(
    session: AsyncSession,
    folders: Sequence[ScannedFolder],
    existing: dict[str, Album],
    *,
    scope_path: str,
    with_children: bool,
    trigger: SyncTrigger,
    now: datetime,
    report: SyncReport,
) -> dict[str, Album]:
    """One album per folder. Folders that are gone lose their album, and with it their media."""
    found: dict[str, Album] = {}
    listed: set[str] = set()

    # walk yields a parent before its children, so the parent always has an id already.
    for folder in folders:
        album = existing.get(folder.relative_path)
        parent = (
            (found.get(folder.parent_path) or existing.get(folder.parent_path or ""))
            if folder.parent_path is not None
            else None
        )

        if album is None:
            album = Album(
                relative_path=folder.relative_path,
                name=folder.name,
                parent_id=parent.id if parent else None,
                is_source=True,
            )
            session.add(album)
            await session.flush()
            _log(session, now, ChangeKind.ALBUM_ADDED, trigger, album=album)
        else:
            album.name = folder.name
            album.parent_id = parent.id if parent else None
            # From here down the folder is read, whatever it was before.
            album.is_source = True

        if not folder.listing_failed:
            listed.add(folder.relative_path)
        found[folder.relative_path] = album

    if with_children:
        for relative_path, album in existing.items():
            if relative_path in found or not _covers(scope_path, relative_path):
                continue
            # Only a folder that was listed can prove that a subfolder of it is gone.
            if _folder_of(relative_path) in listed:
                _log(session, now, ChangeKind.ALBUM_REMOVED, trigger, album=album)
                await session.delete(album)

    await session.flush()
    return found


def _finish_album(
    album: Album, now: datetime, status: ScanStatus, message: str | None = None
) -> None:
    album.last_sync_at = now
    album.last_sync_status = status
    album.last_sync_message = message


# --- files --------------------------------------------------------------------


async def _load_files(session: AsyncSession, scope_path: str) -> dict[str, MediaFile]:
    query = select(MediaFile).options(selectinload(MediaFile.media))
    if scope_path:
        query = query.where(MediaFile.relative_path.startswith(f"{scope_path}/"))
    return {file.relative_path: file for file in await session.scalars(query)}


async def _load_pending(session: AsyncSession, scope_path: str) -> dict[str, PendingFile]:
    query = select(PendingFile)
    if scope_path:
        query = query.where(PendingFile.relative_path.startswith(f"{scope_path}/"))
    return {row.relative_path: row for row in await session.scalars(query)}


async def _split_by_stability(
    session: AsyncSession,
    files: Iterable[ScannedFile],
    *,
    known: dict[str, MediaFile],
    pending: dict[str, PendingFile],
    settings: AppSettings,
    now: datetime,
) -> tuple[list[ScannedFile], set[str]]:
    """Which files are fully copied, and which have to wait for the next listing.

    A file counts as ready when two listings, at least the stability window apart, showed the same
    size and the same modification time. Compared are two observations of the NAS with each other;
    the server clock only measures the distance between the two listings.
    """
    window = timedelta(seconds=settings.stability_seconds)
    ready: list[ScannedFile] = []
    waiting: set[str] = set()

    for file in files:
        row = known.get(file.relative_path)
        unchanged = (
            row is not None
            and row.byte_size == file.byte_size
            and row.modified_at == file.modified_at
        )
        if unchanged:
            # Nothing changed since the last sync, so nothing here can be half written.
            await _forget_observation(session, pending, file.relative_path)
            ready.append(file)
            continue

        observation = pending.get(file.relative_path)
        if observation is None:
            # First sight: remember what the NAS said and wait for the next listing.
            observation = PendingFile(
                relative_path=file.relative_path,
                byte_size=file.byte_size,
                modified_at=file.modified_at,
                first_seen_at=now,
            )
            session.add(observation)
            pending[file.relative_path] = observation
            waiting.add(file.relative_path)
            continue

        if observation.byte_size != file.byte_size or observation.modified_at != file.modified_at:
            # It grew or was written again since the last listing: start the window over.
            observation.byte_size = file.byte_size
            observation.modified_at = file.modified_at
            observation.first_seen_at = now
            waiting.add(file.relative_path)
            continue

        if now - observation.first_seen_at < window:
            waiting.add(file.relative_path)
            continue

        # Two listings, far enough apart, agreed: the file has arrived.
        await _forget_observation(session, pending, file.relative_path)
        ready.append(file)

    return ready, waiting


async def _forget_vanished(
    session: AsyncSession,
    pending: dict[str, PendingFile],
    *,
    folder: str,
    listed: Iterable[ScannedFile],
) -> None:
    """Forget what was waiting in this folder and is not in it any more.

    Only for a folder that was listed, and only for that folder: a listing that failed proves
    nothing, and the safety net turns on exactly this distinction. A file deleted while it was
    still waiting has no medium, nothing derived and nothing to delete - only the note that it
    was once seen.
    """
    there = {file.relative_path for file in listed}
    gone = [path for path in list(pending) if _folder_of(path) == folder and path not in there]
    for path in gone:
        await _forget_observation(session, pending, path)


async def _forget_observation(
    session: AsyncSession, pending: dict[str, PendingFile], relative_path: str
) -> None:
    observation = pending.pop(relative_path, None)
    if observation is not None:
        await session.delete(observation)


async def _sync_group(
    session: AsyncSession,
    *,
    library_base: Path,
    album: Album,
    group: MediaGroup,
    known: dict[str, MediaFile],
    by_quick: dict[tuple[int, str], MediaFile],
    seen: set[str],
    trigger: SyncTrigger,
    now: datetime,
    report: SyncReport,
) -> None:
    """One medium: find it, move it or create it, then bring its files up to date."""
    media = await _resolve_media(
        session,
        library_base=library_base,
        album=album,
        group=group,
        known=known,
        by_quick=by_quick,
        trigger=trigger,
        now=now,
        report=report,
    )

    for role, file in group.files:
        seen.add(file.relative_path)
        row = known.get(file.relative_path)

        if row is None:
            quick = await _quick_hash(library_base, file)
            row = MediaFile(
                media_id=media.id,
                role=role,
                relative_path=file.relative_path,
                filename=file.name,
                content_hash=await _hash(library_base, file),
                quick_hash=quick,
                byte_size=file.byte_size,
                modified_at=file.modified_at,
            )
            session.add(row)
            known[file.relative_path] = row
            by_quick.setdefault((row.byte_size, quick), row)
        else:
            row.media_id = media.id
            row.role = role
            row.filename = file.name
            await _compare_file(
                library_base,
                row,
                file,
                media=media,
                trigger=trigger,
                now=now,
                report=report,
                session=session,
            )

        if role is MediaFileRole.PRIMARY:
            media.content_hash = row.content_hash
            media.quick_hash = row.quick_hash

    media.album_id = album.id
    media.kind = group.kind
    if media.status is MediaStatus.MISSING:
        # Back within the grace period: the derived work is still there, nothing has to be redone.
        media.status = MediaStatus.ACTIVE
        media.missing_since = None
        report.restored += 1
        _log(session, now, ChangeKind.MEDIA_RESTORED, trigger, album=album, media=media)


async def _compare_file(
    library_base: Path,
    row: MediaFile,
    file: ScannedFile,
    *,
    media: Media,
    trigger: SyncTrigger,
    now: datetime,
    report: SyncReport,
    session: AsyncSession,
) -> None:
    """The three stages: the listing, the quick hash, and only then the whole file."""
    if row.byte_size == file.byte_size and row.modified_at == file.modified_at:
        if row.quick_hash is None:
            # Indexed before there was a quick hash. Without one a rename would look like a new
            # file, and the likes and faces of the old one would stay behind.
            row.quick_hash = await _quick_hash(library_base, file)
            media.quick_hash = media.quick_hash or row.quick_hash
        return

    quick = await _quick_hash(library_base, file)
    if row.quick_hash is not None and quick == row.quick_hash:
        # Only touched: a restored backup, a corrected timestamp. Take the new time, leave the
        # medium and everything derived from it alone.
        row.byte_size = file.byte_size
        row.modified_at = file.modified_at
        report.touched += 1
        _log(session, now, ChangeKind.MEDIA_TOUCHED, trigger, media=media, path=row.relative_path)
        return

    content = await _hash(library_base, file)
    row.byte_size = file.byte_size
    row.modified_at = file.modified_at
    row.quick_hash = quick

    if content == row.content_hash:
        report.touched += 1
        return

    row.content_hash = content
    # The file was edited, so everything derived from it is stale. Stage 3 decides from the
    # pixel hash how much really has to be done again.
    media.metadata_version = 0
    media.derive_version = 0
    report.changed += 1
    _log(session, now, ChangeKind.MEDIA_CHANGED, trigger, media=media, path=row.relative_path)


class WithdrawnError(Exception):
    """This picture was taken down. It does not become a medium again, whatever it is called."""


async def _resolve_media(
    session: AsyncSession,
    *,
    library_base: Path,
    album: Album,
    group: MediaGroup,
    known: dict[str, MediaFile],
    by_quick: dict[tuple[int, str], MediaFile],
    trigger: SyncTrigger,
    now: datetime,
    report: SyncReport,
) -> Media:
    """The medium behind this group: the known one, the moved one, or a new one."""
    at_path = known.get(group.primary.relative_path)
    if at_path is not None:
        return at_path.media

    # A file under an unknown path is compared by size and quick hash with the ones that are
    # gone, and only read completely when that matches. A renamed folder with 3.000 photos is
    # not worth 3.000 full reads.
    quick = await _quick_hash(library_base, group.primary)
    candidate = by_quick.get((group.primary.byte_size, quick))

    if candidate is not None and not await asyncio.to_thread(
        (library_base / candidate.relative_path).exists
    ):
        content = await _hash(library_base, group.primary)
        if content == candidate.content_hash:
            report.moved += 1
            known.pop(candidate.relative_path, None)
            _log(
                session,
                now,
                ChangeKind.MEDIA_MOVED,
                trigger,
                album=album,
                media=candidate.media,
                path=group.primary.relative_path,
            )
            candidate.relative_path = group.primary.relative_path
            candidate.filename = group.primary.name
            known[candidate.relative_path] = candidate
            return candidate.media

    content_hash = await _hash(library_base, group.primary)
    if await media_service.is_withdrawn(session, content_hash=content_hash):
        # The same picture an admin took down, under another name or in another folder. A
        # medium is what its content is, so it stays down.
        raise WithdrawnError

    media = Media(
        album_id=album.id,
        kind=group.kind,
        status=MediaStatus.ACTIVE,
        content_hash=content_hash,
        quick_hash=quick,
        metadata_version=0,
        derive_version=0,
    )
    session.add(media)
    await session.flush()
    report.added += 1
    report.added_by_album[str(album.id)] = report.added_by_album.get(str(album.id), 0) + 1
    _log(
        session,
        now,
        ChangeKind.MEDIA_ADDED,
        trigger,
        album=album,
        media=media,
        path=group.primary.relative_path,
    )
    return media


async def _hash(library_base: Path, file: ScannedFile) -> str:
    """BLAKE3 reads the whole file, so it belongs in a thread of its own."""
    return await asyncio.to_thread(hash_file, library_base / file.relative_path)


async def _quick_hash(library_base: Path, file: ScannedFile) -> str:
    return await asyncio.to_thread(
        quick_hash_file, library_base / file.relative_path, file.byte_size
    )


# --- disappearing files -------------------------------------------------------


async def _mark_missing(
    session: AsyncSession, vanished: list[MediaFile], trigger: SyncTrigger, now: datetime
) -> int:
    """A file that is gone takes its medium out of sight; a lost RAW only loses its own row."""
    missing = 0
    for file in vanished:
        if file.role is MediaFileRole.PRIMARY:
            media = file.media
            if media.status is not MediaStatus.MISSING:
                media.status = MediaStatus.MISSING
                media.missing_since = now
                missing += 1
                _log(
                    session,
                    now,
                    ChangeKind.MEDIA_MISSING,
                    trigger,
                    media=media,
                    path=file.relative_path,
                )
        else:
            await session.delete(file)
    await session.flush()
    return missing


async def _purge_expired(
    session: AsyncSession,
    settings: AppSettings,
    trigger: SyncTrigger,
    now: datetime,
    albums: dict[str, Album],
) -> list[uuid.UUID]:
    """Media whose grace period ran out are removed for good, with everything derived from them."""
    cutoff = now - timedelta(days=settings.missing_grace_days)
    query = select(Media).where(
        Media.status == MediaStatus.MISSING,
        Media.missing_since.is_not(None),
        Media.missing_since <= cutoff,
        Media.album_id.in_([album.id for album in albums.values()]),
    )

    expired = list(await session.scalars(query))
    removed = []
    for media in expired:
        # The line outlives the row it describes, so it carries the path rather than the id.
        path = media.files[0].relative_path if media.files else None
        _log(session, now, ChangeKind.MEDIA_REMOVED, trigger, path=path)
        removed.append(media.id)
        await session.delete(media)
    await session.flush()
    return removed


async def _media_without_derivatives(
    session: AsyncSession, albums: dict[str, Album]
) -> list[uuid.UUID]:
    query = select(Media.id).where(
        Media.status == MediaStatus.ACTIVE,
        Media.derive_version < DERIVE_VERSION,
        Media.album_id.in_([album.id for album in albums.values()]),
        attempts.still_open("derive", Media.id),
    )
    return list(await session.scalars(query))


async def _media_without_metadata(
    session: AsyncSession, albums: dict[str, Album]
) -> list[uuid.UUID]:
    query = select(Media.id).where(
        Media.status == MediaStatus.ACTIVE,
        Media.metadata_version < METADATA_VERSION,
        Media.album_id.in_([album.id for album in albums.values()]),
    )
    return list(await session.scalars(query))


# --- bookkeeping --------------------------------------------------------------


def _log(
    session: AsyncSession,
    now: datetime,
    kind: ChangeKind,
    trigger: SyncTrigger,
    *,
    album: Album | None = None,
    media: Media | None = None,
    path: str | None = None,
) -> None:
    """One line per finding. The log explains later what happened during the night."""
    session.add(
        ChangeLogEntry(
            occurred_at=now,
            album_id=album.id if album else (media.album_id if media else None),
            media_id=media.id if media else None,
            kind=kind,
            trigger=trigger,
            path=path or (album.relative_path if album else None),
        )
    )


async def recent_changes(
    session: AsyncSession, *, limit: int = 100, album_id: uuid.UUID | None = None
) -> list[ChangeLogEntry]:
    """The newest lines of the log, for the admin area and for an album's own history."""
    query = select(ChangeLogEntry).order_by(ChangeLogEntry.occurred_at.desc()).limit(limit)
    if album_id is not None:
        query = query.where(ChangeLogEntry.album_id == album_id)
    return list(await session.scalars(query))


async def prune_change_log(session: AsyncSession, *, now: datetime | None = None) -> int:
    """The log is kept for 90 days."""
    now = now or datetime.now(UTC)
    cutoff = now - timedelta(days=RETENTION_DAYS)

    expired = await session.scalar(
        select(func.count()).select_from(ChangeLogEntry).where(ChangeLogEntry.occurred_at < cutoff)
    )
    await session.execute(delete(ChangeLogEntry).where(ChangeLogEntry.occurred_at < cutoff))
    await session.commit()
    return int(expired or 0)


async def _stop(
    session: AsyncSession,
    publication: Publication,
    now: datetime,
    status: ScanStatus,
    message: str,
) -> SyncReport:
    await _finish(session, publication, now, status, message)
    return SyncReport(status=status, message=message)


async def _still_published(session: AsyncSession, publication_id: uuid.UUID) -> bool:
    """Whether the folder is still one of the published ones.

    An admin may take it out of the albums while a read is running, and a read that writes to a
    row nobody kept only produces an error where a clean stop belongs.
    """
    found = await session.scalar(select(Publication.id).where(Publication.id == publication_id))
    return found is not None


async def _finish(
    session: AsyncSession,
    publication: Publication,
    now: datetime,
    status: ScanStatus,
    message: str | None = None,
) -> None:
    if not await _still_published(session, publication.id):
        # Unpublished mid-read: the result has nowhere to go, and that is not an error.
        await session.rollback()
        return

    publication.last_sync_at = now
    publication.last_sync_status = status
    publication.last_sync_message = message
    await session.commit()


# --- metadata -----------------------------------------------------------------


async def apply_metadata(session: AsyncSession, media_id: uuid.UUID, *, library_base: Path) -> bool:
    """Stage 2 for one medium. Idempotent, and it stores the version it ran with."""
    media = await session.get(Media, media_id)
    if media is None or media.status is not MediaStatus.ACTIVE:
        return False

    primary = media.primary_file
    path = library_base / primary.relative_path
    if not await asyncio.to_thread(path.exists):
        return False

    # exiftool and ffprobe are separate programs; waiting for them does not block the loop.
    read = await asyncio.to_thread(
        read_metadata,
        path,
        kind=media.kind,
        relative_path=primary.relative_path,
        modified_at=primary.modified_at,
    )

    media.taken_at = read.taken_at
    media.taken_at_source = read.taken_at_source
    media.width = read.width
    media.height = read.height
    media.duration_seconds = read.duration_seconds
    media.camera_make = read.camera_make
    media.camera_model = read.camera_model
    media.lens = read.lens
    media.latitude = read.latitude
    media.longitude = read.longitude
    media.metadata_version = METADATA_VERSION

    await session.commit()
    return True


@dataclass(frozen=True, slots=True)
class IndexCounts:
    albums: int
    media: int
    #: Of those media, how many are pictures and how many are films.
    photos: int
    videos: int
    missing: int
    pending_metadata: int
    pending_derivatives: int


async def index_counts(session: AsyncSession) -> IndexCounts:
    """The numbers the admin area shows about indexing."""
    albums = await session.scalar(
        select(func.count()).select_from(Album).where(Album.is_source.is_(True))
    )
    # The same media the albums, the timeline and the Überblick count: a copy of another file
    # is not a second picture in the library, and the engine room saying it is left the two
    # screens disagreeing by exactly the number of duplicates.
    kinds = (
        await session.execute(select(Media.kind, func.count()).where(shown()).group_by(Media.kind))
    ).all()
    by_kind = {kind: int(count) for kind, count in kinds}
    media = sum(by_kind.values())
    missing = await session.scalar(
        select(func.count()).select_from(Media).where(Media.status == MediaStatus.MISSING)
    )
    pending = await session.scalar(
        select(func.count())
        .select_from(Media)
        .where(Media.status == MediaStatus.ACTIVE, Media.metadata_version < METADATA_VERSION)
    )
    undrawn = await session.scalar(
        select(func.count())
        .select_from(Media)
        .where(Media.status == MediaStatus.ACTIVE, Media.derive_version < DERIVE_VERSION)
    )
    return IndexCounts(
        albums=int(albums or 0),
        media=media,
        photos=by_kind.get(MediaKind.IMAGE, 0),
        videos=by_kind.get(MediaKind.VIDEO, 0),
        missing=int(missing or 0),
        pending_metadata=int(pending or 0),
        pending_derivatives=int(undrawn or 0),
    )
