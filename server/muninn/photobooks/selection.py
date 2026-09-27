"""Which pictures go into a book, out of everything an album holds.

Two rules, in this order. First, of several shots of one thing only the best is printed: a burst
of eighteen at the water's edge is one picture in a book and eighteen in a folder. Second, what
is left is drawn evenly across the whole album, so a book of a folder with 4500 pictures still
begins where the folder begins and ends where it ends, rather than stopping after the first
hundred and fifty.
"""

import hashlib
import random
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime

from muninn.models.photobook import SHARE_OF_ALBUM, SIZE_MEDIUM

#: Below this many differing bits of the perceptual hash, two pictures show the same thing. The
#: duplicate finder calls six bits "near"; a book is pickier, because two almost equal pages are
#: worse than a page that is missing.
ALIKE_BITS = 12

#: No book is worth making below this, and none needs to be cut below it either.
FEWEST = 8


@dataclass(frozen=True, slots=True)
class Shot:
    """One medium, with everything the book may say about it and nothing more."""

    id: str
    taken_at: datetime
    #: True when the date comes from the folder name rather than from the picture. Such a shot
    #: has a year at best, so it is placed by what is in it and never shows a time.
    guessed: bool
    kind: str
    width: int
    height: int
    has_preview: bool
    latitude: float | None = None
    longitude: float | None = None
    place: str = ""
    region: str = ""
    country: str = ""
    population: int | None = None
    caption: str = ""
    scene: str = ""
    ocr: str = ""
    people: int = 0
    tags: tuple[str, ...] = ()
    #: Faces somebody confirmed, and faces the detector only suspects.
    persons: tuple[str, ...] = ()
    suggested: tuple[str, ...] = ()
    fingerprint: int | None = None
    #: Set while the book is built, for the pages that need a stable random order.
    draw: float = field(default=0.0, compare=False)


def apart(one: Shot, other: Shot) -> int:
    """How far two pictures are from each other, as the duplicate finder measures it.

    The library already stores a 64-bit perceptual hash per medium, so telling two shots of the
    same thing apart costs no model and no new column: it is the number of differing bits.
    """
    if one.fingerprint is None or other.fingerprint is None:
        return 64
    return ((int(one.fingerprint) ^ int(other.fingerprint)) & (2**64 - 1)).bit_count()


def worth(one: Shot) -> tuple[int, int, int]:
    """Which of two shots of the same thing is the one to print."""
    return one.people, len(one.caption), one.width * one.height


def thinned(shots: Sequence[Shot], bits: int = ALIKE_BITS) -> list[Shot]:
    """The pictures worth printing: of several shots of one thing, the best.

    Compared only against what is already kept, so a long burst collapses to the few shots that
    genuinely differ, and the order of the album is restored afterwards.
    """
    kept: list[Shot] = []
    for one in sorted(shots, key=lambda shot: (worth(shot), shot.id), reverse=True):
        if all(apart(one, other) > bits for other in kept):
            kept.append(one)
    return sorted(kept, key=lambda shot: (shot.taken_at, shot.id))


def how_many(album_size: int, size: str, ceiling: int) -> int:
    """How many pictures a book of this size holds: a share of the album, under the ceiling."""
    share = SHARE_OF_ALBUM.get(size, SHARE_OF_ALBUM[SIZE_MEDIUM])
    wanted = round(album_size * share)
    return max(min(wanted, ceiling, album_size), min(FEWEST, album_size))


def spread(shots: Sequence[Shot], wanted: int, seed: int = 0) -> list[Shot]:
    """``wanted`` pictures taken evenly from first to last.

    The album is cut into as many stretches as there are pictures to take, and one is taken out
    of each - the most promising of them, unless the seed says otherwise, which is what makes a
    second book of the same album a different book. The first and the last picture are always in
    it: a book that starts in the middle of a holiday reads like a mistake.
    """
    if wanted >= len(shots):
        return list(shots)
    if wanted <= 0:
        return []

    dice = random.Random(seed)  # noqa: S311 - a book, not a secret
    taken: list[Shot] = []
    for step in range(wanted):
        start = round(step * len(shots) / wanted)
        until = max(round((step + 1) * len(shots) / wanted), start + 1)
        stretch = list(shots[start:until])
        if step == 0:
            taken.append(stretch[0])
        elif step == wanted - 1:
            taken.append(stretch[-1])
        else:
            best = max(stretch, key=lambda shot: (worth(shot), shot.id))
            taken.append(best if dice.random() < 0.6 else dice.choice(stretch))
    return taken


def chosen(shots: Sequence[Shot], *, size: str, ceiling: int, seed: int = 0) -> list[Shot]:
    """The pictures of a book, in order: thinned first, then spread over the whole album."""
    kept = thinned(shots)
    picked = spread(kept, how_many(len(kept), size, ceiling), seed)
    return [replace(shot, draw=_drawn(shot.id, seed)) for shot in picked]


def _drawn(media_id: str, seed: int) -> float:
    """A number between 0 and 1 that is always the same for this picture in this book."""
    mark = hashlib.md5(f"{media_id}:{seed}".encode(), usedforsecurity=False).hexdigest()[:8]
    return int(mark, 16) / 0xFFFFFFFF
