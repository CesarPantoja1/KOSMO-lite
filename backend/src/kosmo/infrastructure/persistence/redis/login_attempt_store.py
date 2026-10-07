from redis.asyncio import Redis

_ATTEMPTS_PREFIX = "auth:login_attempts:"
_WINDOW_SECONDS = 900
_MAX_FAILURES = 10


class RedisLoginAttemptStore:
    def __init__(self, client: Redis) -> None:
        self._client = client

    async def record_failure(self, identifier: str) -> None:
        key = _ATTEMPTS_PREFIX + identifier
        async with self._client.pipeline(transaction=True) as pipe:
            pipe.incr(key)
            pipe.expire(key, _WINDOW_SECONDS)
            await pipe.execute()

    async def clear(self, identifier: str) -> None:
        await self._client.delete(_ATTEMPTS_PREFIX + identifier)

    async def lockout_seconds(self, identifier: str) -> int | None:
        key = _ATTEMPTS_PREFIX + identifier
        raw = await self._client.get(key)
        if raw is None:
            return None
        count = int(raw)
        if count >= _MAX_FAILURES:
            ttl = int(await self._client.ttl(key))
            return ttl if ttl > 0 else None
        return None
