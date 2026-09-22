"""Stage 5 and 6: the describing model fills in its form, and the caption becomes searchable."""

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import httpx
import pytest
import pyvips
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from muninn.ai.analysis import Analysis
from muninn.ai.base import AiError, Check
from muninn.ai.openai_compatible import OpenAiAnalyzer
from muninn.analysis import service
from muninn.models.media import Media, MediaKind
from muninn.models.user import UserRole
from muninn.search import service as search_service
from tests.helpers import auth_header, create_user, login
from tests.test_timeline import JULY, a_medium, an_album

pytestmark = pytest.mark.usefixtures("api_client")

SANDCASTLE = {
    "caption": "Zwei Kinder bauen am Strand eine Sandburg.",
    "tags": ["Strand", "kinder", "Sandburg", "strand", " "],
    "scene": "Strand",
    "ocr_text": "",
    "people_count": 2,
    "time_of_day": "tag",
    "is_screenshot": False,
    "is_document": False,
    "quality": "gut",
}


def a_server(answers: list[str], seen: list[dict[str, Any]]) -> httpx.AsyncClient:
    """A chat server that gives these answers in turn and remembers what it was asked."""

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        content = answers[min(len(seen), len(answers)) - 1]
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def an_analyzer(client: httpx.AsyncClient) -> OpenAiAnalyzer:
    return OpenAiAnalyzer(base_url="http://gpu:8000/v1", model="qwen", client=client)


class TestTheQuestion:
    async def test_the_picture_and_the_form_go_along(self) -> None:
        seen: list[dict[str, Any]] = []
        async with a_server([json.dumps(SANDCASTLE)], seen) as client:
            answer = await an_analyzer(client).analyze(
                ["data:image/webp;base64,AAAA"], context="Album „Urlaub“"
            )

        request = seen[0]
        assert request["model"] == "qwen"
        assert request["response_format"]["type"] == "json_schema"
        content = request["messages"][1]["content"]
        assert content[0] == {
            "type": "image_url",
            "image_url": {"url": "data:image/webp;base64,AAAA"},
        }
        assert "Urlaub" in content[1]["text"]
        # Tidied: lower case, no repeats, no blanks.
        assert answer.tags == ["strand", "kinder", "sandburg"]
        assert answer.scene == "strand"

    async def test_an_answer_off_the_form_is_asked_for_once_more(self) -> None:
        seen: list[dict[str, Any]] = []
        answers = ['{"caption": "nur halb"}', json.dumps(SANDCASTLE)]
        async with a_server(answers, seen) as client:
            answer = await an_analyzer(client).analyze(["data:image/webp;base64,AAAA"])

        assert len(seen) == 2
        assert answer.people_count == 2

    async def test_two_misses_are_a_failure_an_admin_can_read(self) -> None:
        seen: list[dict[str, Any]] = []
        async with a_server(["kein JSON"], seen) as client:
            with pytest.raises(AiError, match="Format"):
                await an_analyzer(client).analyze(["data:image/webp;base64,AAAA"])

        assert len(seen) == 2

    async def test_a_video_is_summed_up_without_a_picture(self) -> None:
        seen: list[dict[str, Any]] = []
        async with a_server(["Kinder spielen am Strand."], seen) as client:
            summary = await an_analyzer(client).summarize(
                [(0, "Ein Kind am Strand."), (12, "Zwei Kinder im Wasser.")]
            )

        assert summary == "Kinder spielen am Strand."
        prompt = seen[0]["messages"][1]["content"]
        assert isinstance(prompt, str)
        assert "Sekunde 12: Zwei Kinder im Wasser." in prompt
        assert "response_format" not in seen[0]

    async def test_a_summary_wrapped_in_json_is_turned_back_into_sentences(self) -> None:
        seen: list[dict[str, Any]] = []
        wrapped = json.dumps({"beschreibung": ["Ein Junge trinkt.", "Er lacht in die Kamera."]})
        async with a_server([wrapped], seen) as client:
            summary = await an_analyzer(client).summarize([(0, "a"), (1, "b")])

        assert summary == "Ein Junge trinkt. Er lacht in die Kamera."
        assert "ohne JSON" in seen[0]["messages"][0]["content"]

    async def test_json_in_a_code_block_is_still_read(self) -> None:
        seen: list[dict[str, Any]] = []
        fenced = f"```json\n{json.dumps(SANDCASTLE)}\n```"
        async with a_server([fenced], seen) as client:
            answer = await an_analyzer(client).analyze(["data:image/webp;base64,AAAA"])

        assert answer.caption.startswith("Zwei Kinder")


class FakeAnalyzer:
    def __init__(self) -> None:
        self.asked: list[tuple[int, str]] = []

    async def analyze(self, images: Sequence[str], *, context: str = "") -> Analysis:
        self.asked.append((len(images), context))
        return Analysis.model_validate(SANDCASTLE).cleaned()

    async def summarize(
        self,
        moments: Sequence[tuple[int, str]],
        *,
        context: str = "",
        spoken: Sequence[tuple[float, str]] = (),
    ) -> str:
        return " ".join(caption for _, caption in moments)


class FakeEmbedder:
    def __init__(self) -> None:
        self.inputs: list[str] = []

    async def embed(self, inputs: Sequence[str]) -> list[list[float]]:
        self.inputs.extend(inputs)
        return [[0.5] * 8 for _ in inputs]

    async def check(self) -> Check:
        return Check(ok=True, detail="", milliseconds=0, dimensions=8)


async def a_photo_with_preview(session: AsyncSession, derived: Path) -> Media:
    album = await an_album(session, "Urlaub/2012 Italien")
    medium = await a_medium(session, album, taken_at=JULY, name="IMG_1.jpg")
    medium.preview_path = f"{medium.id.hex[:2]}/{medium.id.hex}/preview-1.webp"
    preview = derived / medium.preview_path
    preview.parent.mkdir(parents=True)
    # Larger than the model gets to see, so the scaling is part of the test.
    pyvips.Image.black(1600, 1200, bands=3).linear(1, [30, 120, 200]).write_to_file(str(preview))
    await session.commit()
    return medium


async def test_a_photo_is_described_with_its_album_and_date_as_hint(
    session: AsyncSession, tmp_path: Path
) -> None:
    medium = await a_photo_with_preview(session, tmp_path)
    analyzer = FakeAnalyzer()

    described = await service.apply_analysis(
        session, medium.id, analyzer=analyzer, model="qwen", derived_root=tmp_path
    )

    assert described is True
    assert analyzer.asked == [(1, "Album „Urlaub/2012 Italien“, aufgenommen am 14.07.2009")]
    stored = await service.get_analysis(session, medium.id)
    assert stored is not None
    assert stored.caption == "Zwei Kinder bauen am Strand eine Sandburg."
    assert stored.tags == ["strand", "kinder", "sandburg"]


async def test_the_description_can_be_found_by_german_word_stems(
    session: AsyncSession, tmp_path: Path
) -> None:
    """„Sandburgen“ finds „Sandburg“: the full text stems German words."""
    medium = await a_photo_with_preview(session, tmp_path)
    await service.apply_analysis(
        session, medium.id, analyzer=FakeAnalyzer(), model="qwen", derived_root=tmp_path
    )

    found = await session.scalar(
        text(
            "SELECT media_id FROM media_analyses "
            "WHERE search_tsv @@ plainto_tsquery('german', 'Sandburgen')"
        )
    )
    assert found == medium.id


async def test_a_described_photo_is_not_asked_about_again(
    session: AsyncSession, tmp_path: Path
) -> None:
    medium = await a_photo_with_preview(session, tmp_path)
    await service.apply_analysis(
        session, medium.id, analyzer=FakeAnalyzer(), model="qwen", derived_root=tmp_path
    )
    analyzer = FakeAnalyzer()

    again = await service.apply_analysis(
        session, medium.id, analyzer=analyzer, model="qwen", derived_root=tmp_path
    )

    assert again is False
    assert analyzer.asked == []
    assert await service.media_without(session, model="qwen") == []
    # Another model has not described it yet.
    assert await service.media_without(session, model="other") == [medium.id]


async def test_a_video_without_its_720p_version_waits_for_stage_3(
    session: AsyncSession, tmp_path: Path
) -> None:
    medium = await a_photo_with_preview(session, tmp_path)
    medium.kind = MediaKind.VIDEO
    await session.commit()

    assert await service.media_without(session, model="qwen") == []


async def test_the_caption_becomes_a_vector_with_its_tags(
    session: AsyncSession, tmp_path: Path
) -> None:
    medium = await a_photo_with_preview(session, tmp_path)
    assert await search_service.captions_without(session, model="bge-m3") == []
    await service.apply_analysis(
        session, medium.id, analyzer=FakeAnalyzer(), model="qwen", derived_root=tmp_path
    )
    assert await search_service.captions_without(session, model="bge-m3") == [medium.id]
    embedder = FakeEmbedder()

    stored = await search_service.apply_caption_vector(
        session, medium.id, embedder=embedder, model="bge-m3"
    )

    assert stored is True
    assert embedder.inputs == [
        "Zwei Kinder bauen am Strand eine Sandburg. Stichwörter: strand, kinder, sandburg."
    ]
    assert await search_service.count_captions_without(session, model="bge-m3") == 0


async def test_a_new_description_asks_for_a_new_caption_vector(
    session: AsyncSession, tmp_path: Path
) -> None:
    """The old vector stood for words that are no longer there."""
    medium = await a_photo_with_preview(session, tmp_path)
    await service.apply_analysis(
        session, medium.id, analyzer=FakeAnalyzer(), model="qwen", derived_root=tmp_path
    )
    await search_service.apply_caption_vector(
        session, medium.id, embedder=FakeEmbedder(), model="bge-m3"
    )

    await service.store(
        session, medium.id, model="qwen", analysis=Analysis.model_validate(SANDCASTLE)
    )
    await session.commit()

    assert await search_service.captions_without(session, model="bge-m3") == [medium.id]


async def test_the_detail_view_shows_the_description(
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
    api_client: AsyncClient,
    tmp_path: Path,
) -> None:
    medium = await a_photo_with_preview(session, tmp_path)
    await create_user(session_factory, username="anna", display_name="Anna", role=UserRole.USER)
    headers = auth_header(await login(api_client, username="anna"))

    before = (await api_client.get(f"/media/{medium.id}", headers=headers)).json()
    await service.apply_analysis(
        session, medium.id, analyzer=FakeAnalyzer(), model="qwen", derived_root=tmp_path
    )
    after = (await api_client.get(f"/media/{medium.id}", headers=headers)).json()

    assert before["analysis"] is None
    assert after["analysis"]["caption"] == "Zwei Kinder bauen am Strand eine Sandburg."
    assert after["analysis"]["tags"] == ["strand", "kinder", "sandburg"]


async def test_a_missing_preview_is_left_to_stage_3(session: AsyncSession, tmp_path: Path) -> None:
    medium = await a_photo_with_preview(session, tmp_path)
    assert medium.preview_path is not None
    (tmp_path / medium.preview_path).unlink()

    assert (
        await service.apply_analysis(
            session, medium.id, analyzer=FakeAnalyzer(), model="qwen", derived_root=tmp_path
        )
        is False
    )


def test_a_picture_full_of_text_keeps_the_beginning_of_it() -> None:
    """A poster's whole text would run the answer out of room; the rest of the answer counts."""
    from muninn.ai.analysis import OCR_MAX_CHARACTERS, Analysis

    poster = Analysis.model_validate({**SANDCASTLE, "ocr_text": "Konzert am Samstag " * 200})

    assert len(poster.ocr_text) <= OCR_MAX_CHARACTERS
    assert poster.ocr_text.startswith("Konzert am Samstag")
    assert poster.caption == SANDCASTLE["caption"]
