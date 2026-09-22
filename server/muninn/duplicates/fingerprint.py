"""A picture's fingerprint: 64 bits that stay the same when it is shrunk or compressed again.

The perceptual hash: the picture is shrunk to 32 by 32 grey pixels and turned into its
frequencies (a discrete cosine transform, as JPEG does). The 64 lowest frequencies describe its
rough shape; each bit says whether one of them lies above their median. A copy that went through
WhatsApp - smaller, more compressed, without metadata - keeps nearly every bit, a different
picture about half. Measured on thumbnails of the library: shrunk to 40 % and saved at JPEG
quality 35, copies differed in 0.8 bits on average.

Read from the thumbnail Muninn made anyway, never from the original. Plain Python: the transform
needs only the 64 low frequencies, a few milliseconds per picture.
"""

import math
from pathlib import Path

import pyvips

SIZE = 32
LOW = 8

_COSINES = [
    [math.cos((2 * x + 1) * u * math.pi / (2 * SIZE)) for x in range(SIZE)] for u in range(LOW)
]


def fingerprint(path: Path) -> int:
    image = pyvips.Image.thumbnail(str(path), SIZE, height=SIZE, size="force")
    if image.hasalpha():
        image = image.flatten(background=[255, 255, 255])
    grey = image.colourspace("b-w").extract_band(0).cast("uchar")
    return of_pixels(bytes(grey.write_to_memory()))


def of_pixels(pixels: bytes) -> int:
    """The bits of 32 by 32 grey pixels, row by row."""
    # The transform is separable: along the rows first, then down the columns.
    rows = [
        [sum(pixels[y * SIZE + x] * _COSINES[u][x] for x in range(SIZE)) for u in range(LOW)]
        for y in range(SIZE)
    ]
    frequencies = [
        sum(rows[y][u] * _COSINES[v][y] for y in range(SIZE))
        for v in range(LOW)
        for u in range(LOW)
    ]
    # The first is the average brightness, far above all others; it would skew the median.
    ordered = sorted(frequencies[1:])
    median = ordered[len(ordered) // 2]
    bits = 0
    for value in frequencies:
        bits = (bits << 1) | (1 if value > median else 0)
    return bits


def distance(first: int, second: int) -> int:
    """How many of the 64 bits differ."""
    return (first ^ second).bit_count()


def as_signed(bits: int) -> int:
    """PostgreSQL's bigint is signed; the 64 bits are stored as they are."""
    return bits - (1 << 64) if bits >= 1 << 63 else bits


def as_unsigned(value: int) -> int:
    return value + (1 << 64) if value < 0 else value
