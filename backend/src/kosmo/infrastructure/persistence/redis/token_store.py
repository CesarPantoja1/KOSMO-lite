import asyncio
import json
from datetime import datetime

import structlog
from redis.asyncio import Redis

from kosmo.contracts.auth import IssuedToken, RefreshConsumeResult, TokenPair, TokenType

_log = structlog.get_logger("kosmo.auth.token_store")

_REFRESH_PREFIX = "auth:refresh:"
_REVOKED_ACCESS_PREFIX = "auth:revoked:access:"
_FAMILY_PREFIX = "auth:family:"
_GRACE_PREFIX = "auth:grace:"
_FAMILY_SEPARATOR = "|"

_GRACE_POLL_INTERVAL_SECONDS: float = 0.05
_GRACE_POLL_MAX_ATTEMPTS: int = 30


class RedisTokenRevocationStore:
    def __init__(self, client: Redis) -> None:
        self._client = client

    async def register_refresh(
        self,
        *,
        jti: str,
        subject: str,
        ttl_seconds: int,
        family_id: str | None = None,
    ) -> None:
        if ttl_seconds <= 0:
            return
        value = subject if family_id is None else f"{subject}{_FAMILY_SEPARATOR}{family_id}"
        async with self._client.pipeline(transaction=True) as pipe:
            pipe.set(_REFRESH_PREFIX + jti, value, ex=ttl_seconds)
            if family_id is not None:
                pipe.set(_FAMILY_PREFIX + family_id, subject, ex=ttl_seconds)
            await pipe.execute()

    async def consume_refresh(self, *, jti: str) -> RefreshConsumeResult | None:
        key = _REFRESH_PREFIX + jti
        grace_key = _GRACE_PREFIX + jti
        async with self._client.pipeline(transaction=True) as pipe:
            pipe.get(key)
            pipe.delete(key)
            pipe.set(grace_key, "ROTATING", ex=30)
            res = await pipe.execute()
        stored = res[0]
        if stored is None:
            await self._client.delete(grace_key)
            return None
        raw = stored.decode("utf-8") if isinstance(stored, bytes) else str(stored)
        if _FAMILY_SEPARATOR in raw:
            parts = raw.split(_FAMILY_SEPARATOR, 1)
            return RefreshConsumeResult(subject=str(parts[0]), family_id=str(parts[1]))
        return RefreshConsumeResult(subject=raw, family_id=None)

    async def store_grace_period(
        self,
        *,
        old_jti: str,
        token_pair: TokenPair,
        ttl_seconds: int = 30,
    ) -> None:
        if ttl_seconds <= 0:
            return
        payload = json.dumps(
            {
                "access_token": token_pair.access.token,
                "access_jti": token_pair.access.jti,
                "access_expires_at": token_pair.access.expires_at.isoformat(),
                "access_family_id": token_pair.access.family_id,
                "refresh_token": token_pair.refresh.token,
                "refresh_jti": token_pair.refresh.jti,
                "refresh_expires_at": token_pair.refresh.expires_at.isoformat(),
                "refresh_family_id": token_pair.refresh.family_id,
            }
        )
        await self._client.set(_GRACE_PREFIX + old_jti, payload, ex=ttl_seconds)

    async def get_grace_period(self, *, old_jti: str) -> TokenPair | None:
        key = _GRACE_PREFIX + old_jti
        for _ in range(_GRACE_POLL_MAX_ATTEMPTS):
            raw = await self._client.get(key)
            if raw is None:
                return None
            val = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
            if val == "ROTATING":
                await asyncio.sleep(_GRACE_POLL_INTERVAL_SECONDS)
                continue
            try:
                data = json.loads(val)
                return TokenPair(
                    access=IssuedToken(
                        token=str(data["access_token"]),
                        jti=str(data["access_jti"]),
                        expires_at=datetime.fromisoformat(str(data["access_expires_at"])),
                        token_type=TokenType.ACCESS,
                        family_id=data.get("access_family_id"),
                    ),
                    refresh=IssuedToken(
                        token=str(data["refresh_token"]),
                        jti=str(data["refresh_jti"]),
                        expires_at=datetime.fromisoformat(str(data["refresh_expires_at"])),
                        token_type=TokenType.REFRESH,
                        family_id=data.get("refresh_family_id"),
                    ),
                )
            except (json.JSONDecodeError, KeyError):
                return None

        _log.warning(
            "token_store.grace_period_timeout_still_rotating",
            old_jti=old_jti,
            waited_seconds=_GRACE_POLL_MAX_ATTEMPTS * _GRACE_POLL_INTERVAL_SECONDS,
        )
        return None

    async def revoke_access(self, *, jti: str, ttl_seconds: int) -> None:
        if ttl_seconds <= 0:
            return
        await self._client.set(_REVOKED_ACCESS_PREFIX + jti, "1", ex=ttl_seconds)

    async def is_access_revoked(self, *, jti: str) -> bool:
        return bool(await self._client.exists(_REVOKED_ACCESS_PREFIX + jti))

    async def revoke_refresh(self, *, jti: str) -> None:
        await self._client.delete(_REFRESH_PREFIX + jti)

    async def is_family_alive(self, *, family_id: str) -> bool:
        return bool(await self._client.exists(_FAMILY_PREFIX + family_id))

    async def revoke_family(self, *, family_id: str) -> None:
        await self._client.delete(_FAMILY_PREFIX + family_id)
