"""The AI services at a glance on the jobs page: green, red, or not set up."""

from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from muninn.ai import service
from muninn.ai.base import Check
from muninn.huginn import jobs
from muninn.models.ai import AiKind, AiProfile
from muninn.models.user import UserRole
from tests.helpers import auth_header, create_user, login

pytestmark = pytest.mark.usefixtures("api_client")


class Machines:
    """Stands in for the machines: says which answer, and counts how often they were asked."""

    def __init__(self) -> None:
        self.down: set[AiKind] = set()
        self.asked: list[AiKind] = []
        self.timeouts: list[int | None] = []

    async def check(self, profile: AiProfile, **options: Any) -> Check:
        self.asked.append(profile.kind)
        self.timeouts.append(options.get("timeout_seconds"))
        if profile.kind in self.down:
            return Check(ok=False, detail="nicht erreichbar", milliseconds=3)
        return Check(ok=True, detail=f"{profile.model} antwortet.", milliseconds=42)


@pytest.fixture
def machines(monkeypatch: pytest.MonkeyPatch) -> Machines:
    fake = Machines()
    monkeypatch.setattr(service, "check_profile", fake.check)
    return fake


async def admin_headers(
    api_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> dict[str, str]:
    await create_user(session_factory, username="admin", display_name="Admin", role=UserRole.ADMIN)
    return auth_header(await login(api_client, username="admin"))


async def add_profile(
    session_factory: async_sessionmaker[AsyncSession], kind: AiKind, model: str
) -> AiProfile:
    async with session_factory() as session:
        return await service.create_profile(
            session, kind=kind, name=model, base_url="http://gpu:8000/v1", model=model
        )


async def health(api_client: AsyncClient, headers: dict[str, str]) -> dict[str, Any]:
    response = await api_client.get("/admin/jobs/ai", headers=headers)
    assert response.status_code == 200
    return {item["kind"]: item for item in response.json()["services"]}


async def test_only_admins_may_look(
    api_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await create_user(session_factory, username="anna", display_name="Anna")
    headers = auth_header(await login(api_client, username="anna"))

    assert (await api_client.get("/admin/jobs/ai", headers=headers)).status_code == 403


async def test_every_interface_is_listed_and_the_unset_ones_are_asked_nothing(
    api_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    machines: Machines,
) -> None:
    headers = await admin_headers(api_client, session_factory)
    await add_profile(session_factory, AiKind.ANALYZER, "qwen")
    machines.down.add(AiKind.ANALYZER)
    await add_profile(session_factory, AiKind.IMAGE_EMBEDDER, "siglip2")

    services = await health(api_client, headers)

    assert list(services) == [kind.value for kind in AiKind]
    assert services["analyzer"]["configured"] is True
    assert services["analyzer"]["ok"] is False
    assert services["analyzer"]["detail"] == "nicht erreichbar"
    assert services["image_embedder"]["ok"] is True
    assert services["image_embedder"]["milliseconds"] == 42
    assert services["face_detector"] == {
        "kind": "face_detector",
        "configured": False,
        "name": None,
        "model": None,
        "ok": None,
        "detail": None,
        "milliseconds": None,
        "checked_at": None,
        "paused_until": None,
    }
    assert sorted(machines.asked) == sorted([AiKind.ANALYZER, AiKind.IMAGE_EMBEDDER])
    # A short question: the page does not wait for a machine the way the pipeline does.
    assert all(timeout is not None and timeout <= 10 for timeout in machines.timeouts)


async def test_an_answer_is_kept_for_a_while(
    api_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    machines: Machines,
) -> None:
    headers = await admin_headers(api_client, session_factory)
    await add_profile(session_factory, AiKind.TEXT_EMBEDDER, "bge-m3")

    await health(api_client, headers)
    await health(api_client, headers)

    assert machines.asked == [AiKind.TEXT_EMBEDDER]


async def test_a_pause_of_the_worker_is_shown_and_a_kept_green_asked_again(
    api_client: AsyncClient,
    api_app: FastAPI,
    session_factory: async_sessionmaker[AsyncSession],
    machines: Machines,
) -> None:
    headers = await admin_headers(api_client, session_factory)
    await add_profile(session_factory, AiKind.ANALYZER, "qwen")
    await health(api_client, headers)

    # The worker found the machine away after the green answer was kept.
    await api_app.state.redis.set(jobs.pause_key(jobs.ANALYSIS_STAGE), "1", ex=120)
    machines.down.add(AiKind.ANALYZER)
    services = await health(api_client, headers)

    assert machines.asked == [AiKind.ANALYZER, AiKind.ANALYZER]
    assert services["analyzer"]["ok"] is False
    assert services["analyzer"]["paused_until"] is not None


async def test_switching_to_another_profile_asks_the_new_one(
    api_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    machines: Machines,
) -> None:
    headers = await admin_headers(api_client, session_factory)
    await add_profile(session_factory, AiKind.TRANSCRIBER, "whisper")
    await health(api_client, headers)

    async with session_factory() as session:
        spare = await service.create_profile(
            session,
            kind=AiKind.TRANSCRIBER,
            name="Ersatz",
            base_url="http://ersatz:8000/v1",
            model="whisper-small",
        )
        await service.activate(session, spare)
    services = await health(api_client, headers)

    assert machines.asked == [AiKind.TRANSCRIBER, AiKind.TRANSCRIBER]
    assert services["transcriber"]["model"] == "whisper-small"


async def test_an_admin_ends_a_pause_when_the_machine_is_back(
    api_client: AsyncClient,
    api_app: FastAPI,
    session_factory: async_sessionmaker[AsyncSession],
    machines: Machines,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from muninn.huginn.app import celery_app

    sent: list[str] = []
    monkeypatch.setattr(celery_app, "send_task", lambda name, **_: sent.append(name))
    headers = await admin_headers(api_client, session_factory)
    await add_profile(session_factory, AiKind.FACE_DETECTOR, "buffalo_l")
    await api_app.state.redis.set(jobs.pause_key(jobs.FACES_STAGE), "1", ex=300)
    machines.down.add(AiKind.FACE_DETECTOR)
    assert (await health(api_client, headers))["face_detector"]["paused_until"] is not None

    # The machine came back; the admin knows before the pause is over.
    machines.down.clear()
    response = await api_client.delete("/admin/jobs/ai/face_detector/pause", headers=headers)
    services = await health(api_client, headers)

    assert response.status_code == 204
    assert await api_app.state.redis.exists(jobs.pause_key(jobs.FACES_STAGE)) == 0
    assert services["face_detector"]["paused_until"] is None
    # Asked again rather than the kept "away" shown.
    assert services["face_detector"]["ok"] is True
    assert sent == ["muninn.tick"]


async def test_only_admins_end_a_pause(
    api_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await create_user(session_factory, username="anna", display_name="Anna")
    headers = auth_header(await login(api_client, username="anna"))

    response = await api_client.delete("/admin/jobs/ai/analyzer/pause", headers=headers)

    assert response.status_code == 403
