"""Live events, carried between the workers and the open pages by Redis.

A worker cannot reach a browser, and the API process that holds the socket is not the process
doing the work. Redis is already there for the queues, and its publish/subscribe delivers to
whoever happens to be listening without keeping anything - which is exactly right for events
that are only interesting the moment they happen.
"""

import json
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from redis.asyncio import Redis

#: One channel for everything. Each event names its own topic, so a listener can pick.
CHANNEL = "muninn:events"

#: How long to wait for the next event before looking after the socket itself.
POLL_SECONDS = 1.0


#: What every signed-in user may hear: only that the albums changed, never which files.
LIBRARY_TOPIC = "library"

#: Likes and, later, comments: who did what is visible to everybody signed in anyway.
SOCIAL_TOPIC = "social"

#: The faces were looked at again, so who is known and what is still being asked has moved. The
#: Personen screen answers a list of questions; it must not be a list from ten minutes ago.
PEOPLE_TOPIC = "people"


async def publish(redis: Redis, topic: str, **payload: Any) -> None:
    """Tell whoever is listening that something happened. Nobody listening is not an error."""
    event = {"topic": topic, "at": datetime.now(UTC).isoformat(), **payload}
    await redis.publish(CHANNEL, json.dumps(event))


async def listen(redis: Redis) -> AsyncIterator[dict[str, Any]]:
    """Every event as it arrives, until the caller stops asking."""
    pubsub = redis.pubsub()
    await pubsub.subscribe(CHANNEL)
    try:
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=POLL_SECONDS)
            if message is None:
                continue
            data = message.get("data")
            if data is None:
                continue
            parsed: dict[str, Any] = json.loads(data)
            yield parsed
    finally:
        await pubsub.unsubscribe(CHANNEL)
        # aclose() carries no annotations in redis-py.
        await pubsub.aclose()  # type: ignore[no-untyped-call]


#: A ping for the bell. Carries only whom it is for; the live channel hands it to them alone.
NOTIFICATIONS_TOPIC = "notifications"


async def announce_notifications(redis: Redis, recipients: list[uuid.UUID]) -> None:
    """Tell these people's open apps that the bell has something new."""
    if recipients:
        await publish(
            redis,
            NOTIFICATIONS_TOPIC,
            kind="new",
            recipients=[str(user_id) for user_id in recipients],
        )
