"""Build the demo library the App Store screenshots are taken from.

A small, invented family archive: nine folders of photos from Wikimedia Commons, every one of
them CC0 or public domain, so the screenshots can be published. The originals' metadata is
stripped and replaced with a capture date, a place and a camera that fit the folder they are
in, so the timeline, "Heute vor X Jahren" and the map have something to show.

    python3 app/store/demo/build_library.py [target]   # default: data/demo/library

Needs exiftool. Downloads about 70 photos once; files already there are kept.
"""

import json
import random
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

API = "https://commons.wikimedia.org/w/api.php?"
USER_AGENT = "muninn-demo-library/1.0 (https://github.com/ubiteqio/muninn)"
#: Large enough for a sharp preview on a tablet, small enough to keep the download quick.
WIDTH = 2400


@dataclass(frozen=True)
class Folder:
    path: str
    start: datetime
    days: int
    lat: float
    lon: float
    camera: tuple[str, str]
    files: tuple[str, ...]


FOLDERS = (
    Folder(
        "2009/2009-08 Sommerurlaub Ostsee",
        datetime(2009, 8, 3, 10),
        9,
        54.05,
        14.08,
        ("Canon", "Canon EOS 450D"),
        (
            "Beach-647938 640.jpg",
            "Coast in Saunags.jpg",
            "Plage de la Baltique un jour d'orage.JPG",
            "Cliffed coast with resting man near sunset.JPG",
            "Strandkörbe in Kühlungsborn-3-.jpg",
            "GotskaSandön 02.jpg",
            "GotskaSandön 01.jpg",
            "HolnisDrei.JPG",
            "Sunrise on the beach (49336223491).jpg",
            "Children playing at the beach.JPG",
            "Children making sandcastles on Rossbeigh Beach, County Kerry, Ireland 01.jpg",
            "Children making sandcastles on Rossbeigh Beach, County Kerry, Ireland 02.jpg",
            "Child on the beach (Unsplash).jpg",
            "Moody Beach, Wells, United States (Unsplash).jpg",
            "Children enjoying the beach (Unsplash).jpg",
        ),
    ),
    Folder(
        "2012/2012-07 Wandern im Allgäu",
        datetime(2012, 7, 14, 9),
        6,
        47.41,
        10.28,
        ("Panasonic", "DMC-TZ10"),
        (
            "Alps mountains Slovenia.jpg",
            "Alpine meadows and mountains 02.jpg",
            "Alpine meadows and mountains 01.jpg",
            "View Julian Alps from Mrzli vrh 01.jpg",
            "Reifenberg (Chiemgau Alps).jpg",
            "Lookout in Alps (Germany) 04.jpg",
            "Lookout in Alps (Germany) 01.jpg",
            "Lookout in Alps (Germany) 02.jpg",
            "Lookout in Alps (Germany) 05.jpg",
            "Lookout in Alps (Germany) 11.jpg",
            "E-biking at Les Saisies.jpg",
            "Allgäu alps autumn 2017-10-13.jpg",
            "Mixed-breed dogs in Serles.jpg",
        ),
    ),
    Folder(
        "2014/2014-12 Weihnachten bei Oma",
        datetime(2014, 12, 22, 15),
        6,
        49.89,
        10.89,
        ("Apple", "iPhone 5s"),
        (
            "Tallinn Christmas tree 2024.jpg",
            "SouthSide Works Christmas Tree, 2019-12-14, 02.jpg",
            "Christmas tree at Regency Mall, Richmond.jpg",
            "Christmas Tree Oulu Market Hall 20251128.jpg",
            "Enfants faisant un bonhomme de neige.JPG",
            "20210117Schneemann Saarbrücken13.jpg",
            "20210117Schneemann Saarbrücken09.jpg",
            "Moscow, tiny snowman, Jan 2026 04.jpg",
            "Snowman on a foggy day.jpg",
        ),
    ),
    Folder(
        "2016/2016-05 Lenas 7. Geburtstag",
        datetime(2016, 5, 21, 14),
        1,
        50.94,
        6.96,
        ("Apple", "iPhone 6s"),
        (
            "Birthday Cake Bloomsburg, Pennsylvania.jpg",
            "Happy Birthday! (Unsplash).jpg",
            "Birthday cake..red.jpg",
            "Children playing in sarıyer, istanbul.jpg",  # noqa: RUF001
            "Children Playing at West Court of Jian-Kang Elementary School 20180331a.jpg",
            "Dali-Slides-And-Bicycle-20241229.jpg",
            "Pedion tou Areos City Garden 10.jpg",
            "Bahçe ve Sandalye,Büyükada 2015.jpg",
        ),
    ),
    # On this day, years ago: "Heute vor X Jahren" on the day the screenshots are taken.
    Folder(
        "2018/2018-10 Herbst an der Müritz",
        datetime(2018, 10, 7, 10),
        1,
        53.42,
        12.70,
        ("Sony", "ILCE-6000"),
        (
            "Off-Trail Hike (6) (37010870044).jpg",
            "Off-Trail Hike (1) (37688319042).jpg",
            "Off-Trail Hike (7) (23867343708).jpg",
            "Off-Trail Hike (4) (23867228038).jpg",
            "Off-Trail Hike (5) (23867302628).jpg",
            "Off-Trail Hike (8) (37050365153).jpg",
            "Scene swimming area Jones Lake State Park ncwetlands KG (65).jpg",
            "Mirror Lake in July 2023.jpg",
            "Ducklings-Verulamium-Park-lake-20050514-005.jpg",
            "Ducklings-Verulamium-Park-lake-20050514-004.jpg",
        ),
    ),
    Folder(
        "2019/2019-07 Zelten in Schweden",
        datetime(2019, 7, 20, 11),
        8,
        57.05,
        15.05,
        ("Apple", "iPhone XR"),
        (
            "A campfire in the mountains.jpg",
            "Campfire Cooking (Unsplash).jpg",
            "Stand by the fire (Unsplash).jpg",
            "Fire and logs at night (Unsplash).jpg",
            "Fire in the sand hole (Unsplash).jpg",
            "The Digital Marketing Collaboration 2017-05-25 (Unsplash).jpg",
            "Yellow (Unsplash wdTEHCq1mRo).jpg",
            "Best Swimming Spot in Lake Awosting.JPG",
            "Dog walker on pier, Södra Ånnabosjön.jpg",
        ),
    ),
    Folder(
        "2021/2021-04 Die Katzen ziehen ein",
        datetime(2021, 4, 10, 16),
        14,
        50.11,
        8.68,
        ("Apple", "iPhone 12"),
        (
            "A kitten in the hand (Flickr).jpg",
            "A curious kitten (Pixabay).jpg",
            "A kitten on the lawn (Pixabay).jpg",
            "A focused kitten (Pixabay).jpg",
            "Litter of kittens.jpg",
            "Tabby kitten in Brastad.jpg",
        ),
    ),
    Folder(
        "2022/2022-06 Mit Bruno am Meer",
        datetime(2022, 6, 4, 12),
        5,
        55.64,
        8.13,
        ("Apple", "iPhone 13"),
        (
            "Dog at Nørre Vorupør Strand.jpg",
            "Dog resting on the grass.jpg",
            "Two French bulldogs swimming in life jackets.jpg",
            "Dog on a beach.jpg",
            "Dog walkers in Hastings Country Park.jpg",
        ),
    ),
    Folder(
        "2024/2024-03 Willkommen, Mats",
        datetime(2024, 3, 2, 9),
        20,
        50.11,
        8.68,
        ("Apple", "iPhone 15 Pro"),
        (
            "Babies with soft books.jpg",
            "Baby wearing hat and babygrow.jpg",
            "Sleeping-baby (cropped).jpg",
            "Newborn Baby (Unsplash).jpg",
            "Baby-baby-feet-bed-325690.jpg",
        ),
    ),
)


def _open(url: str) -> bytes:
    for attempt in range(8):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})  # noqa: S310
            return urllib.request.urlopen(request, timeout=120).read()  # noqa: S310
        except urllib.error.HTTPError as error:
            if error.code != 429:
                raise
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"Commons kept refusing: {url}")


def _image_info(title: str) -> dict:
    query = {
        "action": "query",
        "format": "json",
        "titles": f"File:{title}",
        "prop": "imageinfo",
        "iiprop": "url|extmetadata",
        "iiurlwidth": WIDTH,
    }
    pages = json.loads(_open(API + urllib.parse.urlencode(query)))["query"]["pages"]
    return next(iter(pages.values()))["imageinfo"][0]


def _target_name(folder: Folder, index: int) -> str:
    """What the camera would have called it: the stock title says nothing a family would."""
    number = (folder.start.year * 37 + index * 3) % 9000 + 1000
    return f"DSC{number:05d}.JPG" if folder.camera[0] == "Sony" else f"IMG_{number:04d}.JPG"


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "data/demo/library")
    rng = random.Random(1997)  # noqa: S311
    credits = []
    for folder in FOLDERS:
        directory = root / folder.path
        directory.mkdir(parents=True, exist_ok=True)
        for index, title in enumerate(folder.files):
            target = directory / _target_name(folder, index)
            info = _image_info(title)
            licence = info.get("extmetadata", {}).get("LicenseShortName", {}).get("value", "")
            if licence not in ("CC0", "Public domain"):
                print(f"skipped, licence is {licence!r}: {title}", file=sys.stderr)
                continue
            credits.append(f"{folder.path}/{target.name}\t{licence}\t{info['descriptionurl']}")
            if target.exists():
                continue
            target.write_bytes(_open(info["thumburl"]))
            taken = folder.start + timedelta(
                days=rng.randrange(folder.days), minutes=rng.randrange(8 * 60)
            )
            lat = folder.lat + rng.uniform(-0.03, 0.03)
            lon = folder.lon + rng.uniform(-0.03, 0.03)
            stamp = taken.strftime("%Y:%m:%d %H:%M:%S")
            subprocess.run(  # noqa: S603
                [  # noqa: S607
                    "exiftool",
                    "-q",
                    "-overwrite_original",
                    "-all=",
                    f"-DateTimeOriginal={stamp}",
                    f"-CreateDate={stamp}",
                    f"-Make={folder.camera[0]}",
                    f"-Model={folder.camera[1]}",
                    f"-GPSLatitude={abs(lat)}",
                    f"-GPSLatitudeRef={'N' if lat >= 0 else 'S'}",
                    f"-GPSLongitude={abs(lon)}",
                    f"-GPSLongitudeRef={'E' if lon >= 0 else 'W'}",
                    str(target),
                ],
                check=True,
            )
            print(f"{folder.path}/{target.name}")
            time.sleep(0.5)
    (root.parent / "CREDITS.tsv").write_text("\n".join(credits) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
