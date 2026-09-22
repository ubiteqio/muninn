"""Taking a search apart: periods and kinds come out, the rest is what is searched for."""

from datetime import date

import pytest

from muninn.models.media import MediaKind
from muninn.search.query import ParsedQuery, parse


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("Hund am Strand", ParsedQuery(text="Hund am Strand")),
        (
            "Strand 2012",
            ParsedQuery(text="Strand", date_from=date(2012, 1, 1), date_until=date(2013, 1, 1)),
        ),
        (
            "Geburtstag aus 2009",
            ParsedQuery(text="Geburtstag", date_from=date(2009, 1, 1), date_until=date(2010, 1, 1)),
        ),
        (
            "Schnee 2010 bis 2014",
            ParsedQuery(text="Schnee", date_from=date(2010, 1, 1), date_until=date(2015, 1, 1)),
        ),
        (
            "Italien im Sommer 2012",
            ParsedQuery(text="Italien", date_from=date(2012, 6, 1), date_until=date(2012, 9, 1)),
        ),
        (
            "Schlitten Winter 2010",
            ParsedQuery(text="Schlitten", date_from=date(2010, 12, 1), date_until=date(2011, 3, 1)),
        ),
        (
            "Juli 2014 Grillen",
            ParsedQuery(text="Grillen", date_from=date(2014, 7, 1), date_until=date(2014, 8, 1)),
        ),
        (
            "Dezember 2019",
            ParsedQuery(text="", date_from=date(2019, 12, 1), date_until=date(2020, 1, 1)),
        ),
        ("nur Videos vom Strand", ParsedQuery(text="vom Strand", kind=MediaKind.VIDEO)),
        ("Fotos", ParsedQuery(text="", kind=MediaKind.IMAGE)),
    ],
)
def test_a_query_is_taken_apart(query: str, expected: ParsedQuery) -> None:
    assert parse(query) == expected


def test_a_number_that_is_no_year_stays_in_the_text() -> None:
    """House numbers and prices are not periods."""
    assert parse("Hausnummer 42") == ParsedQuery(text="Hausnummer 42")
    assert parse("Bus 1234") == ParsedQuery(text="Bus 1234")
