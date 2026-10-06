"""The two models, and the one thing they are asked: turn this into a vector.

SigLIP 2 puts pictures and sentences into the same space, which is what makes "Hund am Strand"
find a photo nobody ever described. BGE-M3 turns a description into a vector of meaning. Both
are loaded once and asked many times.
"""

import base64
import binascii
import io
import logging
from dataclasses import dataclass
from typing import Any, Protocol

from PIL import Image

logger = logging.getLogger(__name__)

#: What an image looks like when it arrives: a data URL, as the OpenAI API spells one.
DATA_URL = "data:"


class UnusableInputError(Exception):
    """The caller sent something that is not a picture and not a sentence."""


class Encoder(Protocol):
    """One model, asked for vectors."""

    @property
    def dimensions(self) -> int: ...

    def encode(self, inputs: list[str]) -> list[list[float]]: ...


@dataclass(frozen=True, slots=True)
class Loaded:
    """A model and everything that belongs to it, kept together."""

    model: Any
    processor: Any
    device: str


def pick_dtype(wanted: str, device: str) -> Any:
    """Half precision on a card, full precision on a processor.

    The card is shared with the describing model, and every gigabyte these two do not take is a
    gigabyte it can use. On a processor half precision would only be slower.
    """
    import torch

    named = {"float16": torch.float16, "bfloat16": torch.bfloat16, "float32": torch.float32}
    if wanted in named:
        return named[wanted]

    return torch.float16 if device == "cuda" else torch.float32


def pick_device(wanted: str) -> str:
    """Where to run. "auto" takes the card if there is one, which is the only sensible default."""
    import torch

    if wanted != "auto":
        return wanted
    if torch.cuda.is_available():
        return "cuda"
    # Apple's GPU, for a laptop that has to answer at all rather than quickly.
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def decode_image(value: str) -> Image.Image:
    """A data URL as a picture. Anything else is the caller's mistake, and is said so."""
    if not value.startswith(DATA_URL):
        raise UnusableInputError("A picture has to arrive as a data URL.")

    try:
        _, encoded = value.split(",", 1)
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as error:
        raise UnusableInputError("The data URL is not valid base64.") from error

    try:
        image = Image.open(io.BytesIO(raw))
        image.load()
    except OSError as error:
        raise UnusableInputError("Those bytes are not a picture this service can read.") from error

    return image.convert("RGB")


def is_image(value: str) -> bool:
    return value.startswith(DATA_URL)


class SiglipEncoder:
    """Pictures and words in one space."""

    def __init__(self, loaded: Loaded) -> None:
        self._loaded = loaded

    @property
    def dimensions(self) -> int:
        size: int = self._loaded.model.config.text_config.hidden_size
        return size

    def encode(self, inputs: list[str]) -> list[list[float]]:
        """Pictures through the picture tower, words through the word tower, in one answer.

        Both are normalised, so a dot product is the cosine and the database can compare them
        the way the search expects.
        """
        import torch

        vectors: list[list[float]] = [[] for _ in inputs]
        pictures = [index for index, value in enumerate(inputs) if is_image(value)]
        words = [index for index, value in enumerate(inputs) if not is_image(value)]

        with torch.inference_mode():
            if pictures:
                images = [decode_image(inputs[index]) for index in pictures]
                batch = self._loaded.processor(images=images, return_tensors="pt")
                batch = {key: value.to(self._loaded.device) for key, value in batch.items()}
                features = _pooled(self._loaded.model.get_image_features(**batch))
                for slot, index in enumerate(pictures):
                    vectors[index] = _normalise(features[slot])

            if words:
                batch = self._loaded.processor(
                    text=[inputs[index] for index in words],
                    # SigLIP 2 was trained on exactly 64 text tokens, padded; say so explicitly.
                    padding="max_length",
                    max_length=64,
                    truncation=True,
                    return_tensors="pt",
                )
                batch = {key: value.to(self._loaded.device) for key, value in batch.items()}
                features = _pooled(self._loaded.model.get_text_features(**batch))
                for slot, index in enumerate(words):
                    vectors[index] = _normalise(features[slot])

        return vectors


class BgeEncoder:
    """Descriptions as vectors of meaning. Words only; a picture here is a mistake."""

    def __init__(self, loaded: Loaded) -> None:
        self._loaded = loaded

    @property
    def dimensions(self) -> int:
        size: int = self._loaded.model.config.hidden_size
        return size

    def encode(self, inputs: list[str]) -> list[list[float]]:
        import torch

        if any(is_image(value) for value in inputs):
            raise UnusableInputError("This model reads words, not pictures.")

        batch = self._loaded.processor(
            inputs, padding=True, truncation=True, max_length=512, return_tensors="pt"
        )
        batch = {key: value.to(self._loaded.device) for key, value in batch.items()}

        with torch.inference_mode():
            output = self._loaded.model(**batch)

        # BGE-M3 uses the first token as the sentence, the way its own examples do.
        return [_normalise(row) for row in output.last_hidden_state[:, 0]]


def _pooled(output: Any) -> Any:
    """One vector per input, whatever transformers wraps it in.

    transformers 4.x returned the pooled tensor from get_image_features/get_text_features;
    5.x returns a BaseModelOutputWithPooling. Indexing that yields the per-token hidden states,
    which is what made every siglip2 request fail with "only one element tensors can be
    converted to Python scalars".
    """
    import torch

    if isinstance(output, torch.Tensor):
        return output
    pooled = getattr(output, "pooler_output", None)
    if pooled is None:
        raise RuntimeError(f"No pooled output in {type(output).__name__}")
    return pooled


def _normalise(vector: Any) -> list[float]:
    import torch

    normalised = torch.nn.functional.normalize(vector, p=2, dim=-1)
    return [float(value) for value in normalised.detach().float().cpu()]


def load_siglip(model_id: str, device: str, dtype: str = "auto") -> SiglipEncoder:
    from transformers import AutoModel, AutoProcessor

    logger.info("Loading %s on %s (%s)", model_id, device, dtype)
    model = AutoModel.from_pretrained(model_id, dtype=pick_dtype(dtype, device)).to(device).eval()
    # transformers ships no types for its loaders; the objects they return are used through
    # narrow calls only, so this is where the untyped world ends.
    processor: Any = AutoProcessor.from_pretrained(model_id)  # type: ignore[no-untyped-call]
    return SiglipEncoder(Loaded(model=model, processor=processor, device=device))


def load_bge(model_id: str, device: str, dtype: str = "auto") -> BgeEncoder:
    from transformers import AutoModel, AutoTokenizer

    logger.info("Loading %s on %s (%s)", model_id, device, dtype)
    model = AutoModel.from_pretrained(model_id, dtype=pick_dtype(dtype, device)).to(device).eval()
    tokenizer = AutoTokenizer.from_pretrained(model_id)
    return BgeEncoder(Loaded(model=model, processor=tokenizer, device=device))
