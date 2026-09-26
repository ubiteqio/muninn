"""FastAPI application factory and process lifespan."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from muninn import __version__
from muninn.api.health import router as health_router
from muninn.api.v1.ai import router as admin_ai_router
from muninn.api.v1.albums import router as albums_router
from muninn.api.v1.auth import router as auth_router
from muninn.api.v1.duplicates import router as duplicates_router
from muninn.api.v1.jobs import router as admin_jobs_router
from muninn.api.v1.library import router as admin_library_router
from muninn.api.v1.live import router as live_router
from muninn.api.v1.media import router as media_router
from muninn.api.v1.memories import router as memories_router
from muninn.api.v1.notify import router as notify_router
from muninn.api.v1.people import admin_router as admin_faces_router
from muninn.api.v1.people import router as people_router
from muninn.api.v1.places import places_router
from muninn.api.v1.places import router as map_router
from muninn.api.v1.report import router as report_router
from muninn.api.v1.search import router as search_router
from muninn.api.v1.settings import router as admin_settings_router
from muninn.api.v1.smarts import router as smarts_router
from muninn.api.v1.social import router as social_router
from muninn.api.v1.users import admin_router as admin_users_router
from muninn.api.v1.users import me_router
from muninn.core.config import Settings, get_settings
from muninn.core.db import create_engine, create_session_factory
from muninn.core.problem import register_exception_handlers
from muninn.core.redis import create_redis

API_PREFIX = "/api/v1"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Open the shared connections once per process and close them on shutdown."""
    settings: Settings = app.state.settings

    engine = create_engine(settings.database_url)
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)
    app.state.redis = create_redis(settings.redis_url)
    # One client for the AI machine, kept open. A search asks it twice, and building a client
    # for each of those threw the connection away every time: a handshake before every word
    # that is looked up. The workers keep their own; this one belongs to the API.
    app.state.ai_client = httpx.AsyncClient()

    try:
        yield
    finally:
        await app.state.ai_client.aclose()
        await app.state.redis.aclose()
        await engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(level=settings.log_level.upper())

    app = FastAPI(
        title="Muninn",
        version=__version__,
        summary="Self-hosted photo and video library",
        openapi_url=f"{API_PREFIX}/openapi.json",
        docs_url=f"{API_PREFIX}/docs",
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.settings = settings

    # The phone's app is its own origin and has to be let in by name; the web app is served
    # from here and never needs this.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(auth_router, prefix=API_PREFIX)
    app.include_router(me_router, prefix=API_PREFIX)
    app.include_router(admin_users_router, prefix=API_PREFIX)
    app.include_router(admin_settings_router, prefix=API_PREFIX)
    app.include_router(admin_ai_router, prefix=API_PREFIX)
    app.include_router(admin_library_router, prefix=API_PREFIX)
    app.include_router(admin_jobs_router, prefix=API_PREFIX)
    app.include_router(duplicates_router, prefix=API_PREFIX)
    app.include_router(admin_faces_router, prefix=API_PREFIX)
    app.include_router(report_router, prefix=API_PREFIX)
    app.include_router(albums_router, prefix=API_PREFIX)
    app.include_router(search_router, prefix=API_PREFIX)
    app.include_router(map_router, prefix=API_PREFIX)
    app.include_router(places_router, prefix=API_PREFIX)
    app.include_router(memories_router, prefix=API_PREFIX)
    app.include_router(smarts_router, prefix=API_PREFIX)
    app.include_router(social_router, prefix=API_PREFIX)
    # After social: /people/mentionable is one of its paths, not a person's id.
    app.include_router(people_router, prefix=API_PREFIX)
    app.include_router(notify_router, prefix=API_PREFIX)
    app.include_router(media_router, prefix=API_PREFIX)
    app.include_router(live_router, prefix=API_PREFIX)

    return app
