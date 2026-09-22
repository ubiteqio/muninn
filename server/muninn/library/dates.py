"""Reading a capture date out of a name.

Sources 3 and 4 of the concept, for the many files from 26 years of cameras whose EXIF is
incomplete or missing. Both are guesses and are stored as such.
"""

import re
from datetime import UTC, datetime

#: IMG_20120814_153012.jpg, 2012-08-14 15.30.12.jpg, PXL_20211231_235959123.jpg
_FULL_DATE = re.compile(
    r"(?P<year>19[7-9]\d|20[0-4]\d)[-_.]?(?P<month>0[1-9]|1[0-2])[-_.]?(?P<day>0[1-9]|[12]\d|3[01])"
    r"(?:[-_. tT]?(?P<hour>[01]\d|2[0-3])[-_.:]?(?P<minute>[0-5]\d)[-_.:]?(?P<second>[0-5]\d))?"
)

#: "2009-07 Italien", "2009_07", "Sommer 2009"
_YEAR_MONTH = re.compile(r"(?P<year>19[7-9]\d|20[0-4]\d)[-_.]?(?P<month>0[1-9]|1[0-2])(?!\d)")
_YEAR_ONLY = re.compile(r"(?<!\d)(?P<year>19[7-9]\d|20[0-4]\d)(?!\d)")


def date_from_name(name: str) -> datetime | None:
    """A date spelled out in a file name, down to the second when it is there."""
    match = _FULL_DATE.search(name)
    if match is None:
        return None

    parts = match.groupdict()
    try:
        return datetime(
            int(parts["year"]),
            int(parts["month"]),
            int(parts["day"]),
            int(parts["hour"] or 0),
            int(parts["minute"] or 0),
            int(parts["second"] or 0),
            tzinfo=UTC,
        )
    except ValueError:
        return None


def date_from_folder(relative_path: str) -> datetime | None:
    """A date in a folder name, taken from the deepest folder that carries one.

    A folder says a month at best, so the first of the month is as precise as this gets.
    """
    for part in reversed([part for part in relative_path.split("/") if part]):
        full = date_from_name(part)
        if full is not None:
            return full

        month = _YEAR_MONTH.search(part)
        if month is not None:
            return datetime(int(month["year"]), int(month["month"]), 1, tzinfo=UTC)

        year = _YEAR_ONLY.search(part)
        if year is not None:
            return datetime(int(year["year"]), 1, 1, tzinfo=UTC)

    return None
