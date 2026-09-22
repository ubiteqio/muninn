"""Speech in a video's sound, as text with its times: Whisper large-v3-turbo.

It runs on the same Torch as the two vector models, so the card holds one CUDA stack, not two.
Whisper has a known weakness with home videos: given silence, music or children playing, it
likes to invent a sentence. Three things keep that down - quiet stretches are not handed to it at
all, its own "this is not speech" judgement is trusted, and a segment it was unsure of is tried
again at a higher temperature or dropped.
"""

import io
import logging
import wave
from dataclasses import dataclass
from typing import Any, Protocol

import numpy as np

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16_000
#: Whisper looks at 30 seconds at a time; longer sound is read segment by segment.
WINDOW_SECONDS = 30

#: Below this loudness (root mean square of the samples, 0 to 1) a whole recording counts as
#: silent and is not transcribed. Room noise sits around 0.001, a voice across a room at 0.01.
SILENCE_RMS = 0.003


class UnusableAudioError(Exception):
    """The caller sent something that is not a WAV this service can read."""


@dataclass(frozen=True, slots=True)
class Segment:
    start: float
    end: float
    text: str


@dataclass(frozen=True, slots=True)
class Transcript:
    language: str
    duration: float
    segments: list[Segment]

    @property
    def text(self) -> str:
        return " ".join(segment.text for segment in self.segments).strip()


class Transcriber(Protocol):
    def transcribe(self, audio: bytes, language: str | None = None) -> Transcript: ...


def decode_wav(data: bytes) -> np.ndarray:
    """A 16-bit PCM WAV as mono float samples at 16 kHz, which is what Whisper reads."""
    try:
        with wave.open(io.BytesIO(data)) as reader:
            channels = reader.getnchannels()
            width = reader.getsampwidth()
            rate = reader.getframerate()
            frames = reader.readframes(reader.getnframes())
    except (wave.Error, EOFError) as error:
        raise UnusableAudioError("The sound has to arrive as a WAV file.") from error

    if width != 2:
        raise UnusableAudioError("The WAV has to hold 16-bit samples.")

    samples = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    if rate != SAMPLE_RATE and samples.size:
        # Linear resampling: good enough for speech, and the caller normally sends 16 kHz.
        target = round(samples.size * SAMPLE_RATE / rate)
        samples = np.interp(
            np.linspace(0, samples.size - 1, target), np.arange(samples.size), samples
        ).astype(np.float32)
    return samples


def is_silent(samples: np.ndarray) -> bool:
    """Whether nothing in the recording is loud enough to be somebody speaking."""
    if samples.size == 0:
        return True
    # The loudest second decides: one sentence in a long quiet video still counts.
    seconds = samples[: samples.size - samples.size % SAMPLE_RATE].reshape(-1, SAMPLE_RATE)
    if seconds.size == 0:
        seconds = samples.reshape(1, -1)
    loudest = float(np.sqrt((seconds**2).mean(axis=1)).max())
    return loudest < SILENCE_RMS


class WhisperTranscriber:
    """Whisper through transformers, with its long-form decoding and its own safeguards."""

    def __init__(self, model: Any, processor: Any, device: str, dtype: Any) -> None:
        self._model = model
        self._processor = processor
        self._device = device
        self._dtype = dtype

    def transcribe(self, audio: bytes, language: str | None = None) -> Transcript:
        samples = decode_wav(audio)
        duration = samples.size / SAMPLE_RATE
        if is_silent(samples):
            return Transcript(language=language or "", duration=duration, segments=[])

        long_form = duration > WINDOW_SECONDS
        features = self._processor(
            samples,
            sampling_rate=SAMPLE_RATE,
            return_tensors="pt",
            # Long sound is read in one go by the long-form decoder; short sound is padded.
            truncation=not long_form,
            padding="longest" if long_form else "max_length",
            return_attention_mask=True,
        )
        inputs = features.input_features.to(self._device, dtype=self._dtype)
        mask = features.attention_mask.to(self._device)

        spoken = language or self._language_of(inputs)

        import torch

        with torch.inference_mode():
            output = self._model.generate(
                inputs,
                attention_mask=mask,
                language=spoken or None,
                task="transcribe",
                return_timestamps=True,
                return_segments=True,
                # Each 30-second window stands on its own: carrying text over is what lets a
                # single invented sentence repeat itself to the end of a video.
                condition_on_prev_tokens=False,
                # OpenAI's own safeguards: a window that looks like no speech is skipped, one
                # decoded with low confidence or in a loop is tried again, warmer.
                temperature=(0.0, 0.2, 0.4, 0.6, 0.8, 1.0),
                no_speech_threshold=0.6,
                logprob_threshold=-1.0,
                compression_ratio_threshold=1.35,
            )

        return Transcript(
            language=spoken or "",
            duration=duration,
            segments=self._segments_of(output, duration),
        )

    def _language_of(self, inputs: Any) -> str:
        """The language of the first 30 seconds, as Whisper's code for it, e.g. "de"."""
        import torch

        with torch.inference_mode():
            tokens = self._model.detect_language(inputs[:, :, :3000])
        code: str = self._processor.tokenizer.decode(tokens[0]).strip("<|>")
        return code

    def _segments_of(self, output: Any, duration: float) -> list[Segment]:
        found = output["segments"][0] if isinstance(output, dict) else []
        segments: list[Segment] = []
        for segment in found:
            text = self._processor.tokenizer.decode(segment["tokens"], skip_special_tokens=True)
            text = " ".join(text.split())
            if not text:
                continue
            start = float(segment["start"])
            end = min(float(segment["end"]), duration)
            segments.append(
                Segment(start=round(start, 2), end=round(max(end, start), 2), text=text)
            )
        return segments


def load_whisper(model_id: str, device: str, dtype_name: str) -> WhisperTranscriber:
    from transformers import AutoProcessor, WhisperForConditionalGeneration

    from embed.encoders import pick_dtype

    dtype = pick_dtype(dtype_name, device)
    logger.info("Loading %s on %s as %s", model_id, device, dtype)
    loaded: Any = WhisperForConditionalGeneration.from_pretrained(
        model_id, dtype=dtype, attn_implementation="sdpa"
    )
    model = loaded.to(device).eval()
    processor: Any = AutoProcessor.from_pretrained(model_id)  # type: ignore[no-untyped-call]
    return WhisperTranscriber(model, processor, device, dtype)
