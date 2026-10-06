"""Turn listing.md and the screenshots into the folders fastlane deliver reads.

    python3 app/store/export_fastlane.py [target]   # default: data/demo/appstore

listing.md stays the one place the texts are written. The name is left out: App Store Connect
keeps the one chosen when the app was created. So is "what's new", which a first version may
not have.
"""

import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).parent
SHOTS = Path("data/demo/shots")
LOCALES = {"de": "de-DE", "en": "en-US"}
FIELDS = {
    "subtitle": "subtitle.txt",
    "promo": "promotional_text.txt",
    "description": "description.txt",
    "keywords": "keywords.txt",
}
URLS = {
    "privacy_url.txt": "https://github.com/ubiteqio/muninn/blob/dev/PRIVACY.md",
    "support_url.txt": "https://github.com/ubiteqio/muninn/issues",
    "marketing_url.txt": "https://github.com/ubiteqio/muninn",
}
APP = {
    "copyright.txt": "2026 UBITEQ.io and Boris Azar",
    "primary_category.txt": "PHOTO_AND_VIDEO",
    "secondary_category.txt": "LIFESTYLE",
}
FIELD = re.compile(r"<!-- field: (\w+)\.(\w+) -->\n```\n(.*?)\n```", re.S)


def main() -> int:
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "data/demo/appstore")
    if target.exists():
        shutil.rmtree(target)
    metadata = target / "metadata"
    metadata.mkdir(parents=True)
    for name, value in APP.items():
        (metadata / name).write_text(value + "\n")

    fields = {
        (lang, field): value
        for lang, field, value in FIELD.findall((HERE / "listing.md").read_text())
    }
    for lang, locale in LOCALES.items():
        folder = metadata / locale
        folder.mkdir()
        for field, name in FIELDS.items():
            (folder / name).write_text(fields[(lang, field)] + "\n")
        for name, value in URLS.items():
            (folder / name).write_text(value + "\n")

        shots = target / "screenshots" / locale
        shots.mkdir(parents=True)
        for png in sorted((SHOTS / lang).glob("*.png")):
            shutil.copy(png, shots / png.name)
        print(f"{locale}: {len(FIELDS)} texts, {len(list(shots.iterdir()))} screenshots")
    return 0


if __name__ == "__main__":
    sys.exit(main())
