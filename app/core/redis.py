"""Redis client and utilities for caching, rate limiting, and sessions."""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from typing import Any

import redis.asyncio as redis
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_redis_client: Redis | None = None


def get_redis_client() -> Redis | None:
    """Return the global Redis client, or None if not configured."""
    return _redis_client


async def init_redis() -> Redis | None:
    """Initialize Redis connection from settings."""
    global _redis_client
    settings = get_settings()

    redis_url = settings.REDIS_URL
    if not redis_url:
        logger.info("REDIS_URL not set; Redis features disabled")
        return None

    try:
        _redis_client = redis.from_url(
            redis_url,
            encoding="utf-8",
            decode_responses=True,
            max_connections=settings.REDIS_MAX_CONNECTIONS,
        )
        await _redis_client.ping()
        logger.info("Redis connected: %s", redis_url)
        return _redis_client
    except RedisError as e:
        logger.warning("Redis connection failed: %s", e)
        _redis_client = None
        return None


async def close_redis() -> None:
    """Close Redis connection."""
    global _redis_client
    if _redis_client:
        await _redis_client.close()
        _redis_client = None


@asynccontextmanager
async def redis_lifespan():
    """Context manager for Redis lifecycle."""
    await init_redis()
    try:
        yield
    finally:
        await close_redis()


# --- Cache helpers ---

async def cache_get(key: str) -> Any | None:
    """Get value from cache."""
    client = get_redis_client()
    if not client:
        return None
    try:
        data = await client.get(key)
        return json.loads(data) if data else None
    except RedisError as e:
        logger.warning("Cache get failed for %s: %s", key, e)
        return None


async def cache_set(key: str, value: Any, ttl: int = 300) -> bool:
    """Set value in cache with TTL (seconds)."""
    client = get_redis_client()
    if not client:
        return False
    try:
        await client.setex(key, ttl, json.dumps(value))
        return True
    except RedisError as e:
        logger.warning("Cache set failed for %s: %s", key, e)
        return False


async def cache_delete(key: str) -> bool:
    """Delete key from cache."""
    client = get_redis_client()
    if not client:
        return False
    try:
        await client.delete(key)
        return True
    except RedisError as e:
        logger.warning("Cache delete failed for %s: %s", key, e)
        return False


async def cache_delete_pattern(pattern: str) -> int:
    """Delete all keys matching pattern."""
    client = get_redis_client()
    if not client:
        return 0
    try:
        keys = []
        async for key in client.scan_iter(match=pattern):
            keys.append(key)
        if keys:
            return await client.delete(*keys)
        return 0
    except RedisError as e:
        logger.warning("Cache delete pattern failed for %s: %s", pattern, e)
        return 0


# --- Rate limiter helpers (Redis-backed) ---

async def rate_limit_check(key: str, limit: int, window_seconds: int) -> int | None:
    """
    Check and consume a rate limit slot.
    Returns retry_after seconds if limit exceeded, else None.
    """
    client = get_redis_client()
    if not client:
        return None  # Fallback: allow if Redis unavailable

    try:
        current = await client.incr(key)
        if current == 1:
            await client.expire(key, window_seconds)
        if current > limit:
            ttl = await client.ttl(key)
            return max(ttl, 1)
        return None
    except RedisError as e:
        logger.warning("Rate limit check failed for %s: %s", key, e)
        return None  # Fail open


# --- Session storage (for future WebSocket / multi-device) ---

SESSION_PREFIX = "session:"
SESSION_TTL = 86400 * 30  # 30 days


async def session_store(session_id: str, data: dict[str, Any], ttl: int = SESSION_TTL) -> bool:
    """Store session data."""
    return await cache_set(f"{SESSION_PREFIX}{session_id}", data, ttl)


async def session_get(session_id: str) -> dict[str, Any] | None:
    """Retrieve session data."""
    return await cache_get(f"{SESSION_PREFIX}{session_id}")


async def session_delete(session_id: str) -> bool:
    """Delete session."""
    return await cache_delete(f"{SESSION_PREFIX}{session_id}")


async def session_delete_user_sessions(user_id: str) -> int:
    """Delete all sessions for a user."""
    return await cache_delete_pattern(f"{SESSION_PREFIX}*user_id:{user_id}*")