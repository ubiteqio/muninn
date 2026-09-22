"""What the service is told when it starts. Nothing here is decided in code."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Every setting is prefixed with EMBED_ in the environment."""

    model_config = SettingsConfigDict(env_prefix="EMBED_", extra="ignore")

    #: The names this service answers to, and the weights behind them. What an admin types into
    #: Muninn's AI profile is the name on the left.
    image_model_name: str = "siglip2"
    image_model_id: str = "google/siglip2-so400m-patch14-384"
    text_model_name: str = "bge-m3"
    text_model_id: str = "BAAI/bge-m3"
    #: Speech to text for the sound of videos, at /v1/audio/transcriptions. An empty name
    #: leaves it out, for a machine that only makes vectors.
    transcribe_model_name: str = "whisper-large-v3-turbo"
    transcribe_model_id: str = "openai/whisper-large-v3-turbo"
    #: Where Whisper runs. Empty follows EMBED_DEVICE (the card); "cpu" leaves its 1.5 to 2 GB of
    #: the card to the describing model, should the card run full beside it.
    transcribe_device: str = ""

    #: Faces at /v1/faces: where they are and who they look like. An empty name leaves it out.
    face_model_name: str = "buffalo_l"
    face_model_url: str = (
        "https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_l.zip"
    )
    #: Where the face models are unpacked; inside the models volume, so they are fetched once.
    face_model_dir: str = "/data/models/insightface/buffalo_l"
    #: How sure the detector has to be. Muninn asks for more still and drops small faces.
    face_threshold: float = 0.5
    #: The most graphics memory the face models may take, in MB. The describing model next to
    #: them needs its share free when it starts.
    face_memory_mb: int = 1024
    #: Where the face models run: "cpu" leaves the card to the others. They are small - about a
    #: fifth of a second per picture on a CPU is plenty for work in the background. Empty
    #: follows EMBED_DEVICE.
    face_device: str = ""

    #: "cuda" on the machine with the card, "cpu" everywhere else, "auto" to take what is there.
    device: str = "auto"

    #: How precisely the weights are held. On a card half precision is the sensible default: it
    #: halves what the models take out of the memory the describing model also wants, and makes
    #: no difference a search would notice. On a CPU half precision is slower, not faster.
    dtype: str = "auto"

    #: When set, every request has to carry it as a bearer token - the way vLLM does it.
    api_key: str = ""

    #: The largest sound file one request may carry: 16 kHz mono WAV is about 2 MB a minute, so
    #: this is a little over an hour of video.
    max_audio_bytes: int = 128 * 1024 * 1024

    #: How many inputs one request may carry. A batch that is too large runs the card out of
    #: memory, and the caller cannot know how much is left on it.
    max_batch: int = 64

    #: An address to wait for before loading anything, such as vLLM's /health. The describing
    #: model measures the card when it starts and takes its share for good; loading these models
    #: meanwhile - and answering Muninn with them - spoils that measurement. Docker starts every
    #: container at once after a reboot, whatever order compose would keep, so the wait is here.
    wait_for: str = ""
    #: How long to wait for it at most; after that the models load all the same.
    wait_seconds: int = 1800

    #: Load the weights when the first request arrives rather than at startup. Handy on a laptop,
    #: pointless on the machine that is meant to answer quickly.
    lazy: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
