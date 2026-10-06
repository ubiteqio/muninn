"""Count every field in listing.md against Apple's limit for it.

python3 app/store/check_listing.py
"""

import re
import sys
from pathlib import Path

LIMITS = {
    "name": 30,
    "subtitle": 30,
    "promo": 170,
    "description": 4000,
    "keywords": 100,
    "whatsnew": 4000,
    "notes": 4000,
    # Google Play
    "title": 30,
    "short": 80,
}

FIELD = re.compile(r"<!-- field: (\w+)\.(\w+) -->\n```\n(.*?)\n```", re.S)


def main() -> int:
    name = sys.argv[1] if len(sys.argv) > 1 else "listing.md"
    text = (Path(__file__).parent / name).read_text()
    failed = False
    for language, field, value in FIELD.findall(text):
        limit = LIMITS[field]
        length = len(value)
        mark = "ok" if length <= limit else "TOO LONG"
        failed |= length > limit
        print(f"{language}.{field:<12} {length:>5} / {limit:<5} {mark}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
