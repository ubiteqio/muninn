"""Whose fault an AI failure is: the machine's rests the stage, the medium's is counted.

Only the face stage counted. Every other AI stage let a medium the machine kept refusing come
round every minute for ever - and a long video was described from its first frame each time.
"""

import uuid
from collections.abc import Sequence
from pathlib import Path

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from muninn.ai import service as ai_service
from muninn.ai.analysis import Analysis
from muninn.ai.base import AiError, AiMachineError
from muninn.ai.openai_compatible import _checked
from muninn.analysis import service as analysis_service
from muninn.core.config import get_settings
from muninn.huginn import jobs, tasks
from muninn.models.ai import AiKind
from muninn.models.attempt import GIVE_UP_AFTER, MediaAttempt
from tests.test_faces import a_video_to_look_at, has_ffmpeg, worker_database  # noqa: F401

pytestmark = pytest.mark.usefixtures("api_client")

MODEL = "qwen3-vl"


class RefusingAnalyzer:
    def __init__(self, error: AiError) -> None:
        self.error = error
        self.asked = 0

    async def analyze(self, images: Sequence[str], *, context: str = "") -> Analysis:
        self.asked += 1
        raise self.error

    async def summarize(self, *args: object, **kwargs: object) -> str:
        raise self.error


async def a_describing_model(session: AsyncSession) -> None:
    await ai_service.create_profile(
        session, kind=AiKind.ANALYZER, name="GPU", base_url="http://gpu.invalid/v1", model=MODEL
    )


async def _attempts_of(session: AsyncSession, media_id: uuid.UUID) -> int:
    session.expire_all()
    found = await session.get(MediaAttempt, (media_id, jobs.ANALYSIS_STAGE))
    return found.attempts if found else 0


@has_ffmpeg
@pytest.mark.usefixtures("worker_database")
async def test_a_video_the_describing_model_refuses_is_given_up_on(
    session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    await a_describing_model(session)
    media_id = (await a_video_to_look_at(session, tmp_path)).id
    refusing = RefusingAnalyzer(AiError("Der Dienst antwortet mit 400: prompt is too long"))
    monkeypatch.setattr(ai_service, "analyzer_for", lambda profile: refusing)
    monkeypatch.setattr(
        tasks, "get_settings", lambda: get_settings().model_copy(update={"derived_path": tmp_path})
    )

    for _ in range(GIVE_UP_AFTER):
        assert await analysis_service.media_without(session, model=MODEL) == [media_id]
        assert await tasks._analyze_media(media_id, "task-1") is False

    # Three noes were enough: the clock leaves it be instead of starting over a fourth time.
    assert await _attempts_of(session, media_id) == GIVE_UP_AFTER
    assert await analysis_service.media_without(session, model=MODEL) == []


@has_ffmpeg
@pytest.mark.usefixtures("worker_database")
async def test_a_machine_that_will_not_take_its_key_costs_the_video_nothing(
    session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Otherwise a wrong key would give up on every medium in the library within minutes."""
    await a_describing_model(session)
    media_id = (await a_video_to_look_at(session, tmp_path)).id
    refusing = RefusingAnalyzer(AiMachineError("Der Schlüssel wird nicht angenommen."))
    monkeypatch.setattr(ai_service, "analyzer_for", lambda profile: refusing)
    monkeypatch.setattr(
        tasks, "get_settings", lambda: get_settings().model_copy(update={"derived_path": tmp_path})
    )

    assert await tasks._analyze_media(media_id, "task-1") is False

    assert await _attempts_of(session, media_id) == 0
    assert await analysis_service.media_without(session, model=MODEL) == [media_id]


@pytest.mark.parametrize(
    ("status", "machine"),
    [
        (401, True),
        (403, True),
        (404, True),
        (502, True),
        (503, True),
        (504, True),
        (400, False),
        (413, False),
        (422, False),
        (500, False),
    ],
)
def test_whose_fault_an_answer_is(status: int, machine: bool) -> None:
    """A gateway, an overloaded service, a key or an address is the machine; a refusal of this
    one request is the medium's, and asking again with it gets the same refusal."""
    response = httpx.Response(status, text="nope")

    with pytest.raises(AiError) as raised:
        _checked(response, "http://gpu.invalid/v1/chat/completions")

    assert isinstance(raised.value, AiMachineError) is machine
