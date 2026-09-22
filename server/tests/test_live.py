"""The live channel: events reach an open page in the moment they happen."""

import asyncio
import json
from collections.abc import MutableMapping
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from muninn.models.user import UserRole
from muninn.notify import events
from tests.helpers import create_user, login

pytestmark = pytest.mark.usefixtures("api_client")


class Socket:
    """A WebSocket client that speaks ASGI to the app, without a server in between."""

    def __init__(self, app: FastAPI, token: str | None) -> None:
        self.app = app
        self.token = token
        self.incoming: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.outgoing: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.task: asyncio.Task[None] | None = None

    async def __aenter__(self) -> "Socket":
        offered = ["bearer", self.token] if self.token else []
        headers = [(b"sec-websocket-protocol", ", ".join(offered).encode())] if offered else []
        scope = {
            "type": "websocket",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "scheme": "ws",
            "http_version": "1.1",
            "path": "/api/v1/ws",
            "raw_path": b"/api/v1/ws",
            "query_string": b"",
            "root_path": "",
            "headers": headers,
            "subprotocols": offered,
            "client": ("test", 1),
            "server": ("test", 80),
        }
        await self.incoming.put({"type": "websocket.connect"})

        async def send(message: MutableMapping[str, Any]) -> None:
            await self.outgoing.put(dict(message))

        self.task = asyncio.create_task(self.app(scope, self.incoming.get, send))
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.incoming.put({"type": "websocket.disconnect", "code": 1000})
        if self.task:
            self.task.cancel()

    async def next(self) -> dict[str, Any]:
        """The next thing the app sent, or a failure rather than a test that hangs."""
        assert self.task is not None
        getter = asyncio.ensure_future(self.outgoing.get())
        done, _ = await asyncio.wait(
            {getter, self.task}, timeout=3, return_when=asyncio.FIRST_COMPLETED
        )
        if getter in done:
            return getter.result()
        getter.cancel()
        if self.task in done:
            self.task.result()
        raise AssertionError("the app sent nothing")


async def token_of(
    api_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    *,
    username: str,
    role: UserRole = UserRole.ADMIN,
) -> str:
    await create_user(session_factory, username=username, display_name=username, role=role)
    tokens = await login(api_client, username=username)
    return str(tokens["access_token"])


async def test_an_event_reaches_an_open_page(
    api_client: AsyncClient,
    api_app: FastAPI,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    token = await token_of(api_client, session_factory, username="admin")

    async with Socket(api_app, token) as socket:
        assert (await socket.next())["type"] == "websocket.accept"

        # Whatever a worker publishes, the page hears - no second question in between.
        await events.publish(api_app.state.redis, "jobs", kind="task_finished", stage="derive")
        message = await socket.next()

    assert message["type"] == "websocket.send"
    assert json.loads(message["text"])["kind"] == "task_finished"


async def test_a_socket_without_a_token_is_closed(
    api_client: AsyncClient,
    api_app: FastAPI,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with Socket(api_app, None) as socket:
        message = await socket.next()

    assert message["type"] == "websocket.close"


async def test_a_made_up_token_is_closed(
    api_client: AsyncClient,
    api_app: FastAPI,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with Socket(api_app, "not-a-token") as socket:
        message = await socket.next()

    assert message["type"] == "websocket.close"


async def test_the_engine_room_is_not_for_everybody(
    api_client: AsyncClient,
    api_app: FastAPI,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A plain user may listen, but the jobs topic names files on the NAS."""
    token = await token_of(api_client, session_factory, username="anna", role=UserRole.USER)

    async with Socket(api_app, token) as socket:
        assert (await socket.next())["type"] == "websocket.accept"

        await events.publish(api_app.state.redis, "jobs", kind="task_finished", stage="derive")
        await events.publish(api_app.state.redis, "albums", kind="album_added")
        message = await socket.next()

    assert json.loads(message["text"])["topic"] == "albums"


async def test_a_bell_ping_reaches_only_whom_it_is_for(
    api_client: AsyncClient,
    api_app: FastAPI,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Nobody else learns that somebody got a notification, nor who else did."""
    from sqlalchemy import select

    from muninn.models.user import User

    anna = await token_of(api_client, session_factory, username="anna", role=UserRole.USER)
    boris = await token_of(api_client, session_factory, username="boris", role=UserRole.USER)
    async with session_factory() as session:
        boris_id = await session.scalar(select(User.id).where(User.username == "boris"))
    assert boris_id is not None

    async with Socket(api_app, anna) as annas, Socket(api_app, boris) as boriss:
        assert (await annas.next())["type"] == "websocket.accept"
        assert (await boriss.next())["type"] == "websocket.accept"

        await events.announce_notifications(api_app.state.redis, [boris_id])
        await events.publish(api_app.state.redis, "albums", kind="album_added")
        for_anna = json.loads((await annas.next())["text"])
        for_boris = json.loads((await boriss.next())["text"])

    assert for_anna["topic"] == "albums"
    assert for_boris["topic"] == "notifications"
    assert "recipients" not in for_boris
