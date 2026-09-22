"""The service, tested without loading two gigabytes of weights."""

import asyncio
import base64
import io
import struct
from dataclasses import dataclass

import numpy as np
import pytest
import torch
from fastapi.testclient import TestClient
from PIL import Image

from embed.config import Settings
from embed.encoders import UnusableInputError, _pooled, decode_image, is_image
from embed.main import create_app
from embed.transcriber import Transcript


class CountingEncoder:
    """Stands in for a model: says how long its vectors are and what it was asked."""

    def __init__(self, dimensions: int = 8) -> None:
        self._dimensions = dimensions
        self.seen: list[list[str]] = []

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def encode(self, inputs: list[str]) -> list[list[float]]:
        self.seen.append(list(inputs))
        return [[float(index)] * self._dimensions for index, _ in enumerate(inputs)]


def a_picture() -> str:
    image = Image.new("RGB", (8, 8), (200, 40, 90))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


@pytest.fixture
def encoder() -> CountingEncoder:
    return CountingEncoder()


@pytest.fixture
def client(encoder: CountingEncoder) -> TestClient:
    settings = Settings(image_model_name="siglip2", text_model_name="bge-m3", lazy=True)
    return TestClient(create_app(settings, encoders={"siglip2": encoder, "bge-m3": encoder}))


def test_it_answers_the_way_the_openai_api_does(client: TestClient) -> None:
    response = client.post("/v1/embeddings", json={"model": "siglip2", "input": ["ein Hund"]})

    body = response.json()
    assert response.status_code == 200
    assert body["object"] == "list"
    assert body["model"] == "siglip2"
    assert body["data"][0]["index"] == 0
    assert len(body["data"][0]["embedding"]) == 8


def test_one_input_may_be_a_bare_string(client: TestClient) -> None:
    response = client.post("/v1/embeddings", json={"model": "siglip2", "input": "ein Hund"})

    assert len(response.json()["data"]) == 1


def test_pictures_and_words_go_to_the_same_model(
    client: TestClient, encoder: CountingEncoder
) -> None:
    """That is the point of SigLIP: a sentence and a photo end up in one space."""
    picture = a_picture()

    client.post("/v1/embeddings", json={"model": "siglip2", "input": [picture, "ein Hund"]})

    assert encoder.seen == [[picture, "ein Hund"]]


def test_a_model_this_service_does_not_serve(client: TestClient) -> None:
    response = client.post("/v1/embeddings", json={"model": "gpt-4", "input": ["x"]})

    assert response.status_code == 404
    assert "siglip2" in response.json()["detail"]


def test_a_batch_that_is_too_large_is_refused_rather_than_attempted(
    encoder: CountingEncoder,
) -> None:
    """A card that runs out of memory takes every other request with it."""
    settings = Settings(max_batch=2, lazy=True)
    client = TestClient(create_app(settings, encoders={"siglip2": encoder, "bge-m3": encoder}))

    response = client.post("/v1/embeddings", json={"model": "siglip2", "input": ["a", "b", "c"]})

    assert response.status_code == 413
    assert encoder.seen == []


def test_nothing_to_embed_costs_no_model(client: TestClient, encoder: CountingEncoder) -> None:
    response = client.post("/v1/embeddings", json={"model": "siglip2", "input": []})

    assert response.json()["data"] == []
    assert encoder.seen == []


def test_it_says_what_it_serves(client: TestClient) -> None:
    body = client.get("/v1/models").json()

    assert {card["id"] for card in body["data"]} == {
        "siglip2",
        "bge-m3",
        "whisper-large-v3-turbo",
        "buffalo_l",
    }


def test_a_key_closes_the_door(encoder: CountingEncoder) -> None:
    settings = Settings(api_key="geheim", lazy=True)
    client = TestClient(create_app(settings, encoders={"siglip2": encoder, "bge-m3": encoder}))

    refused = client.post("/v1/embeddings", json={"model": "siglip2", "input": ["x"]})
    allowed = client.post(
        "/v1/embeddings",
        json={"model": "siglip2", "input": ["x"]},
        headers={"Authorization": "Bearer geheim"},
    )

    assert refused.status_code == 401
    assert allowed.status_code == 200


def test_health_needs_no_key(encoder: CountingEncoder) -> None:
    settings = Settings(api_key="geheim", lazy=True)
    client = TestClient(create_app(settings, encoders={"siglip2": encoder, "bge-m3": encoder}))

    assert client.get("/health").json() == {"status": "ok"}


class TestReadingWhatArrives:
    def test_a_data_url_is_a_picture(self) -> None:
        assert is_image(a_picture()) is True
        assert is_image("ein Hund am Strand") is False

    def test_a_picture_comes_back_as_pixels(self) -> None:
        image = decode_image(a_picture())

        assert image.size == (8, 8)
        assert image.mode == "RGB"

    def test_something_that_is_not_base64(self) -> None:
        with pytest.raises(UnusableInputError, match="base64"):
            decode_image("data:image/jpeg;base64,???")

    def test_bytes_that_are_not_a_picture(self) -> None:
        payload = base64.b64encode(b"kein Bild").decode("ascii")

        with pytest.raises(UnusableInputError, match="picture"):
            decode_image(f"data:image/jpeg;base64,{payload}")

    def test_a_picture_without_a_data_url(self) -> None:
        with pytest.raises(UnusableInputError, match="data URL"):
            decode_image("https://example.com/hund.jpg")


class TestWhatAModelHandsBack:
    """transformers 4.x hands back the vectors, 5.x the whole tower output around them."""

    def test_a_plain_tensor_is_the_vectors(self) -> None:
        rows = torch.tensor([[1.0, 2.0], [3.0, 4.0]])

        assert _pooled(rows) is rows

    def test_a_tower_output_carries_them_under_pooler_output(self) -> None:
        @dataclass
        class Output:
            pooler_output: torch.Tensor
            last_hidden_state: torch.Tensor

        pooled = torch.tensor([[1.0, 2.0]])
        output = Output(pooler_output=pooled, last_hidden_state=torch.zeros(1, 4, 2))

        assert _pooled(output) is pooled

    def test_an_output_without_pooled_vectors_is_an_error_not_hidden_states(self) -> None:
        @dataclass
        class Output:
            pooler_output: None
            last_hidden_state: torch.Tensor

        with pytest.raises(RuntimeError, match="No pooled output"):
            _pooled(Output(pooler_output=None, last_hidden_state=torch.zeros(1, 4, 2)))


def test_base64_is_what_the_openai_sdks_ask_for(client: TestClient) -> None:
    response = client.post(
        "/v1/embeddings",
        json={"model": "siglip2", "input": ["ein Hund", "eine Katze"], "encoding_format": "base64"},
    )

    assert response.status_code == 200
    packed = response.json()["data"][1]["embedding"]
    raw = base64.b64decode(packed)
    assert list(struct.unpack(f"<{len(raw) // 4}f", raw)) == [1.0] * 8


class FakeTranscriber:
    """Stands in for Whisper: hears one sentence, and remembers what it was given."""

    def __init__(self) -> None:
        self.heard: list[tuple[int, str | None]] = []

    def transcribe(self, audio: bytes, language: str | None = None) -> Transcript:
        from embed.transcriber import Segment, Transcript, decode_wav

        samples = decode_wav(audio)
        self.heard.append((samples.size, language))
        return Transcript(
            language=language or "de",
            duration=samples.size / 16_000,
            segments=[Segment(start=0.5, end=2.0, text="Guck mal, Papa!")],
        )


def a_wav(seconds: float = 2.0, rate: int = 16_000, channels: int = 1) -> bytes:
    import wave

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setnchannels(channels)
        writer.setsampwidth(2)
        writer.setframerate(rate)
        writer.writeframes(b"\x10\x00" * int(seconds * rate) * channels)
    return buffer.getvalue()


@pytest.fixture
def listener() -> FakeTranscriber:
    return FakeTranscriber()


@pytest.fixture
def listening_client(encoder: CountingEncoder, listener: FakeTranscriber) -> TestClient:
    settings = Settings(
        image_model_name="siglip2",
        text_model_name="bge-m3",
        transcribe_model_name="whisper",
        lazy=True,
    )
    return TestClient(
        create_app(settings, encoders={"siglip2": encoder, "bge-m3": encoder}, transcriber=listener)
    )


def test_it_transcribes_the_way_the_openai_api_does(
    listening_client: TestClient, listener: FakeTranscriber
) -> None:
    response = listening_client.post(
        "/v1/audio/transcriptions",
        files={"file": ("sound.wav", a_wav(), "audio/wav")},
        data={"model": "whisper", "response_format": "verbose_json", "language": "de"},
    )

    body = response.json()
    assert response.status_code == 200
    assert body["language"] == "de"
    assert body["duration"] == 2.0
    assert body["segments"] == [{"id": 0, "start": 0.5, "end": 2.0, "text": "Guck mal, Papa!"}]
    assert listener.heard == [(32_000, "de")]


def test_plain_json_carries_only_the_text(listening_client: TestClient) -> None:
    response = listening_client.post(
        "/v1/audio/transcriptions",
        files={"file": ("sound.wav", a_wav(), "audio/wav")},
        data={"model": "whisper"},
    )

    assert response.json() == {"text": "Guck mal, Papa!"}


def test_sound_that_is_not_a_wav_is_refused(listening_client: TestClient) -> None:
    response = listening_client.post(
        "/v1/audio/transcriptions",
        files={"file": ("sound.mp3", b"ID3 not a wav", "audio/mpeg")},
        data={"model": "whisper"},
    )

    assert response.status_code == 400


def test_an_unknown_speech_model_is_named(listening_client: TestClient) -> None:
    response = listening_client.post(
        "/v1/audio/transcriptions",
        files={"file": ("sound.wav", a_wav(), "audio/wav")},
        data={"model": "whisper-tiny"},
    )

    assert response.status_code == 404


def test_the_speech_model_is_listed(listening_client: TestClient) -> None:
    ids = [card["id"] for card in listening_client.get("/v1/models").json()["data"]]

    assert ids == ["siglip2", "bge-m3", "whisper", "buffalo_l"]


def test_stereo_at_another_rate_arrives_as_16_khz_mono() -> None:
    from embed.transcriber import decode_wav

    samples = decode_wav(a_wav(seconds=1.0, rate=48_000, channels=2))

    assert samples.shape == (16_000,)


def test_a_quiet_recording_counts_as_silent() -> None:
    from embed.transcriber import decode_wav, is_silent

    assert is_silent(decode_wav(a_wav()))
    assert not is_silent(np.full(16_000, 0.1, dtype=np.float32))


def test_the_models_wait_until_the_describing_model_answers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After a reboot Docker starts everything at once; loading waits for vLLM regardless."""
    import urllib.request

    from embed.main import _wait_for

    asked: list[str] = []

    class Answer:
        status = 200

        def __enter__(self) -> "Answer":
            return self

        def __exit__(self, *_: object) -> None:
            return None

    def urlopen(url: str, timeout: float) -> Answer:
        asked.append(url)
        if len(asked) < 3:
            raise OSError("connection refused")
        return Answer()

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)

    assert asyncio.run(_wait_for("http://vllm:8000/health", 5, every=0.01)) is True
    assert len(asked) == 3


def test_waiting_ends_after_its_time_even_without_an_answer() -> None:
    from embed.main import _wait_for

    assert asyncio.run(_wait_for("http://127.0.0.1:9/health", 0, every=0.01)) is False
