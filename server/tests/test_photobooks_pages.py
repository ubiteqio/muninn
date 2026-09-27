"""What a book is made of, before any machine has a say: which pictures, and on which pages."""

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any

from muninn.models.photobook import SIZE_LARGE, SIZE_MEDIUM, SIZE_SMALL
from muninn.photobooks import pages as layout
from muninn.photobooks import words
from muninn.photobooks.selection import Shot, apart, chosen, how_many, spread, thinned

NOON = datetime(2024, 4, 25, 12, 0, tzinfo=UTC)


def far(at: int) -> int:
    """A fingerprint of its own. Two hashes of unrelated pictures differ in about half the bits;
    two that differ in a single shifted bit are two bits apart and are the same picture."""
    digest = hashlib.md5(f"picture {at}".encode(), usedforsecurity=False).digest()[:8]
    return int.from_bytes(digest, signed=True)  # as the duplicate finder stores them: int64


def a_shot(
    at: int = 0,
    *,
    minutes: int = 0,
    fingerprint: int | None = None,
    caption: str = "",
    people: int = 0,
    persons: tuple[str, ...] = (),
    tags: tuple[str, ...] = (),
    ocr: str = "",
    place: str = "",
    latitude: float | None = None,
    guessed: bool = False,
    width: int = 4000,
    height: int = 3000,
) -> Shot:
    return Shot(
        id=f"{at:08d}-0000-0000-0000-000000000000",
        taken_at=NOON + timedelta(minutes=minutes or at),
        guessed=guessed,
        kind="image",
        width=width,
        height=height,
        has_preview=True,
        latitude=latitude,
        longitude=11.0 if latitude else None,
        place=place,
        caption=caption,
        ocr=ocr,
        people=people,
        persons=persons,
        tags=tags,
        fingerprint=fingerprint,
    )


class TestThinning:
    def test_a_burst_of_one_thing_becomes_the_best_of_it(self) -> None:
        # Four shots two bits apart - one moment, photographed four times.
        burst = [a_shot(at, fingerprint=0b1111 ^ (1 << at), caption="x" * at) for at in range(4)]
        kept = thinned(burst)

        assert len(kept) == 1
        assert kept[0].caption == "xxx"  # the one the analyzer had most to say about

    def test_different_pictures_all_stay(self) -> None:
        different = [a_shot(at, fingerprint=far(at)) for at in range(4)]

        assert len(thinned(different)) == 4

    def test_a_picture_without_a_fingerprint_is_never_dropped(self) -> None:
        # Two identical hashes and one medium nobody fingerprinted: the unknown one stays.
        assert len(thinned([a_shot(0, fingerprint=7), a_shot(1, fingerprint=7), a_shot(2)])) == 2

    def test_what_is_kept_is_back_in_the_order_of_the_album(self) -> None:
        shots = [a_shot(at, fingerprint=far(at)) for at in range(5)]

        assert [one.id for one in thinned(shots)] == [one.id for one in shots]

    def test_distance_is_the_number_of_differing_bits(self) -> None:
        assert apart(a_shot(0, fingerprint=0b1010), a_shot(1, fingerprint=0b1001)) == 2
        assert apart(a_shot(0, fingerprint=None), a_shot(1, fingerprint=3)) == 64


class TestHowMany:
    def test_each_size_takes_its_share_of_the_album(self) -> None:
        assert how_many(100, SIZE_SMALL, 999) == 15
        assert how_many(100, SIZE_MEDIUM, 999) == 30
        assert how_many(100, SIZE_LARGE, 999) == 60

    def test_the_ceiling_wins_over_the_share(self) -> None:
        # The folder with 4500 holidays: 60 percent would be 2700 pages of book.
        assert how_many(4500, SIZE_LARGE, 150) == 150

    def test_a_small_album_is_never_cut_below_what_makes_a_book(self) -> None:
        assert how_many(20, SIZE_SMALL, 150) == 8  # 15 percent would be three pictures
        assert how_many(5, SIZE_SMALL, 150) == 5  # and five pictures are all there is


class TestSpread:
    def test_it_reaches_from_the_first_picture_to_the_last(self) -> None:
        album = [a_shot(at) for at in range(100)]
        taken = spread(album, 10)

        assert taken[0].id == album[0].id
        assert taken[-1].id == album[-1].id

    def test_it_takes_from_the_whole_album_not_from_the_front(self) -> None:
        album = [a_shot(at) for at in range(100)]
        taken = spread(album, 10)

        assert len(taken) == 10
        # Every tenth of the album is represented exactly once.
        assert sorted(album.index(one) // 10 for one in taken) == list(range(10))

    def test_another_seed_makes_another_book(self) -> None:
        album = [a_shot(at, caption="x" * (at % 7)) for at in range(100)]

        assert [one.id for one in spread(album, 20, 1)] != [one.id for one in spread(album, 20, 9)]

    def test_the_same_seed_makes_the_same_book(self) -> None:
        album = [a_shot(at, caption="x" * (at % 7)) for at in range(100)]

        assert [one.id for one in spread(album, 20, 4)] == [one.id for one in spread(album, 20, 4)]

    def test_a_short_album_is_taken_whole(self) -> None:
        album = [a_shot(at) for at in range(5)]

        assert spread(album, 10) == album

    def test_thinning_happens_before_the_spread(self) -> None:
        # Ten pictures, of which eight are the same shot: a book of five cannot be five of those.
        album = [a_shot(at, fingerprint=1) for at in range(8)]
        album += [a_shot(8, fingerprint=far(8)), a_shot(9, fingerprint=far(9))]

        assert len(chosen(album, size=SIZE_LARGE, ceiling=5)) == 3


class TestPages:
    def test_a_book_opens_with_a_title_and_closes_with_a_map(self) -> None:
        book = layout.pages_of([a_shot(at, place="Pernau", latitude=58.4) for at in range(3)])

        assert book[0]["kind"] == "auftakt"
        assert book[-1]["kind"] == "schluss"
        assert book[-1]["route"][0]["name"] == "Pernau"

    def test_a_day_gets_its_own_page_before_its_moments(self) -> None:
        book = layout.pages_of([a_shot(at) for at in range(3)])
        kinds = [page["kind"] for page in book]

        assert kinds[1] == "tag"
        assert "streifen" in kinds

    def test_a_burst_becomes_a_contact_sheet_and_a_handful_a_strip(self) -> None:
        many = layout.pages_of([a_shot(at) for at in range(12)])
        few = layout.pages_of([a_shot(at) for at in range(3)])

        assert any(page["kind"] == "kontaktbogen" for page in many)
        assert any(page["kind"] == "streifen" for page in few)

    def test_a_single_wide_picture_runs_across_the_page(self) -> None:
        book = layout.pages_of([a_shot(0, width=4000, height=2000)])

        assert any(page["kind"] == "doppelseite" for page in book)

    def test_what_somebody_photographed_because_it_was_written_on(self) -> None:
        menu = a_shot(0, ocr="Külmad suupisted / Appetizers / Холодные закуски / 4.50")
        book = layout.pages_of([menu, a_shot(1), a_shot(2)])
        found = next(page for page in book if page["kind"] == "fundstueck")

        assert "Külmad suupisted" in found["lines"]

    def test_a_picture_dated_only_by_its_folder_joins_the_moment_it_belongs_to(self) -> None:
        # The grill picture carries the 1st of January and must not open a day of its own.
        grill = Shot(
            id="ffffffff-0000-0000-0000-000000000000",
            taken_at=datetime(2024, 1, 1, 0, 0, tzinfo=UTC),
            guessed=True,
            kind="image",
            width=4000,
            height=3000,
            has_preview=True,
            tags=("grill", "fleisch"),
        )
        afternoon = [a_shot(at, tags=("grill", "kohle")) for at in range(3)]
        morning = [a_shot(at, minutes=-600, tags=("flugzeug",)) for at in range(3)]

        book = layout.pages_of([*morning, *afternoon, grill])

        assert not any(page.get("day", "").endswith("1. Januar") for page in book)
        assert sum(1 for page in book if page["kind"] == "tag") == 1

    def test_a_guessed_picture_shows_no_time_of_its_own(self) -> None:
        shown = layout.picture(a_shot(0, guessed=True))

        assert shown["at"] == ""

    def test_the_facts_carry_what_the_writing_may_use_and_the_page_carries_its_pictures(
        self,
    ) -> None:
        run = [
            a_shot(
                0,
                caption="Ein Glas steht auf dem Tisch.",
                persons=("Matteo",),
                width=3000,
                height=4000,
            )
        ]
        page = layout.with_pictures(layout.page_for(run)[0], run)

        assert page["facts"]["personen"] == ["Matteo"]
        assert page["facts"]["bilder"][0]["beschreibung"] == "Ein Glas steht auf dem Tisch."
        assert page["_pictures"][0]["caption"] == "Ein Glas steht auf dem Tisch."

    def test_an_album_without_pictures_is_no_book(self) -> None:
        assert layout.pages_of([]) == []


class TestFaults:
    """The rules that keep the machine's prose out of the catalogue voice."""

    def page(self, **facts: Any) -> dict[str, Any]:
        return {"personen": [], "bilder": [], **facts}

    def test_counting_people_is_the_worst_fault(self) -> None:
        written = {
            "headline": "Vier Männer und ein Hund",
            "story": "Sie gehen den Weg entlang.",
            "bildzeilen": [],
        }

        assert "zählt Menschen" in words.weak(written, self.page())
        assert words.scored(written, self.page()) >= 6

    def test_a_number_in_front_of_people_is_caught_even_when_the_list_has_it_not(self) -> None:
        written = {"headline": "Unterwegs", "story": "Sieben Gäste am Tisch.", "bildzeilen": []}

        assert words.scored(written, self.page()) > 0

    def test_a_known_name_must_appear(self) -> None:
        written = {"headline": "Unterwegs", "story": "Es geht weiter.", "bildzeilen": []}

        assert "Matteo" in words.weak(written, self.page(personen=["Matteo"]))

    def test_a_headline_that_only_says_where_somebody_looks(self) -> None:
        written = {
            "headline": "Junge blickt aus dem Fenster",
            "story": "Es geht weiter.",
            "bildzeilen": [],
        }

        assert words.scored(written, self.page()) > 0

    def test_a_moment_of_the_flight_nobody_wrote_down(self) -> None:
        written = {
            "headline": "Matteo und sein Handy",
            "story": "Kurz vor der Landung schaut er hinaus.",
            "bildzeilen": [],
        }

        assert "Landung" in words.weak(written, self.page()) or words.scored(written, {}) > 0

    def test_hedging_never_goes_into_a_book(self) -> None:
        written = {
            "headline": "Scooter unterwegs",
            "story": "Boris fährt los, Lauri vielleicht mit.",
            "bildzeilen": [],
        }

        assert "Vermutung" in words.weak(written, self.page())

    def test_warmth_is_allowed(self) -> None:
        written = {
            "headline": "Der Grill ist an",
            "story": "Boris freut sich sichtlich, der Abend kann kommen.",
            "bildzeilen": ["Rauch über der Kohle"],
        }

        assert words.faults(written, self.page(personen=["Boris"])) == []

    def test_one_line_per_picture_is_expected(self) -> None:
        written = {"headline": "Am Grill", "story": "Es raucht.", "bildzeilen": ["Eine Zeile"]}
        facts = self.page(bilder=[{"nr": 1, "personen": []}, {"nr": 2, "personen": []}])

        assert "2 Bildzeilen" in words.weak(written, facts)

    def test_the_lines_of_the_machine_land_under_the_pictures(self) -> None:
        run = [a_shot(0, caption="Ein Glas steht auf dem Tisch.", width=3000, height=4000)]
        page = layout.with_pictures(layout.page_for(run)[0], run)

        words.put(
            page,
            {
                "headline": "Kühle Pause",
                "story": "Das Wasser steht bereit.",
                "bildzeilen": ["Kaltes Wasser gegen die Hitze"],
            },
        )

        assert page["headline"] == "Kühle Pause"
        assert page["_pictures"][0]["caption"] == "Kaltes Wasser gegen die Hitze"
