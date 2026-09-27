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

#: How long a gap makes the next picture a new moment.
GAP_MINUTES = 45

#: About how many pictures one moment contributes. A page with a single picture on it is a fine
#: page; a book of nothing but those is a slideshow. Spending the pictures on fewer moments is
#: what gives a book its strips, its contact sheets and its map pages.
PER_MOMENT = 3


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
        start, until = stretch_of(len(shots), step, wanted)
        stretch = list(shots[start:until])
        if step == 0:
            taken.append(stretch[0])
        elif step == wanted - 1:
            taken.append(stretch[-1])
        else:
            best = max(stretch, key=lambda shot: (worth(shot), shot.id))
            taken.append(best if dice.random() < 0.6 else dice.choice(stretch))
    return taken


def like(one: Shot, other: Shot) -> float:
    """How much two pictures are about the same thing, by the words the analyzer used."""
    mine = {*one.tags, one.scene} - {""}
    theirs = {*other.tags, other.scene} - {""}
    return len(mine & theirs) / len(mine | theirs) if mine and theirs else 0.0


def placed(media: Sequence[Shot]) -> list[Shot]:
    """Pictures dated only by their folder name, put where they belong by what is in them.

    "Urlaub 2024 - Estland" gives a year and nothing more, so such a picture carries the 1st of
    January and would open the book on a day that never happened. It belongs to the afternoon
    whose pictures look most like it, and it shows no time of its own, because none was recorded.
    """
    dated = [one for one in media if not one.guessed]
    guessed = [one for one in media if one.guessed]
    if not dated or not guessed:
        return sorted(media, key=lambda one: (one.taken_at, one.id))

    runs = runs_of(dated)
    settled = list(dated)
    for one in guessed:
        home = max(runs, key=lambda run: max(like(one, other) for other in run))
        settled.append(replace(one, taken_at=home[-1].taken_at))
    return sorted(settled, key=lambda one: (one.taken_at, one.id))


def runs_of(media: Sequence[Shot], gap_minutes: int = GAP_MINUTES) -> list[list[Shot]]:
    """The pictures grouped into moments: everything taken within three quarters of an hour."""
    runs: list[list[Shot]] = []
    for one in media:
        last = runs[-1][-1] if runs else None
        if last and (one.taken_at - last.taken_at).total_seconds() <= gap_minutes * 60:
            runs[-1].append(one)
        else:
            runs.append([one])
    return runs


def stretch_of(count: int, step: int, of: int) -> tuple[int, int]:
    """Where the ``step``-th of ``of`` equal stretches of ``count`` things begins and ends."""
    start = round(step * count / of)
    return start, max(round((step + 1) * count / of), start + 1)


def some_runs(runs: Sequence[list[Shot]], wanted: int, dice: random.Random) -> list[list[Shot]]:
    """``wanted`` moments taken from all of them: the fullest of each stretch, or a neighbour.

    The first and the last moment are always among them, and which of the others are taken
    depends on the seed - that is what makes the second book of an album a different book, even
    where every moment holds a single picture.
    """
    if wanted >= len(runs):
        return list(runs)
    taken: list[list[Shot]] = []
    for step in range(wanted):
        start, until = stretch_of(len(runs), step, wanted)
        here = list(runs[start:until])
        if step == 0:
            taken.append(here[0])
        elif step == wanted - 1:
            taken.append(here[-1])
        else:
            fullest = max(here, key=len)
            taken.append(fullest if dice.random() < 0.6 else dice.choice(here))
    return taken


def how_many_moments(runs: Sequence[Sequence[Shot]], wanted: int) -> int:
    """How many moments ``wanted`` pictures should be spent on.

    Three pictures a moment make a book worth turning, but only where the moments are that
    large: an album of single shots taken hours apart has nothing to gather, and asking for a
    third of the moments would leave a third of the book. So the wish bends to what is there.
    """
    if not runs:
        return 1
    typical = max(1, min(PER_MOMENT, round(sum(len(run) for run in runs) / len(runs))))
    return max(1, min(-(-wanted // typical), len(runs)))


def shares(runs: Sequence[Sequence[Shot]], wanted: int) -> list[int]:
    """How many pictures each moment contributes: its share of the book, but never none."""
    total = sum(len(run) for run in runs) or 1
    given = [max(1, int(len(run) * wanted / total)) for run in runs]
    # What the rounding left over goes to the moments with the most still to give.
    while sum(given) < wanted and any(one < len(run) for one, run in zip(given, runs, strict=True)):
        at = max(range(len(runs)), key=lambda one: len(runs[one]) - given[one])
        given[at] += 1
    while sum(given) > wanted and any(one > 1 for one in given):
        at = max(range(len(runs)), key=lambda one: given[one])
        given[at] -= 1
    return given


def moments(kept: Sequence[Shot], wanted: int, seed: int = 0) -> list[Shot]:
    """Whole moments, spread across the album, rather than every nth picture.

    Taking every nth picture reaches from the first to the last just as well, and makes a poor
    book: the runs that become a strip, a contact sheet or a map page are cut to a single shot
    each, and what is left is thirty pages of one picture. So the moments are chosen first, and
    each keeps its share of pictures.
    """
    dice = random.Random(seed)  # noqa: S311 - a book, not a secret
    all_runs = runs_of(kept)
    runs = some_runs(all_runs, how_many_moments(all_runs, wanted), dice)
    picked: list[Shot] = []
    for run, share in zip(runs, shares(runs, wanted), strict=True):
        picked.extend(spread(run, share, seed))

    # A book begins where the album begins and ends where it ends, whatever the shares did.
    if picked and picked[0] is not kept[0]:
        picked[0] = kept[0]
    if picked and picked[-1] is not kept[-1]:
        picked[-1] = kept[-1]
    return picked


def chosen(shots: Sequence[Shot], *, size: str, ceiling: int, seed: int = 0) -> list[Shot]:
    """The pictures of a book, in order: thinned first, then the moments across the album."""
    kept = thinned(placed(shots))
    wanted = how_many(len(kept), size, ceiling)
    picked = list(kept) if wanted >= len(kept) else moments(kept, wanted, seed)
    return [replace(shot, draw=_drawn(shot.id, seed)) for shot in picked]


def _drawn(media_id: str, seed: int) -> float:
    """A number between 0 and 1 that is always the same for this picture in this book."""
    mark = hashlib.md5(f"{media_id}:{seed}".encode(), usedforsecurity=False).hexdigest()[:8]
    return int(mark, 16) / 0xFFFFFFFF
