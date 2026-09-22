"""What a search asks for, taken apart by a few plain rules.

The concept has the describing model split "Oma und Lena am Strand in Italien 2012" into people,
places, a period and the rest. People come with a later milestone; until then only what can be
recognised for certain is taken out - years, seasons, months, whether photos or videos are
meant, and (in the engine, from the places the library has photos from) places - and
everything else is what is searched for.
"""

import re
from dataclasses import dataclass
from datetime import date

from muninn.models.media import MediaKind

MONTHS = {
    "januar": 1, "jan": 1, "februar": 2, "feb": 2, "märz": 3, "maerz": 3, "april": 4, "apr": 4,
    "mai": 5, "juni": 6, "jun": 6, "juli": 7, "jul": 7, "august": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9, "oktober": 10, "okt": 10, "november": 11, "nov": 11,
    "dezember": 12, "dez": 12,
}  # fmt: skip

#: A season is a span of months; winter reaches into the next year.
SEASONS = {
    "frühling": (3, 5),
    "fruehling": (3, 5),
    "frühjahr": (3, 5),
    "sommer": (6, 8),
    "herbst": (9, 11),
    "winter": (12, 14),
}

KINDS = {
    "video": MediaKind.VIDEO,
    "videos": MediaKind.VIDEO,
    "film": MediaKind.VIDEO,
    "filme": MediaKind.VIDEO,
    "foto": MediaKind.IMAGE,
    "fotos": MediaKind.IMAGE,
    "bild": MediaKind.IMAGE,
    "bilder": MediaKind.IMAGE,
}

_YEAR = r"(19[5-9]\d|20\d\d)"
_RANGE = re.compile(rf"\b{_YEAR}\s*(?:-|\u2013|bis)\s*{_YEAR}\b", re.IGNORECASE)
_NAMED = re.compile(
    rf"\b(?:im\s+|in\s+)?({'|'.join(sorted(MONTHS | SEASONS, key=len, reverse=True))})\s+{_YEAR}\b",
    re.IGNORECASE,
)
_SINGLE = re.compile(rf"\b(?:aus\s+|von\s+|im\s+jahr\s+|in\s+)?{_YEAR}\b", re.IGNORECASE)
_KIND = re.compile(rf"\b(?:nur\s+)?({'|'.join(KINDS)})\b", re.IGNORECASE)
_FILLER = re.compile(r"\b(?:aus|von|im|in|am|nur|mit)\s*$", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class ParsedQuery:
    #: What is left to search for; empty when the query was only a period or a kind.
    text: str
    #: The first day that counts, and the first that no longer does.
    date_from: date | None = None
    date_until: date | None = None
    #: The places named in it, as typed ("Toskana"). Found by muninn.places, not by the rules
    #: here, because which words are places depends on where the library has photos from.
    places: tuple[str, ...] = ()
    #: The persons named in it, as typed ("Oma", "Lena"): found by muninn.faces.
    persons: tuple[str, ...] = ()
    kind: MediaKind | None = None


def _span(year: int, first_month: int, last_month: int) -> tuple[date, date]:
    """From the first of the first month to the first day after the last one."""
    start = date(year + (first_month - 1) // 12, (first_month - 1) % 12 + 1, 1)
    after = last_month + 1
    end = date(year + (after - 1) // 12, (after - 1) % 12 + 1, 1)
    return start, end


def parse(query: str) -> ParsedQuery:
    text = " ".join(query.split())
    date_from: date | None = None
    date_until: date | None = None
    kind: MediaKind | None = None

    if match := _RANGE.search(text):
        first, last = sorted((int(match.group(1)), int(match.group(2))))
        date_from, date_until = date(first, 1, 1), date(last + 1, 1, 1)
        text = text[: match.start()] + text[match.end() :]
    elif match := _NAMED.search(text):
        word, year = match.group(1).lower(), int(match.group(2))
        if word in MONTHS:
            date_from, date_until = _span(year, MONTHS[word], MONTHS[word])
        else:
            date_from, date_until = _span(year, *SEASONS[word])
        text = text[: match.start()] + text[match.end() :]
    elif match := _SINGLE.search(text):
        year = int(match.group(1))
        date_from, date_until = date(year, 1, 1), date(year + 1, 1, 1)
        text = text[: match.start()] + text[match.end() :]

    if match := _KIND.search(text):
        kind = KINDS[match.group(1).lower()]
        text = text[: match.start()] + text[match.end() :]

    text = _FILLER.sub("", " ".join(text.split())).strip(" ,.-")
    return ParsedQuery(text=text, date_from=date_from, date_until=date_until, kind=kind)
