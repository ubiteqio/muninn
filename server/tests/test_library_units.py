"""The parts of the library that need neither database nor NAS."""

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from muninn.library.dates import date_from_folder, date_from_name
from muninn.library.formats import FileKind, kind_of, stem_of
from muninn.library.grouping import group_files
from muninn.library.hashing import quick_hash_file
from muninn.library.metadata import from_tags
from muninn.library.safety import deletions_are_suspicious
from muninn.library.scanner import ScannedFile, signature_of, walk
from muninn.models.media import DateSource, MediaFileRole, MediaKind

NOW = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)
OLD = NOW - timedelta(days=1)


def a_file(relative_path: str, *, size: int = 10, modified_at: datetime = OLD) -> ScannedFile:
    return ScannedFile(
        relative_path=relative_path,
        name=relative_path.rsplit("/", 1)[-1],
        byte_size=size,
        modified_at=modified_at,
    )


def write(root: Path, relative_path: str, *, content: bytes = b"x") -> Path:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    stamp = OLD.timestamp()
    os.utime(path, (stamp, stamp))
    return path


class TestFormats:
    @pytest.mark.parametrize(
        ("filename", "expected"),
        [
            ("IMG_1234.JPG", FileKind.IMAGE),
            ("urlaub.heic", FileKind.IMAGE),
            ("IMG_1234.CR2", FileKind.RAW),
            ("video.MTS", FileKind.VIDEO),
            ("notizen.txt", None),
            ("ohne-endung", None),
        ],
    )
    def test_what_counts_as_a_medium(self, filename: str, expected: FileKind | None) -> None:
        assert kind_of(filename) is expected

    def test_names_are_compared_without_case(self) -> None:
        assert stem_of("IMG_1234.JPG") == stem_of("img_1234.cr2")


class TestGrouping:
    def test_raw_and_jpeg_of_one_name_are_one_medium(self) -> None:
        groups = group_files([a_file("IMG_1.CR2"), a_file("IMG_1.JPG")])

        assert len(groups) == 1
        assert groups[0].kind is MediaKind.IMAGE
        assert groups[0].primary.name == "IMG_1.JPG"
        assert [role for role, _ in groups[0].others] == [MediaFileRole.RAW]

    def test_a_lone_raw_is_its_own_medium(self) -> None:
        groups = group_files([a_file("IMG_2.NEF")])

        assert len(groups) == 1
        assert groups[0].primary.name == "IMG_2.NEF"

    def test_a_live_photo_keeps_its_clip(self) -> None:
        groups = group_files([a_file("IMG_3.HEIC"), a_file("IMG_3.MOV")])

        assert len(groups) == 1
        assert [role for role, _ in groups[0].others] == [MediaFileRole.MOTION]

    def test_a_jpeg_next_to_a_film_of_the_same_name_stays_two_media(self) -> None:
        """Only HEIC plus MOV is a Live Photo; a JPEG and an MP4 are two things."""
        groups = group_files([a_file("ferien.jpg"), a_file("ferien.mp4")])

        assert {group.kind for group in groups} == {MediaKind.IMAGE, MediaKind.VIDEO}

    def test_videos_of_the_same_name_stay_apart(self) -> None:
        groups = group_files([a_file("clip.mov"), a_file("clip.mp4")])

        assert len(groups) == 2


class TestWalk:
    def test_every_folder_becomes_an_album_even_without_media(self, tmp_path: Path) -> None:
        write(tmp_path, "2009 Italien/IMG_1.jpg")
        write(tmp_path, "2009 Italien/Tag 2/IMG_2.jpg")
        (tmp_path / "leer").mkdir()

        folders = {folder.relative_path: folder for folder in walk(tmp_path)}

        assert set(folders) == {"", "2009 Italien", "2009 Italien/Tag 2", "leer"}
        assert folders["2009 Italien/Tag 2"].parent_path == "2009 Italien"
        assert folders["leer"].files == ()

    def test_ignored_and_hidden_entries_are_skipped(self, tmp_path: Path) -> None:
        write(tmp_path, "@eaDir/thumb.jpg")
        write(tmp_path, ".versteckt/IMG.jpg")
        write(tmp_path, "album/Thumbs.db")
        write(tmp_path, "album/IMG_1.jpg")

        folders = {
            folder.relative_path: folder
            for folder in walk(tmp_path, ignored_names=["@eaDir", "Thumbs.db"])
        }

        assert set(folders) == {"", "album"}
        assert [file.name for file in folders["album"].files] == ["IMG_1.jpg"]

    def test_an_empty_file_is_not_a_medium(self, tmp_path: Path) -> None:
        """A copy that has only just started leaves entries of zero bytes behind."""
        write(tmp_path, "album/IMG_1.jpg")
        write(tmp_path, "album/IMG_2.jpg", content=b"")

        folder = next(item for item in walk(tmp_path) if item.relative_path == "album")

        assert [file.name for file in folder.files] == ["IMG_1.jpg"]

    def test_a_folder_that_cannot_be_listed_says_so(self, tmp_path: Path) -> None:
        """An unreadable folder proves nothing - above all not that its files are gone."""
        folder = tmp_path / "gesperrt"
        folder.mkdir()
        write(folder, "IMG_1.jpg")
        folder.chmod(0o000)

        try:
            folders = {item.relative_path: item for item in walk(tmp_path)}
        finally:
            folder.chmod(0o755)

        assert folders["gesperrt"].listing_failed is True
        assert folders["gesperrt"].was_read is False

    def test_a_folder_whose_signature_still_matches_is_left_alone(self, tmp_path: Path) -> None:
        write(tmp_path, "album/IMG_1.jpg")
        first = next(folder for folder in walk(tmp_path) if folder.relative_path == "album")

        second = next(
            folder
            for folder in walk(tmp_path, known_signatures={"album": first.signature or ""})
            if folder.relative_path == "album"
        )

        assert second.skipped is True
        assert second.files == ()
        assert second.was_read is False

    def test_subfolders_are_visited_even_below_a_skipped_folder(self, tmp_path: Path) -> None:
        """A change in the depth does not show in the signature above it."""
        write(tmp_path, "album/IMG_1.jpg")
        write(tmp_path, "album/Tag 2/IMG_2.jpg")
        signature = next(
            folder.signature for folder in walk(tmp_path) if folder.relative_path == "album"
        )

        folders = {
            folder.relative_path: folder
            for folder in walk(tmp_path, known_signatures={"album": signature or ""})
        }

        assert folders["album"].skipped is True
        assert folders["album/Tag 2"].skipped is False

    def test_a_walk_can_start_inside_the_root(self, tmp_path: Path) -> None:
        write(tmp_path, "album/IMG_1.jpg")
        write(tmp_path, "anderes/IMG_2.jpg")

        folders = [folder.relative_path for folder in walk(tmp_path, base_relative="album")]

        assert folders == ["album"]


class TestSignature:
    def test_the_same_listing_gives_the_same_signature(self) -> None:
        files = [a_file("IMG_1.jpg"), a_file("IMG_2.jpg")]

        assert signature_of(files) == signature_of(list(reversed(files)))

    def test_a_renamed_file_changes_it(self, tmp_path: Path) -> None:
        """Some NAS systems do not touch the folder time on a rename. The listing does."""
        before = signature_of([a_file("IMG_1.jpg")])

        assert before != signature_of([a_file("Italien.jpg")])

    def test_a_changed_size_changes_it(self) -> None:
        before = signature_of([a_file("IMG_1.jpg", size=10)])

        assert before != signature_of([a_file("IMG_1.jpg", size=11)])

    def test_a_changed_time_changes_it(self) -> None:
        before = signature_of([a_file("IMG_1.jpg")])
        later = a_file("IMG_1.jpg", modified_at=OLD + timedelta(seconds=1))

        assert before != signature_of([later])


class TestQuickHash:
    def test_the_same_file_gives_the_same_hash(self, tmp_path: Path) -> None:
        first = write(tmp_path, "a.jpg", content=b"x" * 1000)
        second = write(tmp_path, "b.jpg", content=b"x" * 1000)

        assert quick_hash_file(first, 1000) == quick_hash_file(second, 1000)

    def test_other_content_of_the_same_size_differs(self, tmp_path: Path) -> None:
        first = write(tmp_path, "a.jpg", content=b"x" * 1000)
        second = write(tmp_path, "b.jpg", content=b"y" * 1000)

        assert quick_hash_file(first, 1000) != quick_hash_file(second, 1000)

    def test_the_size_is_part_of_it(self, tmp_path: Path) -> None:
        path = write(tmp_path, "a.jpg", content=b"x" * 1000)

        assert quick_hash_file(path, 1000) != quick_hash_file(path, 999)


class TestSafetyNet:
    @pytest.mark.parametrize(
        ("missing", "known", "expected"),
        [
            (0, 1000, False),
            (49, 1000, False),
            (51, 1000, True),
            (500, 100_000, True),
            (2, 3, True),
        ],
    )
    def test_when_a_sync_pauses(self, missing: int, known: int, expected: bool) -> None:
        paused = deletions_are_suspicious(missing=missing, known=known, share_percent=5, count=500)

        assert paused is expected

    def test_the_thresholds_come_from_the_settings(self) -> None:
        assert deletions_are_suspicious(missing=2, known=100, share_percent=1, count=500) is True
        assert deletions_are_suspicious(missing=2, known=100, share_percent=50, count=500) is False


class TestDates:
    @pytest.mark.parametrize(
        ("filename", "expected"),
        [
            ("IMG_20120814_153012.jpg", datetime(2012, 8, 14, 15, 30, 12, tzinfo=UTC)),
            ("2009-07-14 12.05.33.jpg", datetime(2009, 7, 14, 12, 5, 33, tzinfo=UTC)),
            ("PXL_20211231_235959123.jpg", datetime(2021, 12, 31, 23, 59, 59, tzinfo=UTC)),
            ("urlaub.jpg", None),
            ("IMG_20129999_000000.jpg", None),
        ],
    )
    def test_a_date_in_the_file_name(self, filename: str, expected: datetime | None) -> None:
        assert date_from_name(filename) == expected

    @pytest.mark.parametrize(
        ("folder", "expected"),
        [
            ("2009-07 Italien", datetime(2009, 7, 1, tzinfo=UTC)),
            ("Bilder/Sommer 2009", datetime(2009, 1, 1, tzinfo=UTC)),
            ("Bilder/2009-07 Italien/Tag 2", datetime(2009, 7, 1, tzinfo=UTC)),
            ("Bilder/Ohne Datum", None),
        ],
    )
    def test_a_date_in_the_folder_name(self, folder: str, expected: datetime | None) -> None:
        assert date_from_folder(folder) == expected


class TestMetadataFromTags:
    def test_exif_wins_over_everything_else(self) -> None:
        read = from_tags(
            {"DateTimeOriginal": "2012:08:14 15:30:12", "Make": "Canon", "Model": "EOS 400D"},
            filename="IMG_20200101_000000.jpg",
            relative_path="2009 Italien/IMG_20200101_000000.jpg",
            modified_at=NOW,
        )

        assert read.taken_at == datetime(2012, 8, 14, 15, 30, 12, tzinfo=UTC)
        assert read.taken_at_source is DateSource.EXIF
        assert (read.camera_make, read.camera_model) == ("Canon", "EOS 400D")

    def test_without_exif_the_file_name_decides(self) -> None:
        read = from_tags(
            {}, filename="IMG_20120814_153012.jpg", relative_path="a/b.jpg", modified_at=NOW
        )

        assert read.taken_at_source is DateSource.FILENAME

    def test_then_the_folder_name(self) -> None:
        read = from_tags(
            {}, filename="scan001.jpg", relative_path="2009-07 Italien/scan001.jpg", modified_at=NOW
        )

        assert read.taken_at == datetime(2009, 7, 1, tzinfo=UTC)
        assert read.taken_at_source is DateSource.FOLDER_NAME

    def test_and_last_the_file_itself(self) -> None:
        read = from_tags(
            {}, filename="scan001.jpg", relative_path="alben/scan001.jpg", modified_at=NOW
        )

        assert read.taken_at == NOW
        assert read.taken_at_source is DateSource.FILE_MTIME

    def test_empty_exif_dates_are_not_dates(self) -> None:
        read = from_tags(
            {"DateTimeOriginal": "0000:00:00 00:00:00"},
            filename="scan.jpg",
            relative_path="scan.jpg",
            modified_at=NOW,
        )

        assert read.taken_at_source is DateSource.FILE_MTIME

    def test_coordinates_at_exactly_zero_mean_no_fix(self) -> None:
        read = from_tags(
            {"GPSLatitude": 0, "GPSLongitude": 0},
            filename="scan.jpg",
            relative_path="scan.jpg",
            modified_at=NOW,
        )

        assert (read.latitude, read.longitude) == (None, None)


class TestPictureSize:
    def test_a_quarter_turn_swaps_width_and_height(self) -> None:
        """EXIF reports the sensor, not the picture: a portrait photo says 4032 x 3024."""
        read = from_tags(
            {"ImageWidth": 4032, "ImageHeight": 3024, "Orientation": 6},
            filename="IMG_1.heic",
            relative_path="album/IMG_1.heic",
            modified_at=NOW,
        )

        assert (read.width, read.height) == (3024, 4032)

    def test_an_upright_picture_is_left_alone(self) -> None:
        read = from_tags(
            {"ImageWidth": 4032, "ImageHeight": 3024, "Orientation": 1},
            filename="IMG_1.jpg",
            relative_path="album/IMG_1.jpg",
            modified_at=NOW,
        )

        assert (read.width, read.height) == (4032, 3024)
