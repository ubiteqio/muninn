"""The container probes and the shape of our error responses."""

from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


class _StubConnection:
    def __init__(self, fail: bool) -> None:
        self._fail = fail

    async def __aenter__(self) -> "_StubConnection":
        if self._fail:
            raise ConnectionError("database is down")
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def execute(self, *args: Any, **kwargs: Any) -> None:
        return None


class _StubEngine:
    def __init__(self, fail: bool = False) -> None:
        self._fail = fail

    def connect(self) -> _StubConnection:
        return _StubConnection(self._fail)


class _StubRedis:
    def __init__(self, fail: bool = False) -> None:
        self._fail = fail

    async def ping(self) -> bool:
        if self._fail:
            raise ConnectionError("redis is down")
        return True


async def test_health_needs_no_dependencies(client: AsyncClient) -> None:
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize(
    ("database_fails", "redis_fails"),
    [(False, True), (True, False), (True, True)],
)
async def test_ready_reports_503_when_a_dependency_is_down(
    app: FastAPI, database_fails: bool, redis_fails: bool
) -> None:
    app.state.engine = _StubEngine(fail=database_fails)
    app.state.redis = _StubRedis(fail=redis_fails)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unready"
    assert body["database"] is not database_fails
    assert body["redis"] is not redis_fails


async def test_ready_is_ready_when_everything_answers(app: FastAPI) -> None:
    app.state.engine = _StubEngine()
    app.state.redis = _StubRedis()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": True, "redis": True}


async def test_unknown_route_answers_with_problem_details(client: AsyncClient) -> None:
    response = await client.get("/does-not-exist")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["title"] == "Not Found"
    assert body["status"] == 404
    assert body["instance"] == "/does-not-exist"
