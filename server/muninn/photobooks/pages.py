"""The pages of a book: what each one shows, and what is known about it.

A page is not a row of pictures. It is a moment - a run of shots close in time - laid out in one
of a few shapes: the wide picture across two pages, the strip beside a large one, the contact
sheet of a burst, the thing somebody photographed because it was written on. Which shape a
moment gets follows from what it is: how many pictures, whether they carry coordinates, whether
one of them has text on it.

Every page that speaks carries its ``facts``: the times, places, names and descriptions the
library already holds. Those facts are the only material the writing may use, and they are
dropped before the book is stored - they are the raw analyzer sentences, and the whole point of
the writing is that those do not end up under the pictures.
"""

import hashlib
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import replace
from datetime import date, datetime
from typing import Any

from muninn.photobooks.selection import Shot

MONTHS = (
    "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember",
)  # fmt: skip
WEEKDAYS = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag")

#: What the pictures are of, by the words the description model used. The first that matches
#: names the page; a family archive is full of these few things.
DOINGS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Im Flugzeug", ("flugzeug", "flughafen", "kopfhörer")),
    ("Am Grill", ("grill", "fleisch", "rauch", "kohle")),
    ("Mit dem Roller", ("scooter", "roller", "elektro-scooter")),
    ("Im Auto", ("auto", "rücksitz", "fahrzeug", "parkplatz")),
    ("Bei Tisch", ("essen", "teller", "tisch", "restaurant", "frühstück", "glas")),
    ("Am Wasser", ("reflexion", "spiegelung", "watt", "ufer")),
    ("Am Strand", ("strand", "sand", "meer", "düne")),
    ("Im Park", ("vogel", "vögel", "park", "bank", "möwe")),
    ("Auf dem Spielplatz", ("klettergerüst", "spielplatz", "rutsche", "schaukel")),
    ("In der Stadt", ("stadt", "straße", "fassade", "gebäude", "schild")),
    ("Im Schnee", ("schnee", "winter", "eis", "schlitten")),
    ("Am Wasser", ("see", "fluss", "boot", "hafen")),
)

#: How long a gap makes the next picture a new moment.
GAP_MINUTES = 45


def tilt(media_id: str, spread: float = 2.0) -> float:
    """How crooked a picture sits on the page - always the same for the same picture."""
    seed = int(hashlib.md5(media_id.encode(), usedforsecurity=False).hexdigest()[:8], 16)
    return round(((seed % 1000) / 1000 - 0.5) * 2 * spread, 2)


def tape(media_id: str) -> str:
    """Which way a picture is stuck down."""
    seed = int(hashlib.md5(f"{media_id}tape".encode(), usedforsecurity=False).hexdigest()[:8], 16)
    return ("washi", "corners", "strip")[seed % 3]


def sentence(caption: str) -> str:
    """The first sentence of what the model saw - the rest repeats itself."""
    first = caption.split(". ")[0].strip()
    return first if first.endswith(".") else f"{first}."


def clock(when: datetime) -> str:
    return when.strftime("%H:%M")


def day_name(when: date) -> str:
    return f"{WEEKDAYS[when.weekday()]}, {when.day}. {MONTHS[when.month - 1]}"


def shots(count: int) -> str:
    return "eine Aufnahme" if count == 1 else f"{count} Aufnahmen"


def stations(count: int) -> str:
    return "eine Station" if count == 1 else f"{count} Stationen"


def doing(run: Sequence[Shot]) -> str:
    """What is going on in these pictures, by the words that turn up in them."""
    words = Counter(word for one in run for word in [*one.tags, one.scene])
    for name, marks in DOINGS:
        if any(words.get(mark, 0) for mark in marks):
            return name
    return ""


def who(run: Sequence[Shot]) -> list[str]:
    """The people confirmed in these pictures, the most often seen first."""
    names: Counter[str] = Counter()
    for one in run:
        names.update(one.persons)
    return [name for name, _ in names.most_common(3)]


def part_of_day(hour: int) -> str:
    if hour < 10:
        return "morgens"
    if hour < 14:
        return "mittags"
    if hour < 18:
        return "nachmittags"
    return "abends"


def place_card(one: Shot) -> dict[str, str] | None:
    """What the gazetteer knows about the place - the line under a headline."""
    if not one.place:
        return None
    parts = [part for part in (one.region, one.country) if part]
    return {
        "name": one.place,
        "where": ", ".join(parts),
        "people": f"{one.population:,} Einwohner".replace(",", ".") if one.population else "",
    }


def read_lines(ocr: str) -> list[str]:
    """What is legible on the thing, in pieces a page can set: a menu is not one long line."""
    pieces = [piece.strip(" .,·") for piece in ocr.replace("\n", " / ").split("/")]
    kept = [piece for piece in pieces if 2 < len(piece) < 46]
    return kept[:7] if kept else [ocr[:60]]


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


def by_day(media: Sequence[Shot]) -> dict[date, list[list[Shot]]]:
    days: dict[date, list[list[Shot]]] = defaultdict(list)
    for run in runs_of(media):
        days[run[0].taken_at.date()].append(run)
    return dict(sorted(days.items()))


#: Between two times, German sets an en dash. Ruff mistrusts it in source; here it is text.
UNTIL = "\u2013"


def span(run: Sequence[Shot]) -> str:
    return f"{clock(run[0].taken_at)}{UNTIL}{clock(run[-1].taken_at)} Uhr"


def picture(one: Shot, variant: str = "preview", with_caption: bool = False) -> dict[str, Any]:
    """One picture on a page. The address is signed when the book is read, not now."""
    shown: dict[str, Any] = {
        "id": one.id,
        "variant": "thumb" if variant == "preview" and not one.has_preview else variant,
        "tilt": tilt(one.id),
        "tape": tape(one.id),
        "portrait": (one.height or 1) > (one.width or 1),
        "video": one.kind == "video",
        "at": "" if one.guessed else clock(one.taken_at),
    }
    if with_caption and one.caption:
        shown["caption"] = sentence(one.caption)
    return shown


def facts_of(run: Sequence[Shot], scene: dict[str, Any] | None = None) -> dict[str, Any]:
    """What is known about these pictures - the only material the writing may use.

    The people confirmed anywhere in this moment count for the whole of it: the same flight, the
    same table. A face the detector only suspects is passed as a suspicion and named as one.
    """
    confirmed = who(run)
    suspected = sorted({name for one in run for name in one.suggested} - set(confirmed))
    return {
        **(scene or {}),
        "tageszeit": part_of_day(run[0].taken_at.hour),
        "ort": run[0].place,
        "gegend": ", ".join(part for part in (run[0].region, run[0].country) if part),
        "zeit": span(run) if len(run) > 1 else f"{clock(run[0].taken_at)} Uhr",
        "anzahl": len(run),
        "personen": confirmed,
        "vermutlich_dabei": suspected,
        "beschreibungen": [sentence(one.caption) for one in run if one.caption][:5],
        "worte": sorted({word for one in run for word in one.tags})[:10],
        "gelesen": next((read_lines(one.ocr)[:3] for one in run if len(one.ocr) > 25), []),
        "video": any(one.kind == "video" for one in run),
    }


def story_of(run: Sequence[Shot]) -> str:
    """The page text when no machine wrote one: counted, timed, named. Nothing felt."""
    minutes = int((run[-1].taken_at - run[0].taken_at).total_seconds() // 60)
    lines: list[str] = []

    opening = f"{clock(run[0].taken_at)} Uhr"
    if run[0].place:
        opening += f" in {run[0].place}"
    if minutes >= 3:
        opening += (
            f", {minutes} Minuten lang" if minutes < 90 else f", über {minutes // 60} Stunden"
        )
    lines.append(f"{opening}." if len(run) == 1 else f"{opening}: {shots(len(run))}.")

    names = who(run)
    if len(names) > 1:
        lines.append(f"Zu sehen: {', '.join(names[:-1])} und {names[-1]}.")
    elif names:
        lines.append(f"Zu sehen: {names[0]}.")

    longest = max(run, key=lambda one: len(one.caption))
    if longest.caption:
        lines.append(sentence(longest.caption))
    return " ".join(lines)


def moment_of(run: Sequence[Shot]) -> str:
    """A neighbouring station in a few words: when it was, and what was going on."""
    return f"{clock(run[0].taken_at)} Uhr {doing(run).lower()}".strip()


def captioned(page: dict[str, Any]) -> list[dict[str, Any]]:
    """The pictures on this page that carry a line under them, in reading order."""
    found: list[dict[str, Any]] = []
    for field in ("hero", "picture", "pictures", "taped", "column", "strip", "sheet"):
        held = page.get(field)
        shown_here = held if isinstance(held, list) else [held] if isinstance(held, dict) else []
        found.extend(
            shown for shown in shown_here if isinstance(shown, dict) and "caption" in shown
        )
    return found


def with_pictures(page: dict[str, Any], run: Sequence[Shot]) -> dict[str, Any]:
    """Lists the page's captioned pictures in its facts, and remembers which is which.

    The raw description belongs in the facts as material - "Ein Glas mit Eiswürfeln steht auf
    einem Tisch" is what the analyzer saw. What goes under the picture is written from it.
    """
    facts = page.get("facts")
    shown = captioned(page)
    if not facts or not shown:
        return page

    by_id = {one.id: one for one in run}
    facts["bilder"] = [
        {
            "nr": at + 1,
            "beschreibung": sentence(by_id[shot["id"]].caption)
            if shot["id"] in by_id and by_id[shot["id"]].caption
            else "",
            "personen": sorted(by_id[shot["id"]].persons) if shot["id"] in by_id else [],
            "wohl": sorted(set(by_id[shot["id"]].suggested) - set(by_id[shot["id"]].persons))
            if shot["id"] in by_id
            else [],
            "uhr": shot.get("at", ""),
        }
        for at, shot in enumerate(shown)
    ]
    page["_pictures"] = shown
    return page


def pages_of(media: Sequence[Shot], *, title: str = "") -> list[dict[str, Any]]:
    """The whole book, from the opening page to the map at the end."""
    ordered = placed(media)
    if not ordered:
        return []

    cast = who(ordered)
    first, last = ordered[0].taken_at, ordered[-1].taken_at
    days = by_day(ordered)
    towns = list(dict.fromkeys(one.place for one in ordered if one.place))
    abroad = next(
        (one.country for one in ordered if one.country and one.country != "Deutschland"), ""
    )

    pages: list[dict[str, Any]] = [
        {
            "kind": "auftakt",
            "title": title or abroad or "Die Reise",
            "subtitle": _days_between(first, last),
            "route": " · ".join(towns),
            "counts": " · ".join(
                part
                for part in (
                    shots(len(ordered)),
                    f"{sum(1 for one in ordered if one.kind == 'video')} Film"
                    if any(one.kind == "video" for one in ordered)
                    else "",
                    f"{len(days)} Tage" if len(days) > 1 else "",
                    f"{len(towns)} Orte" if len(towns) > 1 else "",
                )
                if part
            ),
            "hero": picture(max(ordered, key=lambda one: (one.people, len(one.caption)))),
        }
    ]

    for when, runs in days.items():
        flat = [one for run in runs for one in run]
        stops = list(dict.fromkeys(one.place for one in flat if one.place))
        pages.append(
            {
                "kind": "tag",
                "day": day_name(when),
                "towns": " → ".join(stops),
                "note": f"{clock(flat[0].taken_at)}{UNTIL}{clock(flat[-1].taken_at)} Uhr · "
                f"{shots(len(flat))} · {stations(len(runs))}",
                "doing": doing(flat),
                "behind": picture(max(flat, key=lambda one: one.people)),
            }
        )
        for at, run in enumerate(runs):
            # What happened just before and just after, in the day's own words. A page that knows
            # its neighbours writes "Nach dem Strand" where it would otherwise write "Bierglas im
            # Freien": the moment is the gap between two others, not the thing in the frame.
            before = runs[at - 1] if at else None
            after = runs[at + 1] if at + 1 < len(runs) else None
            scene = {
                "reise": title or abroad or "die Reise",
                "tag": f"Tag {list(days).index(when) + 1} von {len(days)}",
                "abschnitt": _where_in_journey(days, when, at, len(runs)),
                "reisegruppe": cast,
                "station": f"{at + 1}. von {len(runs)} an diesem Tag",
                **({"davor": moment_of(before)} if before else {}),
                **({"danach": moment_of(after)} if after else {}),
            }
            pages.extend(with_pictures(page, run) for page in page_for(run, scene))

    pages.append(_closing(ordered, days, towns))
    return pages


def _days_between(first: datetime, last: datetime) -> str:
    if first.date() == last.date():
        return f"{last.day}. {MONTHS[last.month - 1]} {last.year}"
    if (first.month, first.year) == (last.month, last.year):
        return f"{first.day}. bis {last.day}. {MONTHS[last.month - 1]} {last.year}"
    return (
        f"{first.day}. {MONTHS[first.month - 1]} bis {last.day}. {MONTHS[last.month - 1]} "
        f"{last.year}"
    )


def _where_in_journey(days: dict[date, list[list[Shot]]], when: date, at: int, of_day: int) -> str:
    if when == next(iter(days)) and at == 0:
        return "Anreise"
    if when == list(days)[-1] and at == of_day - 1:
        return "Abreise"
    return "unterwegs"


def _closing(
    media: Sequence[Shot], days: dict[date, list[list[Shot]]], towns: Sequence[str]
) -> dict[str, Any]:
    """The map at the end: where the book has been, and who was there."""
    return {
        "kind": "schluss",
        "headline": "Die Reise",
        "note": f"{len(days)} Tage · {shots(len(media))}" if len(days) > 1 else shots(len(media)),
        "route": [
            {
                "name": town,
                "lat": next(one.latitude for one in media if one.place == town and one.latitude),
                "lon": next(one.longitude for one in media if one.place == town and one.longitude),
                "land": next(one.country for one in media if one.place == town),
                "anzahl": sum(1 for one in media if one.place == town),
            }
            for town in towns
            if any(one.place == town and one.latitude for one in media)
        ],
        "stations": [
            {
                "name": town,
                "count": sum(1 for one in media if one.place == town),
                "card": place_card(next(one for one in media if one.place == town)),
            }
            for town in towns
        ],
        "people": who(media),
    }


def page_for(run: Sequence[Shot], scene: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """The pages one moment becomes - usually one, two when something was written on."""
    head = run[0]
    what = doing(run)
    pages: list[dict[str, Any]] = []

    read = [one for one in run if len(one.ocr) > 25]
    if read:
        found = max(read, key=lambda one: len(one.ocr))
        pages.append(
            {
                "kind": "fundstueck",
                "facts": facts_of([found], scene),
                "headline": "Gelesen",
                "note": f"{found.place} · {clock(found.taken_at)} Uhr"
                if found.place
                else f"{clock(found.taken_at)} Uhr",
                "story": sentence(found.caption),
                "picture": picture(found),
                "lines": read_lines(found.ocr),
            }
        )
        run = [one for one in run if one.id != found.id]
        if not run:
            return pages
        head = run[0]

    if len(run) >= 10:
        return [
            *pages,
            {
                "kind": "kontaktbogen",
                "facts": facts_of(run, scene),
                "headline": what or "Kurz hintereinander",
                "note": f"{shots(len(run))} · {span(run)}",
                "story": story_of(run),
                "card": place_card(head),
                "hero": picture(run[len(run) // 2], with_caption=True),
                "sheet": [picture(one, "thumb") for one in run],
            },
        ]

    if len(run) >= 5 and any(one.latitude for one in run):
        return [
            *pages,
            {
                "kind": "karte",
                "facts": facts_of(run, scene),
                "headline": head.place or what or "Unterwegs",
                "note": span(run),
                "story": story_of(run),
                "card": place_card(head),
                "points": [
                    {"lat": one.latitude, "lon": one.longitude} for one in run if one.latitude
                ],
                "taped": [picture(one, with_caption=True) for one in run[:2]],
                "strip": [picture(one, "thumb") for one in run[2:6]],
            },
        ]

    if len(run) >= 3:
        hero = max(run, key=lambda one: (one.people, len(one.caption)))
        rest = [one for one in run if one.id != hero.id][:3]
        return [
            *pages,
            {
                "kind": "streifen",
                "facts": facts_of(run, scene),
                "headline": what or head.place or "",
                "note": f"{head.place} · {span(run)}" if head.place else span(run),
                "story": story_of(run),
                "card": place_card(head),
                "hero": picture(hero, with_caption=True),
                "column": [picture(one, "thumb") for one in rest],
            },
        ]

    wide = [one for one in run if one.width > one.height]
    if wide and len(run) == 1:
        return [
            *pages,
            {
                "kind": "doppelseite",
                "facts": facts_of(run, scene),
                "headline": what or head.place or "",
                "note": f"{head.place} · {clock(head.taken_at)} Uhr"
                if head.place
                else f"{clock(head.taken_at)} Uhr",
                "story": sentence(head.caption),
                "picture": picture(wide[0]),
            },
        ]

    return [
        *pages,
        {
            "kind": "zwei",
            "facts": facts_of(run, scene),
            "headline": what or head.place or "",
            "note": span(run) if len(run) > 1 else f"{clock(head.taken_at)} Uhr",
            "story": story_of(run),
            "card": place_card(head),
            "pictures": [picture(one, with_caption=True) for one in run],
        },
    ]
