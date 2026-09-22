"""Hashing a file: the identity of a medium, and how a change or a move is recognised."""

import os
from pathlib import Path

from blake3 import blake3

#: Read in chunks so a 40 GB video does not have to fit into memory.
CHUNK_SIZE = 1024 * 1024


def hash_file(path: Path) -> str:
    digest = blake3()
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK_SIZE):
            digest.update(chunk)
    return str(digest.hexdigest())


#: How much of a file the quick hash reads at each end.
QUICK_HASH_BYTES = 1024 * 1024


def quick_hash_file(path: Path, byte_size: int) -> str:
    """A hash over the first and last mebibyte plus the size.

    Two short reads instead of a full one: enough to tell an edited file from one that was merely
    touched, and enough to find a moved file before reading it completely. Reading a 4 GB video
    over a gigabit line costs half a minute; this costs nothing worth measuring.
    """
    digest = blake3()
    digest.update(f"{byte_size}\n".encode())

    with path.open("rb") as handle:
        digest.update(handle.read(QUICK_HASH_BYTES))
        if byte_size > QUICK_HASH_BYTES * 2:
            handle.seek(-QUICK_HASH_BYTES, os.SEEK_END)
            digest.update(handle.read(QUICK_HASH_BYTES))

    return str(digest.hexdigest())
