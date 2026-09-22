"""Muninn's embedding service, speaking the OpenAI embeddings and transcription APIs.

Four models behind one address: SigLIP 2 for pictures and the sentences that should find them,
BGE-M3 for descriptions, Whisper for what is said in a video, InsightFace for faces. Which one
answers is decided by the model name in the request, exactly as with any other OpenAI-compatible
server - so Muninn needs no special case for this one. Faces have no OpenAI API; /v1/faces is
shaped like the others.
"""

import asyncio
import base64
import logging
import struct
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field

from embed.config import Settings, get_settings
from embed.encoders import Encoder, UnusableInputError, load_bge, load_siglip, pick_device
from embed.faces import FaceFinder, UnusableImageError, load_insightface
from embed.transcriber import Transcriber, Transcript, UnusableAudioError, load_whisper

logger = logging.getLogger(__name__)


class EmbeddingRequest(BaseModel):
    """The OpenAI request, as much of it as this service uses."""

    model: str
    #: A picture arrives as a data URL, a text as itself. One or many.
    input: str | list[str]
    #: The OpenAI SDKs ask for "base64" unless told otherwise; both are answered.
    encoding_format: Literal["float", "base64"] = "float"


class Embedding(BaseModel):
    object: Literal["embedding"] = "embedding"
    index: int
    embedding: list[float] | str


class EmbeddingResponse(BaseModel):
    object: Literal["list"] = "list"
    data: list[Embedding]
    model: str
    usage: dict[str, int] = Field(default_factory=lambda: {"prompt_tokens": 0, "total_tokens": 0})


class TranscriptSegment(BaseModel):
    id: int
    start: float
    end: float
    text: str


class TranscriptionResponse(BaseModel):
    """OpenAI's "verbose_json": the text, and when each part of it was said."""

    task: Literal["transcribe"] = "transcribe"
    language: str
    duration: float
    text: str
    segments: list[TranscriptSegment]


class FacesRequest(BaseModel):
    """Pictures as data URLs, like the embeddings take them."""

    model: str
    input: str | list[str]


class FaceView(BaseModel):
    #: Left, top, right, bottom in pixels of the picture, upright.
    box: list[float]
    score: float
    landmarks: list[list[float]]
    embedding: list[float]


class FacesResult(BaseModel):
    index: int
    width: int
    height: int
    faces: list[FaceView]


class FacesResponse(BaseModel):
    object: Literal["list"] = "list"
    data: list[FacesResult]
    model: str


class ModelCard(BaseModel):
    id: str
    object: Literal["model"] = "model"
    owned_by: str = "muninn"
    #: How long the vectors are. Not part of the OpenAI API, and useful enough to send anyway.
    dimensions: int | None = None


class ModelList(BaseModel):
    object: Literal["list"] = "list"
    data: list[ModelCard]


def create_app(
    settings: Settings | None = None,
    encoders: dict[str, Encoder] | None = None,
    transcriber: Transcriber | None = None,
    face_finder: FaceFinder | None = None,
) -> FastAPI:
    """The service. `encoders`, `transcriber` and `face_finder` are for tests: they skip loading
    the weights."""
    settings = settings or get_settings()
    logging.basicConfig(level=logging.INFO)

    loaders: dict[str, Callable[[], Encoder]] = {
        settings.image_model_name: lambda: load_siglip(
            settings.image_model_id, _device(settings), settings.dtype
        ),
        settings.text_model_name: lambda: load_bge(
            settings.text_model_id, _device(settings), settings.dtype
        ),
    }
    loaded: dict[str, Encoder] = dict(encoders or {})
    listening: dict[str, Transcriber] = {}
    if transcriber is not None and settings.transcribe_model_name:
        listening[settings.transcribe_model_name] = transcriber

    def transcriber_for(name: str) -> Transcriber:
        if not settings.transcribe_model_name or name != settings.transcribe_model_name:
            served = settings.transcribe_model_name or "no speech model"
            raise HTTPException(404, f"This service transcribes with {served}, not {name!r}.")
        if name not in listening:
            listening[name] = load_whisper(
                settings.transcribe_model_id,
                pick_device(settings.transcribe_device)
                if settings.transcribe_device
                else _device(settings),
                settings.dtype,
            )
        return listening[name]

    finders: dict[str, FaceFinder] = {}
    if face_finder is not None and settings.face_model_name:
        finders[settings.face_model_name] = face_finder

    def finder_for(name: str) -> FaceFinder:
        if not settings.face_model_name or name != settings.face_model_name:
            served = settings.face_model_name or "no face model"
            raise HTTPException(404, f"This service finds faces with {served}, not {name!r}.")
        if name not in finders:
            finders[name] = load_insightface(
                settings.face_model_url,
                Path(settings.face_model_dir),
                pick_device(settings.face_device) if settings.face_device else _device(settings),
                settings.face_threshold,
                settings.face_memory_mb,
            )
        return finders[name]

    def encoder_for(name: str) -> Encoder:
        if name in loaded:
            return loaded[name]

        load = loaders.get(name)
        if load is None:
            known = ", ".join(sorted(loaders))
            raise HTTPException(404, f"This service serves {known}, not {name!r}.")

        loaded[name] = load()
        return loaded[name]

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if settings.wait_for:
            await _wait_for(settings.wait_for, settings.wait_seconds)
        # Loading at startup means the first picture is not the one that waits two minutes.
        if not settings.lazy and not encoders:
            for name in loaders:
                encoder_for(name)
            if settings.transcribe_model_name:
                transcriber_for(settings.transcribe_model_name)
            if settings.face_model_name:
                finder_for(settings.face_model_name)
        yield

    app = FastAPI(title="Muninn embeddings", version="1.0.0", lifespan=lifespan)
    app.state.settings = settings

    def guard(authorization: Annotated[str | None, Header()] = None) -> None:
        """The same door vLLM has: a bearer token, when one was set up."""
        if not settings.api_key:
            return
        if authorization != f"Bearer {settings.api_key}":
            raise HTTPException(401, "Unauthorized")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/v1/models", dependencies=[Depends(guard)])
    async def models() -> ModelList:
        """What this service answers to. Dimensions only for what is already loaded."""
        return ModelList(
            data=[
                ModelCard(
                    id=name,
                    dimensions=loaded[name].dimensions if name in loaded else None,
                )
                for name in loaders
            ]
            + (
                [ModelCard(id=settings.transcribe_model_name)]
                if settings.transcribe_model_name
                else []
            )
            + ([ModelCard(id=settings.face_model_name)] if settings.face_model_name else [])
        )

    @app.post("/v1/embeddings", dependencies=[Depends(guard)])
    async def embeddings(payload: EmbeddingRequest) -> EmbeddingResponse:
        inputs = [payload.input] if isinstance(payload.input, str) else payload.input
        if not inputs:
            return EmbeddingResponse(data=[], model=payload.model)
        if len(inputs) > settings.max_batch:
            raise HTTPException(
                413, f"At most {settings.max_batch} inputs at a time, not {len(inputs)}."
            )

        encoder = encoder_for(payload.model)
        started = time.perf_counter()
        try:
            vectors = await _in_a_thread(encoder.encode, inputs)
        except UnusableInputError as error:
            raise HTTPException(400, str(error)) from error

        logger.info(
            "%s: %d inputs in %d ms",
            payload.model,
            len(inputs),
            int((time.perf_counter() - started) * 1000),
        )
        return EmbeddingResponse(
            data=[
                Embedding(index=index, embedding=_pack(vector, payload.encoding_format))
                for index, vector in enumerate(vectors)
            ],
            model=payload.model,
        )

    @app.post("/v1/faces", dependencies=[Depends(guard)])
    async def faces(payload: FacesRequest) -> FacesResponse:
        """Every face in each picture: its box, its five points and its vector.

        Not part of the OpenAI API - there is no such thing there - but shaped like it.
        """
        inputs = [payload.input] if isinstance(payload.input, str) else payload.input
        if len(inputs) > settings.max_batch:
            raise HTTPException(
                413, f"At most {settings.max_batch} inputs at a time, not {len(inputs)}."
            )
        finder = finder_for(payload.model)
        try:
            pictures = [_picture_bytes(item) for item in inputs]
            started = time.perf_counter()
            found = await asyncio.to_thread(finder.find, pictures)
        except UnusableImageError as error:
            raise HTTPException(400, str(error)) from error

        logger.info(
            "%s: %d faces in %d pictures in %d ms",
            payload.model,
            sum(len(result.faces) for result in found),
            len(inputs),
            int((time.perf_counter() - started) * 1000),
        )
        return FacesResponse(
            model=payload.model,
            data=[
                FacesResult(
                    index=index,
                    width=result.width,
                    height=result.height,
                    faces=[
                        FaceView(
                            box=list(face.box),
                            score=face.score,
                            landmarks=[list(point) for point in face.landmarks],
                            embedding=face.embedding,
                        )
                        for face in result.faces
                    ],
                )
                for index, result in enumerate(found)
            ],
        )

    @app.post("/v1/audio/transcriptions", dependencies=[Depends(guard)])
    async def transcriptions(
        file: Annotated[UploadFile, File()],
        model: Annotated[str, Form()],
        language: Annotated[str | None, Form()] = None,
        response_format: Annotated[str, Form()] = "json",
    ) -> Any:
        """What is said in a recording, OpenAI style. Muninn asks for "verbose_json"."""
        listener = transcriber_for(model)
        audio = await file.read(settings.max_audio_bytes + 1)
        if len(audio) > settings.max_audio_bytes:
            raise HTTPException(413, f"At most {settings.max_audio_bytes} bytes of sound.")

        started = time.perf_counter()
        try:
            transcript: Transcript = await asyncio.to_thread(
                listener.transcribe, audio, language or None
            )
        except UnusableAudioError as error:
            raise HTTPException(400, str(error)) from error

        logger.info(
            "%s: %.0f s of sound, %d segments in %d ms",
            model,
            transcript.duration,
            len(transcript.segments),
            int((time.perf_counter() - started) * 1000),
        )
        if response_format == "text":
            from fastapi.responses import PlainTextResponse

            return PlainTextResponse(transcript.text)
        if response_format == "verbose_json":
            return TranscriptionResponse(
                language=transcript.language,
                duration=round(transcript.duration, 2),
                text=transcript.text,
                segments=[
                    TranscriptSegment(id=index, start=seg.start, end=seg.end, text=seg.text)
                    for index, seg in enumerate(transcript.segments)
                ],
            )
        return {"text": transcript.text}

    @app.exception_handler(UnusableInputError)
    async def unusable(request: Request, error: Exception) -> Any:
        from fastapi.responses import JSONResponse

        return JSONResponse({"error": str(error)}, status_code=400)

    return app


def _pack(vector: list[float], encoding_format: str) -> list[float] | str:
    """As OpenAI does it: base64 of little-endian float32, or the plain list."""
    if encoding_format == "base64":
        return base64.b64encode(struct.pack(f"<{len(vector)}f", *vector)).decode("ascii")
    return vector


def _picture_bytes(item: str) -> bytes:
    """A data URL's bytes. Faces are only ever looked for in pictures."""
    if not item.startswith("data:image/") or ";base64," not in item:
        raise UnusableImageError("Send each picture as a base64 data URL.")
    try:
        return base64.b64decode(item.split(";base64,", 1)[1], validate=True)
    except ValueError as error:
        raise UnusableImageError("The data URL does not hold base64.") from error


async def _wait_for(url: str, seconds: int, *, every: float = 5.0) -> bool:
    """Until the address answers 200, or the time is up. Returns whether it answered."""
    import urllib.error
    import urllib.request

    def answers() -> bool:
        try:
            with urllib.request.urlopen(url, timeout=5) as response:  # noqa: S310 - our setting
                return bool(response.status == 200)
        except (urllib.error.URLError, OSError, ValueError):
            return False

    deadline = time.monotonic() + seconds
    logger.info("Waiting for %s before loading the models", url)
    while time.monotonic() < deadline:
        if await asyncio.to_thread(answers):
            logger.info("%s answers; loading the models", url)
            return True
        await asyncio.sleep(every)
    logger.warning("%s did not answer within %d s; loading the models anyway", url, seconds)
    return False


def _device(settings: Settings) -> str:
    return pick_device(settings.device)


async def _in_a_thread(
    work: Callable[[list[str]], list[list[float]]], inputs: list[str]
) -> list[list[float]]:
    """Encoding holds the GIL and takes seconds; the event loop has other requests to answer."""
    return await asyncio.to_thread(work, inputs)
