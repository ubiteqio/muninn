"""What Muninn expects of a machine, and what it gets back."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol

from muninn.ai.analysis import Analysis


class AiError(Exception):
    """The machine could not be reached, refused, or answered with something unusable.

    Carries a sentence an admin can act on, because that sentence ends up on their screen.
    """


class AiUnreachableError(AiError):
    """Nobody answered at all: the machine is off, or its service not running. Unlike a bad
    answer about one picture, this says nothing about the medium and everything about the
    machine - asking with the next medium is pointless."""


@dataclass(frozen=True, slots=True)
class Check:
    """What came of asking a machine whether it is there."""

    ok: bool
    #: One sentence for the admin area: the model that answered, or what went wrong.
    detail: str
    milliseconds: int
    #: How long the vectors are. Only an embedder knows this, and only when it answered.
    dimensions: int | None = None


class Embedder(Protocol):
    """Turns pictures or words into vectors of the same space.

    One embedder serves one model: the picture model and the word model are two profiles, even
    when the same container answers both.
    """

    async def embed(self, inputs: Sequence[str]) -> list[list[float]]:
        """Vectors for these inputs, in the order they came in.

        A picture is passed as a data URL, a text as itself - the way the OpenAI embeddings API
        spells both.
        """
        ...

    async def check(self) -> Check:
        """Ask the machine one small question, to see whether it is there at all."""
        ...


class Analyzer(Protocol):
    """Looks at pictures and fills in the form stage 5 needs."""

    async def analyze(self, images: Sequence[str], *, context: str = "") -> Analysis:
        """What can be seen in these pictures, in German.

        A picture is passed as a data URL. The context - album, date - is a hint for the model,
        not something to describe.
        """
        ...

    async def summarize(
        self,
        moments: Sequence[tuple[int, str]],
        *,
        context: str = "",
        spoken: Sequence[tuple[float, str]] = (),
    ) -> str:
        """One or two sentences about a whole video, from what was seen second by second and,
        when anything is said in it, from what was heard."""
        ...


@dataclass(frozen=True, slots=True)
class SpokenPart:
    """One stretch of speech: from when to when, and what was said."""

    start: float
    end: float
    text: str


@dataclass(frozen=True, slots=True)
class Transcript:
    """What was heard in a recording. No parts at all means nobody spoke."""

    language: str = ""
    parts: list[SpokenPart] = field(default_factory=list)

    @property
    def text(self) -> str:
        return " ".join(part.text for part in self.parts).strip()


class Transcriber(Protocol):
    """Listens to a recording and writes down what is said, with the time of each part."""

    async def transcribe(self, wav: bytes) -> Transcript:
        """A 16 kHz mono WAV in, the spoken parts out, in order."""
        ...


@dataclass(frozen=True, slots=True)
class DetectedFace:
    """One face in a picture."""

    #: Left, top, right, bottom as fractions of the picture's width and height (0 to 1).
    box: tuple[float, float, float, float]
    #: How sure the detector is that this is a face.
    score: float
    #: Its vector: close to those of the same person, far from everybody else's.
    embedding: list[float]
    #: Its size in pixels of the picture as it was sent: small faces say little.
    pixels: int
    #: The picture's width divided by its height, to turn the box into a square.
    aspect: float = 1.0


class FaceDetector(Protocol):
    """Finds the faces in pictures, and a vector for each."""

    async def detect(self, images: Sequence[str]) -> list[list[DetectedFace]]:
        """Pictures as data URLs in, the faces of each out, in the same order."""
        ...

    async def check(self) -> Check:
        """Whether the model is there and answers."""
        ...
