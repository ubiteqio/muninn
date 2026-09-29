"""A video, one frame every few seconds, straight from ffmpeg into memory - and which of them to
look at.

Nothing is written to disk: ffmpeg decodes the 720p preview and writes JPEGs into a pipe, and the
frames are cut apart where one JPEG ends and the next begins. Most moments of a family video look
like the one before, so a frame is only worth a question to the model when it differs enough
from the last one that was asked about.
"""

import asyncio
import base64
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

import pyvips

#: The longest edge a frame is decoded at: plenty for a caption, cheap for the model.
FRAME_EDGE = 768

#: How different two frames must be to count as a change, as the mean difference of their grey
#: 32x32 versions on a scale of 0 to 255. As many frames as possible are looked at; only the
#: seconds in which the picture stands still are skipped. Measured on twelve videos from the
#: library, even a calm handheld shot moves by about 6 from one second to the next, so below
#: that is noise and compression, not something new. About 93 % of all seconds go through.
CHANGE_THRESHOLD = 6.0

#: The description looks at one frame every this many seconds - and of those only at the ones
#: that changed. A picture that stands still is described once, however long it stands.
DESCRIBE_EVERY_SECONDS = 5

_SIGNATURE_EDGE = 32
_START = b"\xff\xd8"
_END = b"\xff\xd9"
_READ_SIZE = 1 << 16

#: How long ffmpeg may say nothing at all before the video counts as unreadable. This is a
#: watchdog, not a budget for the whole video: the caller describes every frame it is handed,
#: and a long video may rightly take hours. Only silence from the decoder is a fault.
STALL_SECONDS = 120


@dataclass(frozen=True, slots=True)
class Frame:
    second: int
    jpeg: bytes

    def data_url(self) -> str:
        return f"data:image/jpeg;base64,{base64.b64encode(self.jpeg).decode('ascii')}"


def split_jpegs(buffer: bytes) -> tuple[list[bytes], bytes]:
    """The complete JPEGs at the start of a buffer, and what is left of the next one.

    ffmpeg's JPEGs carry no embedded thumbnail, and inside the compressed data a 0xFF is always
    followed by 0x00, so the end marker cannot turn up in the middle of a picture.
    """
    pictures: list[bytes] = []
    position = 0
    while True:
        start = buffer.find(_START, position)
        if start < 0:
            return pictures, b""
        end = buffer.find(_END, start + 2)
        if end < 0:
            return pictures, buffer[start:]
        pictures.append(buffer[start : end + 2])
        position = end + 2


async def frames_of(
    video: Path, *, every: int = 1, stall_seconds: int = STALL_SECONDS
) -> AsyncIterator[Frame]:
    """One frame every ``every`` seconds of the video, in order, as JPEGs."""
    process = await asyncio.create_subprocess_exec(
        "ffmpeg",
        "-nostdin",
        "-v",
        "error",
        "-i",
        str(video),
        "-vf",
        f"fps=1,scale='min({FRAME_EDGE},iw)':'min({FRAME_EDGE},ih)':force_original_aspect_ratio=decrease",
        "-f",
        "image2pipe",
        "-c:v",
        "mjpeg",
        "-q:v",
        "4",
        "-",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    if process.stdout is None:
        raise FrameError("ffmpeg started without a pipe to read from.")

    second = 0
    rest = b""
    try:
        while True:
            # Each read has its own watchdog. A budget around the whole loop would also count
            # the time the caller spends on every frame it is handed - a model answering about
            # an hour of video - and would end a good video halfway through.
            try:
                async with asyncio.timeout(stall_seconds):
                    chunk = await process.stdout.read(_READ_SIZE)
            except TimeoutError as error:
                raise FrameError(
                    f"ffmpeg said nothing about {video.name} for {stall_seconds} seconds."
                ) from error
            if not chunk:
                break
            pictures, rest = split_jpegs(rest + chunk)
            for picture in pictures:
                # ffmpeg's own "one every five seconds" rounds and may drop the end; one a
                # second is exact, and passing on every fifth of them costs next to nothing.
                if second % every == 0:
                    yield Frame(second=second, jpeg=picture)
                second += 1
        await process.wait()
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()

    if process.returncode != 0 and second == 0:
        problem = (await process.stderr.read()).decode(errors="replace") if process.stderr else ""
        raise FrameError(f"ffmpeg could not read {video.name}: {problem.strip()[:200]}")


class FrameError(Exception):
    """The video could not be read at all."""


def signature(jpeg: bytes) -> bytes:
    """A frame reduced to what the change check needs: 32x32 grey values."""
    image = pyvips.Image.thumbnail_buffer(
        jpeg, _SIGNATURE_EDGE, height=_SIGNATURE_EDGE, size=pyvips.enums.Size.FORCE
    ).colourspace(pyvips.enums.Interpretation.B_W)
    if image.bands > 1:
        image = image[0]
    # pyvips hands back a memoryview whose items are one-byte strings; bytes gives numbers.
    return bytes(image.cast(pyvips.enums.BandFormat.UCHAR).write_to_memory())


def difference(first: bytes, second: bytes) -> float:
    """The mean difference of two signatures, from 0 (the same) to 255."""
    if len(first) != len(second) or not first:
        return 255.0
    return sum(abs(a - b) for a, b in zip(first, second, strict=True)) / len(first)


class ChangeFilter:
    """Lets a frame through when it shows something new - the first one always - and, when a
    ``max_gap_seconds`` is given, when it has been quiet that long."""

    def __init__(
        self, *, threshold: float = CHANGE_THRESHOLD, max_gap_seconds: int | None = None
    ) -> None:
        self._threshold = threshold
        self._max_gap = max_gap_seconds
        self._last: bytes | None = None
        self._last_second = 0

    def wants(self, frame: Frame) -> bool:
        current = signature(frame.jpeg)
        due = (
            self._last is None
            or (self._max_gap is not None and frame.second - self._last_second >= self._max_gap)
            or difference(self._last, current) >= self._threshold
        )
        if due:
            self._last = current
            self._last_second = frame.second
        return due
