"""Shared test fixtures.

Health and unit tests run without any infrastructure. Everything that touches the database uses
Muninn's own PostgreSQL image through testcontainers, because the schema depends on citext and on
the extensions of that image. Redis is faked; its only job in these tests is counting.
"""

import os
from collections.abc import AsyncIterator, Iterator

import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from muninn.core.config import Settings
from muninn.core.db import create_engine, create_session_factory
from muninn.main import create_app

POSTGRES_IMAGE = os.environ.get("MUNINN_TEST_POSTGRES_IMAGE", "muninn/postgres:local")

TEST_JWT_SECRET = "test-secret-not-used-anywhere-else"

# Settings are read the moment anything imports them, and Alembic's env.py does. Defaults go in
# before that, so a single test file runs the same way as the whole suite.
# Hashing at the real cost would add several seconds to every run without testing anything
# that the cheap parameters do not also test.
os.environ.setdefault("MUNINN_PASSWORD_HASHING_IS_CHEAP", "1")
os.environ.setdefault("MUNINN_JWT_SECRET", TEST_JWT_SECRET)
os.environ.setdefault("MUNINN_REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault(
    "MUNINN_DATABASE_URL", "postgresql+asyncpg://muninn:muninn@localhost:5432/muninn"
)


# --- without infrastructure ---------------------------------------------------


@pytest.fixture
def settings() -> Settings:
    return Settings(
        database_url="postgresql+asyncpg://muninn:muninn@localhost:5432/muninn",
        redis_url="redis://localhost:6379/0",
        jwt_secret=TEST_JWT_SECRET,
    )


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """A client that does not run the lifespan, so nothing connects."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


# --- with a real database -----------------------------------------------------


@pytest.fixture(scope="session")
def sync_database_url() -> Iterator[str]:
    """A throwaway PostgreSQL on Muninn's image, as a synchronous URL."""
    testcontainers = pytest.importorskip("testcontainers.postgres")
    try:
        container = testcontainers.PostgresContainer(POSTGRES_IMAGE, driver="psycopg")
        container.start()
    except Exception as error:  # pragma: no cover - depends on the machine, not on our code
        pytest.skip(f"cannot start {POSTGRES_IMAGE}: {error}")

    try:
        yield container.get_connection_url()
    finally:
        container.stop()


@pytest.fixture(scope="session")
def database_url(sync_database_url: str) -> str:
    return sync_database_url.replace("+psycopg", "+asyncpg")


@pytest.fixture(scope="session")
def migrated_database(database_url: str) -> str:
    """Bring the throwaway database to the current schema, once for the whole session."""
    from alembic import command
    from alembic.config import Config

    from muninn.core.config import get_settings

    os.environ["MUNINN_DATABASE_URL"] = database_url
    get_settings.cache_clear()

    command.upgrade(Config("alembic.ini"), "head")
    return database_url


@pytest.fixture(scope="session")
def db_settings(migrated_database: str) -> Settings:
    return Settings(
        database_url=migrated_database,
        redis_url="redis://localhost:6379/0",
        jwt_secret=TEST_JWT_SECRET,
        refresh_cookie_secure=False,
    )


@pytest.fixture(scope="session")
async def engine(db_settings: Settings) -> AsyncIterator[AsyncEngine]:
    engine = create_engine(db_settings.database_url)
    yield engine
    await engine.dispose()


@pytest.fixture(scope="session")
def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return create_session_factory(engine)


@pytest.fixture(autouse=True)
async def clean_tables(request: pytest.FixtureRequest) -> AsyncIterator[None]:
    """Every database test starts on empty tables."""
    if "api_client" not in request.fixturenames and "session" not in request.fixturenames:
        yield
        return

    engine: AsyncEngine = request.getfixturevalue("engine")
    async with engine.begin() as connection:
        await connection.execute(
            sa.text(
                "TRUNCATE users, refresh_tokens, settings, publications, albums, media,"
                " media_files, pending_files, change_log, ai_profiles, image_embeddings,"
                " caption_embeddings, media_analyses, video_frames, media_transcripts, likes,"
                " favorites, comments, comment_mentions, notifications, notification_settings,"
                " duplicate_groups, duplicate_members, memories, memory_media, persons, faces,"
                " face_rejections,"
                " places"
                " CASCADE"
            )
        )
    yield


@pytest.fixture
async def session(session_factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session


@pytest.fixture
def fake_redis() -> object:
    from fakeredis import FakeAsyncRedis

    return FakeAsyncRedis(decode_responses=True)


@pytest.fixture
def api_app(
    db_settings: Settings,
    engine: AsyncEngine,
    session_factory: async_sessionmaker[AsyncSession],
    fake_redis: object,
) -> FastAPI:
    app = create_app(db_settings)
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.redis = fake_redis
    return app


@pytest.fixture
async def api_client(api_app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=api_app)
    async with AsyncClient(transport=transport, base_url="http://test/api/v1") as client:
        yield client


# --- collection ---------------------------------------------------------------

DATABASE_FIXTURES = frozenset(
    {
        "api_app",
        "api_client",
        "database_url",
        "db_settings",
        "engine",
        "migrated_database",
        "session",
        "session_factory",
        "sync_database_url",
    }
)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Mark every test that needs the PostgreSQL container, so `-m "not database"` can skip it.

    Tests say what they need through their fixtures; repeating that in a decorator would only be
    one more thing to forget.
    """
    for item in items:
        fixtures = getattr(item, "fixturenames", ())
        if DATABASE_FIXTURES.intersection(fixtures):
            item.add_marker("database")
