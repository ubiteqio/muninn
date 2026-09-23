"""Cut Material Symbols Rounded down to the icons Muninn actually uses.

The full variable font is 5 MB, which is not something to ship to a phone. Subsetting by ligature
name alone does not help much: the layout closure drags in every icon whose name happens to be
spelled with the same letters. So this resolves each icon name to its glyph, keeps exactly those
glyphs plus the letters their names are spelled with, and turns the closure off. What survives in
the ligature table is precisely our icons, and the component can keep writing the icon name.

Run it whenever ICONS changes and commit the generated font:

    uv run --quiet --with "fonttools[woff]" scripts/subset-icons.py
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

from fontTools.ttLib import TTFont

#: Every icon used in the app. Keep it sorted.
ICONS = [
    "add_photo_alternate",
    "arrow_back",
    "arrow_upward",
    "auto_awesome",
    "bar_chart",
    "block",
    "chat_bubble",
    "check_circle",
    "chevron_left",
    "chevron_right",
    "close",
    "content_copy",
    "contrast",
    "create_new_folder",
    "dark_mode",
    "delete",
    "download",
    "edit",
    "error",
    "expand_more",
    "favorite",
    "folder",
    "group",
    "history",
    "home",
    "image_search",
    "info",
    "ios_share",
    "light_mode",
    "lock_reset",
    "logout",
    "map",
    "more_horiz",
    "notifications",
    "pause",
    "person",
    "person_add",
    "person_search",
    "photo_library",
    "play_arrow",
    "question_mark",
    "search",
    "shield_person",
    "star",
    "sync",
    "tune",
    "visibility_off",
    "volume_off",
    "volume_up",
    "warning",
]

APP_DIR = pathlib.Path(__file__).resolve().parent.parent
SOURCE = APP_DIR / "node_modules/material-symbols/material-symbols-rounded.woff2"
FONT_TARGET = APP_DIR / "src/assets/fonts/material-symbols-rounded-subset.woff2"


def resolve_glyphs(font: TTFont) -> dict[str, str]:
    """Map icon name -> glyph name, by walking the ligature substitutions.

    The components are glyph names, not characters ("underscore", not "_"), so they are
    translated back through the character map first.
    """
    gsub = font["GSUB"].table
    glyph_order = set(font.getGlyphOrder())
    character_of = {glyph: chr(code) for code, glyph in font.getBestCmap().items()}
    found: dict[str, str] = {}

    for lookup in gsub.LookupList.Lookup:
        for subtable in lookup.SubTable:
            # Lookup type 7 wraps the real subtable, which is where the ligatures live.
            subtable = getattr(subtable, "ExtSubTable", subtable)
            ligatures = getattr(subtable, "ligatures", None)
            if not ligatures:
                continue
            for first, entries in ligatures.items():
                for entry in entries:
                    parts = [character_of.get(first), *(character_of.get(c) for c in entry.Component)]
                    if any(part is None for part in parts):
                        continue
                    name = "".join(part for part in parts if part is not None)
                    if name in ICONS and entry.LigGlyph in glyph_order:
                        found[name] = entry.LigGlyph

    return found


def main() -> int:
    if not SOURCE.exists():
        print(f"Run pnpm install first: {SOURCE} is missing", file=sys.stderr)
        return 1

    font = TTFont(SOURCE)
    glyphs = resolve_glyphs(font)

    missing = sorted(set(ICONS) - set(glyphs))
    if missing:
        print(f"No glyph found for: {', '.join(missing)}", file=sys.stderr)
        return 1

    letters = "".join(sorted(set("".join(ICONS))))

    subprocess.run(
        [
            "pyftsubset",
            str(SOURCE),
            f"--output-file={FONT_TARGET}",
            "--flavor=woff2",
            # The icon glyphs themselves, plus the letters their ligatures are spelled with.
            "--glyphs=" + ",".join(sorted(glyphs.values())),
            f"--text={letters}",
            "--layout-features+=liga,dlig,calt,rlig",
            # Without this the closure pulls in every icon spelled with the same letters.
            "--no-layout-closure",
            "--notdef-outline",
        ],
        check=True,
    )

    size = FONT_TARGET.stat().st_size / 1024
    print(f"Wrote {FONT_TARGET.name} ({size:.1f} kB) with {len(glyphs)} icons")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
