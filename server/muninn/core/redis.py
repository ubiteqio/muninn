"""Redis client factory. Redis carries queues and live events."""

from redis.asyncio import Redis


def create_redis(redis_url: str) -> Redis:
    # from_url is untyped in the current release, so the annotation has to be ours.
    client: Redis = Redis.from_url(redis_url, decode_responses=True)
    return client
