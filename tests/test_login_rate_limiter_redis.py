"""Unit tests for Redis-backed login rate limiter with in-memory fallback."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from redis.exceptions import RedisError

from app.core.security.rate_limiter import (
    LOGIN_ATTEMPTS_PREFIX,
    LOGIN_BLOCKED_PREFIX,
    check_login_blocked_async,
    rate_limiter,
    register_failed_login_async,
    reset_login_attempts_async,
)


@pytest.fixture(autouse=True)
def _clean_memory_rate_limiter():
    rate_limiter.clear()
    yield
    rate_limiter.clear()


@pytest.mark.asyncio
async def test_fallback_to_memory_when_redis_client_none() -> None:
    """When get_redis_client() is None, rate limiter falls back to in-memory implementation."""
    key = 'fallback_none@example.com'
    with patch('app.core.rate_limiter.get_redis_client', return_value=None):
        for _ in range(4):
            await register_failed_login_async(key)
        assert await check_login_blocked_async(key) is None

        await register_failed_login_async(key)
        blocked = await check_login_blocked_async(key)
        assert blocked is not None
        assert blocked > 0

        await reset_login_attempts_async(key)
        assert await check_login_blocked_async(key) is None


@pytest.mark.asyncio
async def test_redis_login_attempts_tracking_and_blocking() -> None:
    """When Redis is available, attempts and blocking are handled via Redis keys."""
    mock_redis = AsyncMock()
    attempts_store: dict[str, str] = {}
    ttl_store: dict[str, int] = {}

    async def mock_incr(key: str) -> int:
        current = int(attempts_store.get(key, 0)) + 1
        attempts_store[key] = str(current)
        return current

    async def mock_get(key: str) -> str | None:
        return attempts_store.get(key)

    async def mock_ttl(key: str) -> int:
        return ttl_store.get(key, -2)

    async def mock_setex(key: str, seconds: int, value: str) -> None:
        attempts_store[key] = value
        ttl_store[key] = seconds

    async def mock_delete(*keys: str) -> int:
        deleted = 0
        for k in keys:
            if k in attempts_store or k in ttl_store:
                attempts_store.pop(k, None)
                ttl_store.pop(k, None)
                deleted += 1
        return deleted

    mock_redis.incr.side_effect = mock_incr
    mock_redis.get.side_effect = mock_get
    mock_redis.ttl.side_effect = mock_ttl
    mock_redis.setex.side_effect = mock_setex
    mock_redis.delete.side_effect = mock_delete
    mock_redis.expire = AsyncMock()

    key = 'redis_test@example.com'
    blocked_key = f'{LOGIN_BLOCKED_PREFIX}{key}'
    attempts_key = f'{LOGIN_ATTEMPTS_PREFIX}{key}'

    with patch(
        'app.core.rate_limiter.get_redis_client', return_value=mock_redis
    ):
        for _ in range(4):
            await register_failed_login_async(key)
        assert await check_login_blocked_async(key) is None

        # 5th attempt triggers block
        await register_failed_login_async(key)
        mock_redis.setex.assert_called_with(blocked_key, 1800, '1')

        blocked = await check_login_blocked_async(key)
        assert blocked == 1800

        await reset_login_attempts_async(key)
        assert attempts_key not in attempts_store
        assert blocked_key not in ttl_store


@pytest.mark.asyncio
async def test_fallback_on_redis_error() -> None:
    """When Redis operations raise RedisError, fallback smoothly to in-memory state."""
    mock_redis = AsyncMock()
    mock_redis.ttl.side_effect = RedisError('Connection lost')
    mock_redis.incr.side_effect = RedisError('Connection lost')
    mock_redis.delete.side_effect = RedisError('Connection lost')

    key = 'redis_err@example.com'

    with patch(
        'app.core.rate_limiter.get_redis_client', return_value=mock_redis
    ):
        for _ in range(5):
            await register_failed_login_async(key)

        # Redis check raises RedisError -> falls back to in-memory, which registered 5 attempts
        blocked = await check_login_blocked_async(key)
        assert blocked is not None
        assert blocked > 0
