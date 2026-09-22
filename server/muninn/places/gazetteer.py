"""The places of the world from GeoNames, boiled down to what Muninn needs to name a spot.

GeoNames publishes every place with its coordinates, and separately the names of each in every
language. The image build downloads the files once and turns them into one small table with a
German name for every place, its region and its country - "Florenz, Toskana, Italien" - and
the words it may be searched by in any language. Nothing is asked of GeoNames afterwards: where
a photo was taken never leaves the server.

    python -m muninn.places.gazetteer <directory with the GeoNames files> <target .tsv.gz>

The directory holds cities1000.txt, admin1CodesASCII.txt, countryInfo.txt and
alternateNamesV2.txt, unpacked.
"""

import csv
import gzip
import sys
import unicodedata
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

#: Raised when what the prepared file says, or how it is chosen, changes; places are then
#: loaded and assigned again.
GAZETTEER_VERSION = 1

#: Parts of a town (Maxvorstadt), and places that are gone: a photo from Munich's centre is
#: from München, not from the quarter whose centre happens to lie nearest.
SKIPPED_FEATURES = frozenset({"PPLX", "PPLH", "PPLQ", "PPLW", "PPLCH"})

#: Shorter words are too often something else ("Au", "Ems").
MIN_KEY_LENGTH = 3

csv.field_size_limit(sys.maxsize)


@dataclass(frozen=True, slots=True)
class Place:
    id: int
    name: str
    region: str | None
    country: str | None
    country_code: str
    population: int
    latitude: float
    longitude: float
    #: Lower-case names in Latin script it may be searched by: its own in any language, and
    #: those of its region and country.
    keys: tuple[str, ...]


def is_latin(name: str) -> bool:
    """Only names a German keyboard types; the Cyrillic Москва is no key for Moskau."""
    return all(
        not char.isalpha() or unicodedata.name(char, "").startswith("LATIN") for char in name
    )


def keys_of(names: Iterable[str]) -> set[str]:
    return {
        name.strip().lower()
        for name in names
        if len(name.strip()) >= MIN_KEY_LENGTH
        and is_latin(name)
        and not any(char.isdigit() for char in name)
    }


def _rows(path: Path) -> Iterator[list[str]]:
    with path.open(encoding="utf-8", newline="") as file:
        for row in csv.reader(file, delimiter="\t", quoting=csv.QUOTE_NONE):
            if row and not row[0].startswith("#"):
                yield row


def german_names(path: Path, wanted: set[int]) -> dict[int, str]:
    """The German name of each wanted place: the short one before the official one ("Italien",
    not "Italienische Republik"), the preferred before any other, never a historic one."""
    best: dict[int, tuple[int, str]] = {}
    for row in _rows(path):
        # id, geonameid, language, name, preferred, short, colloquial, historic, from, to
        if len(row) < 8 or row[2] != "de":
            continue
        geoname = int(row[1])
        if geoname not in wanted or row[6] == "1" or row[7] == "1":
            continue
        rank = (0 if row[5] == "1" else 2) + (0 if row[4] == "1" else 1)
        if geoname not in best or rank < best[geoname][0]:
            best[geoname] = (rank, row[3])
    return {geoname: name for geoname, (_, name) in best.items()}


def prepare(source: Path) -> Iterator[Place]:
    countries: dict[str, tuple[int, str]] = {}
    for row in _rows(source / "countryInfo.txt"):
        # ISO, ISO3, ISO numeric, fips, name, capital, area, population, continent, tld,
        # currency code and name, phone, postal code format and pattern, languages, geonameid
        countries[row[0]] = (int(row[16]), row[4])
    regions: dict[str, tuple[int, str, str]] = {}
    for row in _rows(source / "admin1CodesASCII.txt"):
        # "IT.16", name, ascii name, geonameid
        regions[row[0]] = (int(row[3]), row[1], row[2])
    cities = [row for row in _rows(source / "cities1000.txt") if row[7] not in SKIPPED_FEATURES]

    wanted = (
        {int(row[0]) for row in cities}
        | {geoname for geoname, _, _ in regions.values()}
        | {geoname for geoname, _ in countries.values()}
    )
    german = german_names(source / "alternateNamesV2.txt", wanted)

    for row in cities:
        # geonameid, name, ascii name, alternate names, latitude, longitude, feature class and
        # code, country code, cc2, admin1 .. admin4, population, elevation, dem, timezone, date
        geoname, country_code = int(row[0]), row[8]
        region = regions.get(f"{country_code}.{row[10]}")
        country = countries.get(country_code)
        region_name = german.get(region[0], region[1]) if region else None
        country_name = german.get(country[0], country[1]) if country else None
        names = [row[1], row[2], *row[3].split(","), german.get(geoname, "")]
        if region:
            names += [region[1], region[2], german.get(region[0], "")]
        if country:
            names += [country[1], german.get(country[0], "")]
        yield Place(
            id=geoname,
            name=german.get(geoname, row[1]),
            region=region_name,
            country=country_name,
            country_code=country_code,
            population=int(row[14] or 0),
            latitude=float(row[4]),
            longitude=float(row[5]),
            keys=tuple(sorted(keys_of(names))),
        )


def write(places: Iterable[Place], target: Path) -> int:
    count = 0
    with gzip.open(target, "wt", encoding="utf-8", newline="") as file:
        out = csv.writer(file, delimiter="\t", quoting=csv.QUOTE_NONE, escapechar="\\")
        for place in places:
            out.writerow(
                [
                    place.id,
                    place.name,
                    place.region or "",
                    place.country or "",
                    place.country_code,
                    place.population,
                    place.latitude,
                    place.longitude,
                    "|".join(place.keys),
                ]
            )
            count += 1
    return count


def read(path: Path) -> Iterator[Place]:
    with gzip.open(path, "rt", encoding="utf-8", newline="") as file:
        for row in csv.reader(file, delimiter="\t", quoting=csv.QUOTE_NONE, escapechar="\\"):
            yield Place(
                id=int(row[0]),
                name=row[1],
                region=row[2] or None,
                country=row[3] or None,
                country_code=row[4],
                population=int(row[5]),
                latitude=float(row[6]),
                longitude=float(row[7]),
                keys=tuple(row[8].split("|")) if row[8] else (),
            )


if __name__ == "__main__":
    written = write(prepare(Path(sys.argv[1])), Path(sys.argv[2]))
    print(f"{written} places")
