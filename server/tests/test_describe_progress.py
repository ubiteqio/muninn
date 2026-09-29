"""A video being described says which of its frames it is at."""

from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from muninn.ai import service as ai_service
from muninn.ai.analysis import Analysis
from muninn.core.config import get_settings
from muninn.huginn import jobs, tasks
from tests.test_ai_failures import a_describing_model
from tests.test_faces import a_video_to_look_at, has_ffmpeg, worker_database  # noqa: F401

pytestmark = pytest.mark.usefixtures("api_client")

ANSWER = Analysis.model_validate(
    {
        "caption": "Ein blaues Bild.",
        "tags": ["blau"],
        "scene": "innen",
        "ocr_text": "",
        "people_count": 0,
        "time_of_day": "innen",
        "is_screenshot": False,
        "is_document": False,
        "quality": "gut",
    }
)


class AnsweringAnalyzer:
    async def analyze(self, images: Any, *, context: str = "") -> Analysis:
        return ANSWER

    async def summarize(self, *args: object, **kwargs: object) -> str:
        return "Ein blaues Video."


@has_ffmpeg
@pytest.mark.usefixtures("worker_database")
async def test_each_frame_says_where_it_is(
    session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    await a_describing_model(session)
    media_id = (await a_video_to_look_at(session, tmp_path)).id
    monkeypatch.setattr(ai_service, "analyzer_for", lambda profile: AnsweringAnalyzer())
    monkeypatch.setattr(
        tasks, "get_settings", lambda: get_settings().model_copy(update={"derived_path": tmp_path})
    )
    monkeypatch.setattr(tasks, "PROGRESS_EVERY_SECONDS", 0.0)
    heard: list[dict[str, Any]] = []

    async def write(_redis: object, _task_id: str, **progress: Any) -> None:
        heard.append(progress)

    monkeypatch.setattr(jobs, "write_task_progress", write)
    # Described, it hands the caption on to stage 6; that queue is not what this is about.
    monkeypatch.setattr(tasks.embed_caption, "delay", lambda *_args: None)

    assert await tasks._analyze_media(media_id, "task-1") is True

    # Six seconds, a frame every five: two frames to look at, and it said so for each.
    assert [(one["frames_done"], one["frames_total"]) for one in heard] == [(1, 2), (2, 2)]
    assert all(one["total_seconds"] == 6 for one in heard)
