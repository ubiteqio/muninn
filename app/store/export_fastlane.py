"""Turn listing.md and the screenshots into the folders fastlane deliver reads.

    python3 app/store/export_fastlane.py [target] [language ...]
    # default: data/demo/appstore, every language

listing.md stays the one place the texts are written. "What's new" is left out: a first version
may not have it. Naming languages exports only those, so deliver touches only those; whatever
else is in the target is left alone, a Fastfile included.
"""

import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).parent
SHOTS = Path("data/demo/shots")
LOCALES = {"de": "de-DE", "en": "en-US"}
FIELDS = {
    "name": "name.txt",
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
    languages = sys.argv[2:] or list(LOCALES)
    metadata = target / "metadata"
    screenshots = target / "screenshots"
    # Only the export's own folders are replaced.
    for folder in (metadata, screenshots):
        if folder.exists():
            shutil.rmtree(folder)
    metadata.mkdir(parents=True)
    for name, value in APP.items():
        (metadata / name).write_text(value + "\n")

    fields = {
        (lang, field): value
        for lang, field, value in FIELD.findall((HERE / "listing.md").read_text())
    }
    for lang in languages:
        locale = LOCALES[lang]
        folder = metadata / locale
        folder.mkdir()
        for field, name in FIELDS.items():
            (folder / name).write_text(fields[(lang, field)] + "\n")
        for name, value in URLS.items():
            (folder / name).write_text(value + "\n")

        shots = screenshots / locale
        shots.mkdir(parents=True)
        for png in sorted((SHOTS / lang).glob("*.png")):
            shutil.copy(png, shots / png.name)
        print(f"{locale}: {len(FIELDS)} texts, {len(list(shots.iterdir()))} screenshots")
    return 0


if __name__ == "__main__":
    sys.exit(main())
