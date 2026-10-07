from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from redis.asyncio import Redis

from kosmo.infrastructure.persistence.redis.login_attempt_store import RedisLoginAttemptStore


@pytest.mark.asyncio
@pytest.mark.unit
async def test_redis_login_attempt_store_record_failure_uses_atomic_pipeline() -> None:
    # Arrange
    mock_redis = MagicMock(spec=Redis)
    mock_pipe = MagicMock()
    mock_pipe.execute = AsyncMock(return_value=[1, True])
    mock_redis.pipeline.return_value.__aenter__ = AsyncMock(return_value=mock_pipe)
    mock_redis.pipeline.return_value.__aexit__ = AsyncMock(return_value=None)

    store = RedisLoginAttemptStore(mock_redis)

    # Act
    await store.record_failure("user@example.com")

    # Assert
    mock_redis.pipeline.assert_called_once_with(transaction=True)
    mock_pipe.incr.assert_called_once_with("auth:login_attempts:user@example.com")
    mock_pipe.expire.assert_called_once_with("auth:login_attempts:user@example.com", 900)
    mock_pipe.execute.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_redis_login_attempt_store_clear() -> None:
    # Arrange
    mock_redis = MagicMock(spec=Redis)
    mock_redis.delete = AsyncMock()
    store = RedisLoginAttemptStore(mock_redis)

    # Act
    await store.clear("user@example.com")

    # Assert
    mock_redis.delete.assert_awaited_once_with("auth:login_attempts:user@example.com")


@pytest.mark.asyncio
@pytest.mark.unit
async def test_redis_login_attempt_store_lockout_seconds() -> None:
    # Arrange
    mock_redis = MagicMock(spec=Redis)
    mock_redis.get = AsyncMock()
    mock_redis.ttl = AsyncMock()
    store = RedisLoginAttemptStore(mock_redis)

    # Case 1: Key not found
    mock_redis.get.return_value = None
    assert await store.lockout_seconds("user@example.com") is None

    # Case 2: Below threshold
    mock_redis.get.return_value = b"5"
    assert await store.lockout_seconds("user@example.com") is None

    # Case 3: At or above threshold with positive TTL
    mock_redis.get.return_value = b"10"
    mock_redis.ttl.return_value = 450
    assert await store.lockout_seconds("user@example.com") == 450

    # Case 4: At threshold but TTL expired/negative
    mock_redis.get.return_value = b"10"
    mock_redis.ttl.return_value = -1
    assert await store.lockout_seconds("user@example.com") is None
