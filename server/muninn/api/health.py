"""Health endpoints for Docker. These live outside /api/v1 and need no authentication."""

import logging

from fastapi import APIRouter, Request, Response
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from muninn.api.schemas.health import HealthResponse, ReadyResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health", summary="Liveness probe")
async def health() -> HealthResponse:
    return HealthResponse()


@router.get("/ready", summary="Readiness probe")
async def ready(request: Request, response: Response) -> ReadyResponse:
    engine: AsyncEngine = request.app.state.engine
    redis: Redis = request.app.state.redis

    database_ok = await _check_database(engine)
    redis_ok = await _check_redis(redis)

    if not (database_ok and redis_ok):
        response.status_code = 503
        return ReadyResponse(status="unready", database=database_ok, redis=redis_ok)
    return ReadyResponse(status="ready", database=True, redis=True)


async def _check_database(engine: AsyncEngine) -> bool:
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception:
        logger.warning("database is not reachable", exc_info=True)
        return False
    return True


async def _check_redis(redis: Redis) -> bool:
    try:
        await redis.ping()
    except Exception:
        logger.warning("redis is not reachable", exc_info=True)
        return False
    return True
