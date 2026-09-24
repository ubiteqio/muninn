"""Talking to an OpenAI-compatible server: the API vLLM, Ollama and the others all speak."""

import time
from collections.abc import Sequence
from typing import Any

import httpx
from pydantic import ValidationError

from muninn.ai.analysis import (
    SUMMARY_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
    Analysis,
    analysis_schema,
    plain_summary,
    summary_prompt,
    user_prompt,
)
from muninn.ai.base import (
    AiError,
    AiUnreachableError,
    Check,
    DetectedFace,
    SpokenPart,
    Transcript,
)


class OpenAiEmbedder:
    """Vectors from a model behind /v1/embeddings."""

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str = "",
        timeout_seconds: int = 120,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._api_key = api_key
        self._timeout = timeout_seconds
        self._client = client

    async def embed(self, inputs: Sequence[str]) -> list[list[float]]:
        if not inputs:
            return []

        payload = await self._post("/embeddings", {"model": self._model, "input": list(inputs)})
        rows = payload.get("data")
        if not isinstance(rows, list) or len(rows) != len(inputs):
            raise AiError(f"{self._model} answered with {_count(rows)} vectors for {len(inputs)}.")

        # The API does not promise the order, but it does number every row.
        vectors: list[list[float]] = [[] for _ in inputs]
        for row in rows:
            index = row.get("index", 0) if isinstance(row, dict) else 0
            vector = row.get("embedding") if isinstance(row, dict) else None
            if not isinstance(vector, list) or not 0 <= index < len(inputs):
                raise AiError(f"{self._model} answered with something that is not a vector.")
            vectors[index] = [float(value) for value in vector]

        return vectors

    async def check(self) -> Check:
        started = time.perf_counter()
        try:
            vectors = await self.embed(["Hallo aus Muninn."])
        except AiError as error:
            return Check(ok=False, detail=str(error), milliseconds=_since(started))

        length = len(vectors[0]) if vectors else 0
        return Check(
            ok=length > 0,
            detail=f"{self._model} antwortet mit {length} Dimensionen.",
            milliseconds=_since(started),
            dimensions=length,
        )

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        return await post_json(
            f"{self._base_url}{path}",
            payload,
            api_key=self._api_key,
            timeout_seconds=self._timeout,
            client=self._client,
        )


class OpenAiAnalyzer:
    """A describing model behind /v1/chat/completions, held to the analysis schema."""

    #: One more try when the answer does not fit the form; a second miss is a real failure.
    ATTEMPTS = 2

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str = "",
        timeout_seconds: int = 120,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._api_key = api_key
        self._timeout = timeout_seconds
        self._client = client

    async def analyze(self, images: Sequence[str], *, context: str = "") -> Analysis:
        if not images:
            raise AiError("Ohne Bild gibt es nichts zu beschreiben.")

        content: list[dict[str, Any]] = [
            {"type": "image_url", "image_url": {"url": image}} for image in images
        ]
        content.append({"type": "text", "text": user_prompt(context)})
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": content},
            ],
            "temperature": 0.2,
            # Room for the whole form: a caption, twenty tags and 500 characters of text in
            # the picture come to about 600 tokens; cut shorter, the JSON stays open.
            "max_tokens": 1500,
            # The server holds the model to the form; Pydantic checks it once more anyway.
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "analysis", "schema": analysis_schema()},
            },
        }

        problem = ""
        for _ in range(self.ATTEMPTS):
            answer = _message_of(
                await post_json(
                    f"{self._base_url}/chat/completions",
                    payload,
                    api_key=self._api_key,
                    timeout_seconds=self._timeout,
                    client=self._client,
                )
            )
            try:
                return Analysis.model_validate_json(_without_fences(answer)).cleaned()
            except ValidationError as error:
                problem = f"{error.error_count()} Fehler, z. B. {error.errors()[0]['msg']}"

        raise AiError(f"{self._model} antwortet nicht im verlangten Format: {problem}")

    async def summarize(
        self,
        moments: Sequence[tuple[int, str]],
        *,
        context: str = "",
        spoken: Sequence[tuple[float, str]] = (),
    ) -> str:
        if not moments:
            raise AiError("Ohne Standbilder gibt es nichts zusammenzufassen.")

        answer = _message_of(
            await post_json(
                f"{self._base_url}/chat/completions",
                {
                    "model": self._model,
                    "messages": [
                        {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
                        {
                            "role": "user",
                            "content": summary_prompt(list(moments), context, list(spoken)),
                        },
                    ],
                    "temperature": 0.2,
                    "max_tokens": 200,
                },
                api_key=self._api_key,
                timeout_seconds=self._timeout,
                client=self._client,
            )
        )
        answer = plain_summary(answer)
        if not answer:
            raise AiError(f"{self._model} fasst das Video nicht zusammen.")
        return answer


def _message_of(payload: dict[str, Any]) -> str:
    choices = payload.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        message = choices[0].get("message")
        if isinstance(message, dict):
            return str(message.get("content") or "")
    return ""


def _without_fences(answer: str) -> str:
    """Some models wrap JSON in a Markdown code block even when told not to."""
    text = answer.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        text = text.rsplit("```", 1)[0]
    return text.strip()


class OpenAiTranscriber:
    """A speech model behind /v1/audio/transcriptions, asked for text with times."""

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str = "",
        timeout_seconds: int = 120,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._api_key = api_key
        self._timeout = timeout_seconds
        self._client = client

    async def transcribe(self, wav: bytes) -> Transcript:
        payload = await post_form(
            f"{self._base_url}/audio/transcriptions",
            data={"model": self._model, "response_format": "verbose_json"},
            files={"file": ("sound.wav", wav, "audio/wav")},
            api_key=self._api_key,
            timeout_seconds=self._timeout,
            client=self._client,
        )
        segments = payload.get("segments")
        parts: list[SpokenPart] = []
        if isinstance(segments, list):
            for segment in segments:
                if not isinstance(segment, dict):
                    continue
                text = " ".join(str(segment.get("text", "")).split())
                if text:
                    parts.append(
                        SpokenPart(
                            start=float(segment.get("start", 0.0)),
                            end=float(segment.get("end", 0.0)),
                            text=text,
                        )
                    )
        elif payload.get("text"):
            # A server that only knows plain JSON: the words, without their times.
            parts.append(SpokenPart(start=0.0, end=0.0, text=str(payload["text"]).strip()))

        return Transcript(language=str(payload.get("language") or ""), parts=parts)

    async def check(self) -> Check:
        """One second of silence: the answer is empty, but it proves the model is there."""
        started = time.perf_counter()
        try:
            await self.transcribe(silent_wav(seconds=1))
        except AiError as error:
            return Check(ok=False, detail=str(error), milliseconds=_since(started))
        return Check(ok=True, detail=f"{self._model} hört zu.", milliseconds=_since(started))


#: How many pictures go to the face model in one request.
#:
#: The machine names its own limit and refuses more with a 413. Ours defaults to 64 and is set
#: to less in places, so this stays under any of them: a minute of video is a dozen frames, and
#: a request per dozen costs nothing next to what the model itself takes.
FACES_AT_ONCE = 16


class OpenAiFaceDetector:
    """Faces from Muninn's embedding service at /v1/faces - shaped like the OpenAI endpoints,
    though OpenAI has no such thing."""

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str = "",
        timeout_seconds: int = 120,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._api_key = api_key
        self._timeout = timeout_seconds
        self._client = client

    async def detect(self, images: Sequence[str]) -> list[list[DetectedFace]]:
        """The faces in these pictures, one list each, in the order they were given.

        A long video is a lot of frames at once, and the machine says how many it will take in
        one request - the answer was a 413 and a whole video without faces. They go in parts
        small enough for any setting of it, and the parts are put back together here.
        """
        if not images:
            return []
        if len(images) > FACES_AT_ONCE:
            parts = [
                await self.detect(images[start : start + FACES_AT_ONCE])
                for start in range(0, len(images), FACES_AT_ONCE)
            ]
            return [faces for part in parts for faces in part]
        payload = await post_json(
            f"{self._base_url}/faces",
            {"model": self._model, "input": list(images)},
            api_key=self._api_key,
            timeout_seconds=self._timeout,
            client=self._client,
        )
        rows = payload.get("data")
        if not isinstance(rows, list) or len(rows) != len(images):
            raise AiError("Die Antwort enthält nicht für jedes Bild Gesichter.")
        found: list[list[DetectedFace]] = [[] for _ in images]
        for row in rows:
            try:
                index = int(row["index"])
                width, height = float(row["width"]), float(row["height"])
                faces = [
                    DetectedFace(
                        box=(
                            float(face["box"][0]) / width,
                            float(face["box"][1]) / height,
                            float(face["box"][2]) / width,
                            float(face["box"][3]) / height,
                        ),
                        score=float(face["score"]),
                        embedding=[float(value) for value in face["embedding"]],
                        pixels=int(
                            min(
                                float(face["box"][2]) - float(face["box"][0]),
                                float(face["box"][3]) - float(face["box"][1]),
                            )
                        ),
                        aspect=width / height,
                    )
                    for face in row["faces"]
                ]
            except (KeyError, TypeError, ValueError, ZeroDivisionError, IndexError) as error:
                raise AiError(f"Die Antwort ist unlesbar: {error}") from error
            if not 0 <= index < len(images):
                raise AiError("Die Antwort nennt ein Bild, nach dem nicht gefragt war.")
            found[index] = faces
        return found

    async def check(self) -> Check:
        """A small grey picture: no faces in it, but the answer proves the model is there."""
        started = time.perf_counter()
        try:
            await self.detect([grey_picture()])
        except AiError as error:
            return Check(ok=False, detail=str(error), milliseconds=_since(started))
        return Check(
            ok=True, detail=f"{self._model} findet Gesichter.", milliseconds=_since(started)
        )


def grey_picture() -> str:
    """A 64 by 64 grey JPEG as a data URL."""
    import base64

    import pyvips

    picture = (pyvips.Image.black(64, 64, bands=3) + 128).cast("uchar")
    jpeg = bytes(picture.write_to_buffer(".jpg"))
    return "data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii")


def silent_wav(*, seconds: int) -> bytes:
    """A WAV of silence at 16 kHz mono, for asking a speech model whether it is there."""
    import io
    import wave

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(16_000)
        writer.writeframes(b"\x00\x00" * 16_000 * seconds)
    return buffer.getvalue()


async def probe_chat_model(
    *,
    base_url: str,
    model: str,
    api_key: str = "",
    timeout_seconds: int = 120,
    client: httpx.AsyncClient | None = None,
) -> Check:
    """Ask a describing model one short question, to see whether it is there.

    Deliberately not the real analysis prompt: this is about the connection, the key and the
    model name, and it should cost the GPU as little as possible.
    """
    started = time.perf_counter()
    try:
        payload = await post_json(
            f"{base_url.rstrip('/')}/chat/completions",
            {
                "model": model,
                "messages": [{"role": "user", "content": "Antworte mit dem Wort: bereit"}],
                "max_tokens": 8,
                "temperature": 0,
            },
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            client=client,
        )
    except AiError as error:
        return Check(ok=False, detail=str(error), milliseconds=_since(started))

    choices = payload.get("choices")
    answer = ""
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        message = choices[0].get("message")
        if isinstance(message, dict):
            answer = str(message.get("content", "")).strip()

    if not answer:
        return Check(
            ok=False,
            detail=f"{model} antwortet, sagt aber nichts.",
            milliseconds=_since(started),
        )

    return Check(
        ok=True,
        detail=f"{model} antwortet: „{answer[:60]}“",
        milliseconds=_since(started),
    )


#: How long connecting to a machine may take. A machine that is switched off does not refuse, it
#: stays silent, and the operating system only gives up after a minute or more. Every AI stage
#: would hold a worker that long per medium; five seconds say "away" just as surely.
CONNECT_SECONDS = 5


def _timeout(seconds: int) -> httpx.Timeout:
    """The profile's time for the answer, but a short one for getting through at all."""
    return httpx.Timeout(seconds, connect=min(CONNECT_SECONDS, seconds))


async def post_json(
    url: str,
    payload: dict[str, Any],
    *,
    api_key: str,
    timeout_seconds: int,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """One request, with every way it can go wrong turned into a sentence for an admin."""
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

    async def send(http: httpx.AsyncClient) -> httpx.Response:
        return await http.post(
            url, json=payload, headers=headers, timeout=_timeout(timeout_seconds)
        )

    try:
        if client is not None:
            response = await send(client)
        else:
            async with httpx.AsyncClient() as http:
                response = await send(http)
    except (httpx.ConnectError, httpx.ConnectTimeout) as error:
        raise AiUnreachableError(f"{url} ist nicht erreichbar: {error}") from error
    except httpx.TimeoutException as error:
        raise AiError(f"Keine Antwort innerhalb von {timeout_seconds} Sekunden.") from error
    except httpx.HTTPError as error:
        raise AiError(f"{url} ist nicht erreichbar: {error}") from error

    return _checked(response, url)


async def post_form(
    url: str,
    *,
    data: dict[str, str],
    files: dict[str, tuple[str, bytes, str]],
    api_key: str,
    timeout_seconds: int,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """A file upload, with the same sentences for an admin as post_json."""
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

    async def send(http: httpx.AsyncClient) -> httpx.Response:
        return await http.post(
            url, data=data, files=files, headers=headers, timeout=_timeout(timeout_seconds)
        )

    try:
        if client is not None:
            response = await send(client)
        else:
            async with httpx.AsyncClient() as http:
                response = await send(http)
    except (httpx.ConnectError, httpx.ConnectTimeout) as error:
        raise AiUnreachableError(f"{url} ist nicht erreichbar: {error}") from error
    except httpx.TimeoutException as error:
        raise AiError(f"Keine Antwort innerhalb von {timeout_seconds} Sekunden.") from error
    except httpx.HTTPError as error:
        raise AiError(f"{url} ist nicht erreichbar: {error}") from error

    return _checked(response, url)


def _since(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _count(rows: object) -> int:
    return len(rows) if isinstance(rows, list) else 0


def _snippet(response: httpx.Response) -> str:
    text = response.text.strip().replace("\n", " ")
    return text[:120] if text else "ohne Text"


def _checked(response: httpx.Response, url: str) -> dict[str, Any]:
    if response.status_code == 401 or response.status_code == 403:
        raise AiError("Der Schlüssel wird nicht angenommen.")
    if response.status_code == 404:
        raise AiError(f"{url} gibt es dort nicht. Endet die Basis-URL auf /v1?")
    if response.status_code >= 400:
        raise AiError(f"Der Dienst antwortet mit {response.status_code}: {_snippet(response)}")

    try:
        body: dict[str, Any] = response.json()
    except ValueError as error:
        raise AiError("Die Antwort ist kein JSON.") from error

    if not isinstance(body, dict):
        raise AiError("Die Antwort ist kein JSON-Objekt.")
    return body
