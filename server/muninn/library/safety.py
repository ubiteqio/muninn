"""The safety net around every sync.

Two things must never happen: Muninn indexing a folder that is not the library, and Muninn
declaring half the library gone because a share dropped out. Both are checked here.

The question both checks answer is the same: is this really the folder that was set up, and is it
really there? A share that is not mounted looks exactly like an empty folder - so Muninn asks the
file system which device the folder sits on and compares that with the device it was set up on.
A marker file does the same job for setups where the device legitimately changes.
"""

from pathlib import Path

#: May lie in a library root as an alternative proof: useful where the device id changes, for
#: instance when the share is remounted by something that gives it a new device each time.
MARKER_NAME = ".muninn-root"


class RootUnavailableError(Exception):
    """The folder is not there, or not a folder at all."""


class NotMountedError(Exception):
    """The folder sits on a different file system than when it was set up.

    That is what an unmounted share looks like from the inside: the mount point is an ordinary,
    usually empty folder on the container's own disk.
    """


def device_of(path: Path) -> int | None:
    """Which file system the folder lies on, or None if it cannot be read."""
    try:
        return path.stat().st_dev
    except OSError:
        return None


def check_available(path: Path, *, expected_device: int | None = None) -> None:
    """Refuse to sync anything that is not the folder Muninn was pointed at.

    Everything here can fail on a share that is gone or not readable, and a failure is never
    proof of anything: it is reported, not interpreted.
    """
    try:
        if not path.is_dir():
            raise RootUnavailableError(str(path))
        has_marker = (path / MARKER_NAME).exists()
    except OSError as error:
        raise RootUnavailableError(str(path)) from error

    if has_marker:
        return

    if expected_device is not None and device_of(path) != expected_device:
        raise NotMountedError(str(path))


def deletions_are_suspicious(*, missing: int, known: int, share_percent: int, count: int) -> bool:
    """True when this many disappeared files look like an accident rather than a deletion.

    ``known`` counts only what this sync was responsible for: the files in the folders it read
    completely. A folder it could not list is never part of the reckoning.

    Either rule is off at 0, and both are by default: a file deleted on the NAS disappears from
    the albums with the next read. What an outage looks like is caught before this - a share that
    is not mounted sits on another device, a folder that cannot be listed deletes nothing - and
    a missing file comes back by itself within the grace period.
    """
    if missing == 0:
        return False
    if count > 0 and missing >= count:
        return True
    return share_percent > 0 and known > 0 and missing / known > share_percent / 100
