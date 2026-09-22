"""What a worker process needs to talk to the database.

Celery tasks are synchronous, the services are not. Each worker process keeps one event loop and
one engine on it, so a task does not pay for a new connection pool every time.
"""

import asyncio
from collections.abc import AsyncIterator, Coroutine
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from muninn.core.config import get_settings
from muninn.core.db import create_engine, create_session_factory

_loop: asyncio.AbstractEventLoop | None = None
_engine: AsyncEngine | None = None
_sessions: async_sessionmaker[AsyncSession] | None = None


def run[T](coroutine: Coroutine[Any, Any, T]) -> T:
    """Run one coroutine on this process's loop."""
    global _loop
    if _loop is None:
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
    return _loop.run_until_complete(coroutine)


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    global _engine, _sessions
    if _sessions is None:
        _engine = create_engine(get_settings().database_url)
        _sessions = create_session_factory(_engine)

    async with _sessions() as session:
        yield session


def shutdown() -> None:
    """Close what the process opened. Called when the worker stops."""
    global _loop, _engine, _sessions
    if _engine is not None and _loop is not None:
        _loop.run_until_complete(_engine.dispose())
    if _loop is not None:
        _loop.close()
    _loop, _engine, _sessions = None, None, None
