"""Listing a folder on the NAS.

Pure file system work: no database, no decisions about media. One listing answers everything the
reconciliation needs - which media files lie here, how large they are, when they changed, and a
signature over all of that.
"""

import os
from collections.abc import Collection, Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from blake3 import blake3

from muninn.library.formats import kind_of


@dataclass(frozen=True, slots=True)
class ScannedFile:
    #: Path below the root, with forward slashes.
    relative_path: str
    name: str
    byte_size: int
    modified_at: datetime


@dataclass(frozen=True, slots=True)
class ScannedFolder:
    """One folder of the root, which will become one album."""

    relative_path: str
    name: str
    parent_path: str | None
    files: tuple[ScannedFile, ...]
    #: Hash over the sorted listing of media files; None when the folder could not be read.
    signature: str | None = None
    #: True when the signature matched the stored one, so the files were not looked at.
    skipped: bool = False
    #: True when the listing could not be read. Such a folder proves nothing - above all not
    #: that something is gone.
    listing_failed: bool = False

    @property
    def was_read(self) -> bool:
        """Whether this listing is complete, and may therefore be judged on."""
        return not self.skipped and not self.listing_failed


def signature_of(files: Collection[ScannedFile]) -> str:
    """A fingerprint of the listing: how many files, and which names, sizes and times.

    The folder's own modification time is deliberately not part of it. Some NAS systems do not
    update it when a file is renamed, and older shares round times to two seconds - the listing
    itself is the more honest answer, and it costs the same single round trip.
    """
    digest = blake3()
    digest.update(f"{len(files)}\n".encode())
    for file in sorted(files, key=lambda item: item.name):
        line = f"{file.name}\x1f{file.byte_size}\x1f{file.modified_at.timestamp()}\n"
        digest.update(line.encode())
    return str(digest.hexdigest())


def is_ignored(name: str, ignored_names: Collection[str]) -> bool:
    """Hidden entries are always skipped; the rest comes from the admin settings."""
    if name.startswith("."):
        return True
    folded = name.casefold()
    return any(folded == ignored.casefold() for ignored in ignored_names)


def walk(
    root: Path,
    *,
    ignored_names: Collection[str] = (),
    known_signatures: Mapping[str, str] | None = None,
    base_relative: str = "",
    with_children: bool = True,
    excluded_paths: Collection[str] = (),
) -> Iterator[ScannedFolder]:
    """Every folder below the root, the root itself first.

    Folders without media are returned too: they become collections in the album tree.

    ``known_signatures`` maps a folder to the signature of its last complete listing. A folder
    whose signature still matches is reported as skipped and its files are not looked at - that
    is the quick sync. Subfolders are visited all the same, because a change deeper down does
    not show in the signature above.

    ``base_relative`` starts the walk inside the root, for syncing a single album.
    ``excluded_paths`` are folders an admin switched off: they and everything below are left out.
    """
    yield from _walk_folder(
        root,
        base_relative,
        _parent_of(base_relative),
        ignored_names,
        known_signatures or {},
        with_children,
        frozenset(excluded_paths),
    )


def _walk_folder(
    root: Path,
    relative_path: str,
    parent_path: str | None,
    ignored_names: Collection[str],
    known_signatures: Mapping[str, str],
    with_children: bool,
    excluded: frozenset[str] = frozenset(),
) -> Iterator[ScannedFolder]:
    folder = root / relative_path if relative_path else root
    name = folder.name if relative_path else root.name

    entries = _entries(folder)
    if entries is None:
        yield _unreadable(relative_path, name, parent_path)
        return

    files: list[ScannedFile] = []
    subfolders: list[str] = []

    for entry in entries:
        if is_ignored(entry.name, ignored_names):
            continue

        child_path = f"{relative_path}/{entry.name}" if relative_path else entry.name

        # Symbolic links are not followed: a link back up the tree would walk forever, and a
        # link to a file would index the same original twice.
        if entry.is_symlink():
            continue

        if entry.is_dir(follow_symlinks=False):
            if child_path not in excluded:
                subfolders.append(child_path)
            continue

        if kind_of(entry.name) is None:
            continue

        try:
            stat = entry.stat(follow_symlinks=False)
        except OSError:
            # One unreadable entry makes the listing incomplete, and an incomplete listing may
            # never lead to a deletion.
            yield _unreadable(relative_path, name, parent_path)
            return

        # An empty file is never a picture. Copy tools create the entry first and fill it
        # afterwards, so this is what a copy that has only just started looks like.
        if stat.st_size == 0:
            continue

        files.append(
            ScannedFile(
                relative_path=child_path,
                name=entry.name,
                byte_size=stat.st_size,
                modified_at=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
            )
        )

    signature = signature_of(files)
    skipped = known_signatures.get(relative_path) == signature

    yield ScannedFolder(
        relative_path=relative_path,
        name=name,
        parent_path=parent_path,
        files=() if skipped else tuple(sorted(files, key=lambda file: file.relative_path)),
        signature=signature,
        skipped=skipped,
    )

    if not with_children:
        return

    for child_relative in sorted(subfolders):
        yield from _walk_folder(
            root,
            child_relative,
            relative_path,
            ignored_names,
            known_signatures,
            with_children,
            excluded,
        )


def _unreadable(relative_path: str, name: str, parent_path: str | None) -> ScannedFolder:
    return ScannedFolder(
        relative_path=relative_path,
        name=name,
        parent_path=parent_path,
        files=(),
        listing_failed=True,
    )


def _entries(folder: Path) -> list[os.DirEntry[str]] | None:
    """Read a folder, or None when it cannot be listed - never proof of an empty folder."""
    try:
        with os.scandir(folder) as scan:
            return sorted(scan, key=lambda entry: entry.name)
    except OSError:
        return None


def _parent_of(relative_path: str) -> str | None:
    if not relative_path:
        return None
    return relative_path.rsplit("/", 1)[0] if "/" in relative_path else ""
