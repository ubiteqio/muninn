"""A small counter in Redis, used to slow down password guessing."""

from dataclasses import dataclass

from redis.asyncio import Redis


@dataclass(frozen=True, slots=True)
class RateLimit:
    allowed: bool
    remaining: int
    retry_after_seconds: int


class RateLimiter:
    """Counts events per key in a fixed window. Only failures are counted, so a working login
    never locks anybody out."""

    def __init__(self, redis: Redis, *, limit: int, window_seconds: int) -> None:
        self._redis = redis
        self._limit = limit
        self._window = window_seconds

    def _key(self, scope: str, identifier: str) -> str:
        return f"muninn:ratelimit:{scope}:{identifier}"

    async def check(self, scope: str, identifier: str) -> RateLimit:
        key = self._key(scope, identifier)
        current = await self._redis.get(key)
        used = int(current) if current is not None else 0
        if used < self._limit:
            return RateLimit(allowed=True, remaining=self._limit - used, retry_after_seconds=0)

        ttl = await self._redis.ttl(key)
        return RateLimit(
            allowed=False, remaining=0, retry_after_seconds=max(ttl, 1) if ttl > 0 else self._window
        )

    async def record_failure(self, scope: str, identifier: str) -> None:
        key = self._key(scope, identifier)
        async with self._redis.pipeline(transaction=True) as pipeline:
            pipeline.incr(key)
            pipeline.expire(key, self._window, nx=True)
            await pipeline.execute()

    async def reset(self, scope: str, identifier: str) -> None:
        await self._redis.delete(self._key(scope, identifier))
