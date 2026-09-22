"""Make the app icons and splash screens for iOS, Android and the browser from the raven.

Everything starts from public/muninn-mark.png, the raven without the word: a word is unreadable
at icon size. The icon is the raven on parchment, the tile the logo sits on in the app header.
The splash screens are the app's dark background with that tile in the middle - the dark blue
raven straight on the dark background would disappear.

Run it when the mark changes and commit what it writes:

    uv run --quiet --with pillow scripts/make-icons.py
"""

import pathlib

from PIL import Image, ImageDraw

APP_DIR = pathlib.Path(__file__).resolve().parent.parent
MARK = APP_DIR / "public" / "muninn-mark.png"

#: Pergament, as in the header's logo tile.
PARCHMENT = (0xED, 0xE6, 0xD6)
#: Rabenschwarz, the app's background and the splash colour in capacitor.config.ts.
RAVEN_BLACK = (0x0B, 0x0D, 0x12)

IOS = APP_DIR / "ios" / "App" / "App" / "Assets.xcassets"
ANDROID = APP_DIR / "android" / "app" / "src" / "main" / "res"

#: Launcher icons per density: the legacy square and round icon, and the adaptive foreground.
ANDROID_DENSITIES = {"mdpi": 1.0, "hdpi": 1.5, "xhdpi": 2.0, "xxhdpi": 3.0, "xxxhdpi": 4.0}


def mark() -> Image.Image:
    """The raven, cropped to what is drawn."""
    image = Image.open(MARK).convert("RGBA")
    box = image.getchannel("A").point(lambda alpha: 255 if alpha > 8 else 0).getbbox()
    assert box is not None, "the mark is empty"
    return image.crop(box)


def placed(size: int, raven: Image.Image, share: float, background: tuple[int, ...]) -> Image.Image:
    """A square of this size with the raven in the middle, its height `share` of the square."""
    canvas = Image.new("RGBA", (size, size), background)
    height = round(size * share)
    width = round(raven.width * height / raven.height)
    scaled = raven.resize((width, height), Image.Resampling.LANCZOS)
    canvas.alpha_composite(scaled, ((size - width) // 2, (size - height) // 2))
    return canvas


def rounded(image: Image.Image, radius: float) -> Image.Image:
    """The image with transparent round corners; radius as a share of its side."""
    mask = Image.new("L", image.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, image.width - 1, image.height - 1), radius=round(image.width * radius), fill=255
    )
    out = image.copy()
    out.putalpha(mask)
    return out


def circle(image: Image.Image) -> Image.Image:
    mask = Image.new("L", image.size, 0)
    ImageDraw.Draw(mask).ellipse((0, 0, image.width - 1, image.height - 1), fill=255)
    out = image.copy()
    out.putalpha(mask)
    return out


def splash(width: int, height: int, raven: Image.Image) -> Image.Image:
    """The dark background with the parchment tile in the middle."""
    canvas = Image.new("RGBA", (width, height), (*RAVEN_BLACK, 255))
    side = round(min(width, height) * 0.28)
    tile = rounded(placed(side, raven, 0.72, (*PARCHMENT, 255)), 0.22)
    canvas.alpha_composite(tile, ((width - side) // 2, (height - side) // 2))
    return canvas


def save(image: Image.Image, path: pathlib.Path, *, opaque: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    (image.convert("RGB") if opaque else image).save(path, optimize=True)
    print(f"  {path.relative_to(APP_DIR)} {image.width}x{image.height}")


def main() -> None:
    raven = mark()

    # iOS: one 1024 icon, which must not be transparent; iOS rounds the corners itself.
    save(
        placed(1024, raven, 0.74, (*PARCHMENT, 255)),
        IOS / "AppIcon.appiconset" / "AppIcon-512@2x.png",
        opaque=True,
    )
    for name in ("splash-2732x2732.png", "splash-2732x2732-1.png", "splash-2732x2732-2.png"):
        save(splash(2732, 2732, raven), IOS / "Splash.imageset" / name, opaque=True)

    # Android.
    for density, factor in ANDROID_DENSITIES.items():
        folder = ANDROID / f"mipmap-{density}"
        side = round(48 * factor)
        square = placed(side, raven, 0.74, (*PARCHMENT, 255))
        save(rounded(square, 0.18), folder / "ic_launcher.png")
        save(circle(placed(side, raven, 0.66, (*PARCHMENT, 255))), folder / "ic_launcher_round.png")
        # Adaptive: 108 dp, of which the launcher may cut away all but a 66 dp circle.
        save(
            placed(round(108 * factor), raven, 0.5, (0, 0, 0, 0)),
            folder / "ic_launcher_foreground.png",
        )
    for splash_file in sorted(ANDROID.glob("drawable*/splash.png")):
        with Image.open(splash_file) as current:
            size = current.size
        save(splash(*size, raven), splash_file, opaque=True)

    # The browser: the tab icon and the icon a phone puts on its home screen.
    public = APP_DIR / "public"
    save(rounded(placed(64, raven, 0.8, (*PARCHMENT, 255)), 0.2), public / "favicon.png")
    save(placed(180, raven, 0.74, (*PARCHMENT, 255)), public / "apple-touch-icon.png", opaque=True)


if __name__ == "__main__":
    main()
