"""The machines Muninn asks: the profiles, and what happens when one answers or does not."""

import json
from typing import Any

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from muninn.ai import service
from muninn.ai.base import AiError
from muninn.ai.openai_compatible import OpenAiEmbedder, probe_chat_model
from muninn.models.ai import AiKind
from muninn.models.user import UserRole
from tests.helpers import auth_header, create_user, login

pytestmark = pytest.mark.usefixtures("api_client")


def a_server(handler: Any) -> httpx.AsyncClient:
    """An AI server that only exists inside the test."""
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def embeddings(dimensions: int = 4) -> Any:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        rows = [
            {"index": index, "embedding": [0.5] * dimensions}
            for index, _ in enumerate(payload["input"])
        ]
        return httpx.Response(200, json={"data": rows, "model": payload["model"]})

    return handler


async def admin_headers(
    api_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> dict[str, str]:
    await create_user(session_factory, username="admin", display_name="Admin", role=UserRole.ADMIN)
    return auth_header(await login(api_client, username="admin"))


class TestTalkingToAServer:
    async def test_it_asks_for_vectors_and_keeps_their_order(self) -> None:
        seen: dict[str, Any] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen.update(json.loads(request.content))
            seen["url"] = str(request.url)
            seen["authorization"] = request.headers.get("authorization", "")
            # Deliberately the wrong way round: the API numbers its rows, order is not promised.
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"index": 1, "embedding": [2.0, 2.0]},
                        {"index": 0, "embedding": [1.0, 1.0]},
                    ]
                },
            )

        async with a_server(handler) as client:
            embedder = OpenAiEmbedder(
                base_url="http://gpu.zuhause:8000/v1",
                model="siglip2",
                api_key="geheim",
                client=client,
            )
            vectors = await embedder.embed(["eins", "zwei"])

        assert vectors == [[1.0, 1.0], [2.0, 2.0]]
        assert seen["url"] == "http://gpu.zuhause:8000/v1/embeddings"
        assert seen["model"] == "siglip2"
        assert seen["authorization"] == "Bearer geheim"

    async def test_nothing_to_embed_costs_no_request(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
            raise AssertionError("asked the server for nothing")

        async with a_server(handler) as client:
            embedder = OpenAiEmbedder(base_url="http://gpu:8000/v1", model="m", client=client)
            assert await embedder.embed([]) == []

    async def test_a_refused_key_is_said_in_words(self) -> None:
        async with a_server(lambda request: httpx.Response(401, json={})) as client:
            embedder = OpenAiEmbedder(base_url="http://gpu:8000/v1", model="m", client=client)

            with pytest.raises(AiError, match="Schlüssel"):
                await embedder.embed(["hallo"])

    async def test_an_address_without_v1_says_so(self) -> None:
        async with a_server(lambda request: httpx.Response(404, text="nope")) as client:
            embedder = OpenAiEmbedder(base_url="http://gpu:8000", model="m", client=client)

            with pytest.raises(AiError, match="/v1"):
                await embedder.embed(["hallo"])

    async def test_a_machine_that_is_not_there(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("no route to host")

        async with a_server(handler) as client:
            embedder = OpenAiEmbedder(base_url="http://gpu:8000/v1", model="m", client=client)
            check = await embedder.check()

        assert check.ok is False
        assert "nicht erreichbar" in check.detail

    async def test_checking_an_embedder_reports_its_dimensions(self) -> None:
        async with a_server(embeddings(1152)) as client:
            embedder = OpenAiEmbedder(base_url="http://gpu:8000/v1", model="siglip2", client=client)
            check = await embedder.check()

        assert check.ok is True
        assert check.dimensions == 1152
        assert "1152" in check.detail

    async def test_checking_a_describing_model_repeats_its_answer(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200, json={"choices": [{"message": {"role": "assistant", "content": "bereit"}}]}
            )

        async with a_server(handler) as client:
            check = await probe_chat_model(
                base_url="http://gpu:8000/v1", model="Qwen3-VL-8B-Instruct", client=client
            )

        assert check.ok is True
        assert "bereit" in check.detail
        assert "Qwen3-VL-8B-Instruct" in check.detail


class TestProfiles:
    async def test_the_first_profile_of_an_interface_is_the_one_in_use(
        self, session: AsyncSession
    ) -> None:
        first = await service.create_profile(
            session,
            kind=AiKind.IMAGE_EMBEDDER,
            name="GPU im Keller",
            base_url="http://gpu:8000/v1",
            model="siglip2",
        )
        spare = await service.create_profile(
            session,
            kind=AiKind.IMAGE_EMBEDDER,
            name="Ersatz",
            base_url="http://ersatz:8000/v1",
            model="siglip2",
        )

        assert first.is_active is True
        assert spare.is_active is None
        active = await service.active_profile(session, AiKind.IMAGE_EMBEDDER)
        assert active is not None
        assert active.id == first.id

    async def test_only_one_machine_is_in_use_per_interface(self, session: AsyncSession) -> None:
        first = await service.create_profile(
            session,
            kind=AiKind.ANALYZER,
            name="GPU",
            base_url="http://gpu:8000/v1",
            model="Qwen3-VL-8B-Instruct",
        )
        spare = await service.create_profile(
            session,
            kind=AiKind.ANALYZER,
            name="Ersatz",
            base_url="http://ersatz:8000/v1",
            model="Qwen3-VL-8B-Instruct",
        )

        await service.activate(session, spare)

        await session.refresh(first)
        assert first.is_active is None
        assert spare.is_active is True

    async def test_interfaces_do_not_get_in_each_others_way(self, session: AsyncSession) -> None:
        """Every interface has its own machine in use at the same time."""
        for kind in (AiKind.ANALYZER, AiKind.IMAGE_EMBEDDER, AiKind.TEXT_EMBEDDER):
            await service.create_profile(
                session, kind=kind, name=str(kind), base_url="http://gpu:8000/v1", model="m"
            )

        for kind in (AiKind.ANALYZER, AiKind.IMAGE_EMBEDDER, AiKind.TEXT_EMBEDDER):
            assert await service.active_profile(session, kind) is not None


class TestOverHttp:
    async def test_an_admin_sets_up_a_machine(
        self, api_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        headers = await admin_headers(api_client, session_factory)

        response = await api_client.post(
            "/admin/ai/profiles",
            headers=headers,
            json={
                "kind": "analyzer",
                "name": "GPU im Keller",
                "base_url": "http://gpu.zuhause:8000/v1",
                "model": "Qwen3-VL-8B-Instruct",
                "api_key": "geheim",
                "concurrency": 2,
                "timeout_seconds": 120,
            },
        )

        assert response.status_code == 201
        body = response.json()
        assert body["is_active"] is True
        assert body["has_api_key"] is True
        # The key itself stays on the server, whoever asks.
        assert "geheim" not in json.dumps(body)

    async def test_a_key_that_is_not_sent_again_stays(
        self, api_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        headers = await admin_headers(api_client, session_factory)
        created = (
            await api_client.post(
                "/admin/ai/profiles",
                headers=headers,
                json={
                    "kind": "text_embedder",
                    "name": "GPU",
                    "base_url": "http://gpu:8000/v1",
                    "model": "bge-m3",
                    "api_key": "geheim",
                },
            )
        ).json()

        changed = await api_client.patch(
            f"/admin/ai/profiles/{created['id']}",
            headers=headers,
            json={"model": "bge-m3-neu"},
        )

        assert changed.json()["model"] == "bge-m3-neu"
        assert changed.json()["has_api_key"] is True

    async def test_removing_the_one_in_use_leaves_the_interface_without_a_machine(
        self, api_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        headers = await admin_headers(api_client, session_factory)
        created = (
            await api_client.post(
                "/admin/ai/profiles",
                headers=headers,
                json={
                    "kind": "image_embedder",
                    "name": "GPU",
                    "base_url": "http://gpu:8000/v1",
                    "model": "siglip2",
                },
            )
        ).json()

        removed = await api_client.delete(f"/admin/ai/profiles/{created['id']}", headers=headers)

        assert removed.status_code == 204
        assert (await api_client.get("/admin/ai/profiles", headers=headers)).json() == []

    async def test_only_admins_may_look(
        self, api_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        await create_user(session_factory, username="anna", display_name="Anna")
        headers = auth_header(await login(api_client, username="anna"))

        assert (await api_client.get("/admin/ai/profiles", headers=headers)).status_code == 403
        assert (await api_client.get("/admin/ai/profiles")).status_code == 401


async def test_a_machine_that_is_switched_off_is_given_up_on_within_seconds() -> None:
    """Connecting gets five seconds; only the answer may take the profile's time.

    A switched-off machine does not refuse, it stays silent - with the profile's two minutes as
    the limit for connecting too, every AI stage held a worker that long per medium.
    """
    limits: dict[str, float] = {}
    answer = embeddings()

    def handler(request: httpx.Request) -> httpx.Response:
        limits.update(request.extensions["timeout"])
        response: httpx.Response = answer(request)
        return response

    async with a_server(handler) as client:
        embedder = OpenAiEmbedder(
            base_url="http://gpu.zuhause:8000/v1",
            model="siglip2",
            timeout_seconds=120,
            client=client,
        )
        await embedder.embed(["eins"])

    assert limits["connect"] == 5
    assert limits["read"] == 120
