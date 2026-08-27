from __future__ import annotations

import logging
import threading
import time
from collections import deque

from app.core.config import get_settings
from app.core.redis import RedisError, get_redis_client, rate_limit_check

logger = logging.getLogger(__name__)

LOGIN_ATTEMPTS_PREFIX = 'login_attempts:'
LOGIN_BLOCKED_PREFIX = 'login_blocked:'


class _LoginRateLimiter:
    """In-memory sliding-window limiter for failed login attempts.

    The counter is keyed by an identifier (email and/or IP). Once the number
    of failed attempts within the configured window reaches the limit, the
    identifier is blocked for the configured block duration. A successful
    login resets the counter.

    This is a development/test-friendly in-memory implementation; the
    interface is intentionally simple so a Redis-based backend can be added
    later without changing callers.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state: dict[str, deque[float]] = {}
        self._blocked_until: dict[str, float] = {}

    def _prune(self, key: str, now: float) -> None:
        settings = get_settings()
        window = settings.LOGIN_ATTEMPT_WINDOW_MINUTES * 60.0
        attempts = self._state.get(key)
        if attempts is None:
            return
        while attempts and attempts[0] <= now - window:
            attempts.popleft()
        if not attempts:
            self._state.pop(key, None)

    def check_blocked(self, key: str, now: float | None = None) -> int | None:
        """Return remaining blocked seconds for the key, or None if allowed."""
        now = time.monotonic() if now is None else now
        with self._lock:
            blocked_until = self._blocked_until.get(key)
            if blocked_until is not None and now < blocked_until:
                return max(1, int(blocked_until - now))

            settings = get_settings()
            self._prune(key, now)
            attempts = self._state.get(key)
            if (
                attempts is not None
                and len(attempts) >= settings.LOGIN_MAX_ATTEMPTS
            ):
                self._blocked_until[key] = (
                    now + settings.LOGIN_BLOCK_DURATION_MINUTES * 60.0
                )
                return max(
                    1, int(settings.LOGIN_BLOCK_DURATION_MINUTES * 60.0)
                )

            self._blocked_until.pop(key, None)
            return None

    def register_failed_attempt(
        self, key: str, now: float | None = None
    ) -> bool:
        now = time.monotonic() if now is None else now
        with self._lock:
            attempts = self._state.setdefault(key, deque())
            was_already_blocked = (
                key in self._blocked_until and now < self._blocked_until[key]
            )
            attempts.append(now)
            settings = get_settings()
            self._prune(key, now)
            if len(attempts) >= settings.LOGIN_MAX_ATTEMPTS:
                self._blocked_until[key] = (
                    now + settings.LOGIN_BLOCK_DURATION_MINUTES * 60.0
                )
                return not was_already_blocked
            return False

    def reset_attempts(self, key: str) -> None:
        with self._lock:
            self._state.pop(key, None)
            self._blocked_until.pop(key, None)

    def prune_all_stale(self, now: float | None = None) -> int:
        """Purge all expired login attempt counters and unblocked keys."""
        now = time.monotonic() if now is None else now
        pruned_count = 0
        with self._lock:
            for key in list(self._state.keys()):
                self._prune(key, now)
                if key not in self._state:
                    pruned_count += 1
            for key, blocked_until in list(self._blocked_until.items()):
                if now >= blocked_until:
                    self._blocked_until.pop(key, None)
        return pruned_count

    def clear(self) -> None:
        with self._lock:
            self._state.clear()
            self._blocked_until.clear()


rate_limiter = _LoginRateLimiter()


def build_email_login_key(email: str) -> str:
    return f'email:{email.strip().lower()}'


def build_ip_login_key(client_ip: str) -> str:
    return f'ip:{client_ip.strip()}'


def build_login_key(email: str, client_ip: str | None = None) -> str:
    identifier = email.strip().lower()
    if client_ip:
        return f'{client_ip}|{identifier}'
    return identifier


def check_login_blocked(key: str, now: float | None = None) -> int | None:
    return rate_limiter.check_blocked(key, now)


def register_failed_login(key: str, now: float | None = None) -> bool:
    return rate_limiter.register_failed_attempt(key, now)


def reset_login_attempts(key: str) -> None:
    rate_limiter.reset_attempts(key)


async def check_login_blocked_async(
    key: str, now: float | None = None
) -> int | None:
    """Return remaining blocked seconds for the key, or None if allowed.

    Checks Redis first if configured; falls back to in-memory limiter on failure
    or if Redis is not active.
    """
    client = get_redis_client()
    if client:
        try:
            blocked_key = f'{LOGIN_BLOCKED_PREFIX}{key}'
            ttl = await client.ttl(blocked_key)
            if ttl > 0:
                return ttl

            attempts_key = f'{LOGIN_ATTEMPTS_PREFIX}{key}'
            raw_attempts = await client.get(attempts_key)
            if raw_attempts is not None:
                settings = get_settings()
                if int(raw_attempts) >= settings.LOGIN_MAX_ATTEMPTS:
                    block_ttl = int(settings.LOGIN_BLOCK_DURATION_MINUTES * 60)
                    await client.setex(blocked_key, block_ttl, '1')
                    return block_ttl
            return None
        except RedisError as e:
            logger.warning(
                'Redis login rate limit check failed for %s: %s', key, e
            )

    return rate_limiter.check_blocked(key, now)


async def register_failed_login_async(
    key: str, now: float | None = None
) -> bool:
    """Register a failed login attempt for key.

    Returns True if this failed attempt just triggered a new lockout.
    Updates Redis if configured, and updates in-memory fallback state.
    """
    mem_just_locked = rate_limiter.register_failed_attempt(key, now)

    client = get_redis_client()
    if client:
        try:
            settings = get_settings()
            window_seconds = int(settings.LOGIN_ATTEMPT_WINDOW_MINUTES * 60)
            block_duration_seconds = int(
                settings.LOGIN_BLOCK_DURATION_MINUTES * 60
            )

            attempts_key = f'{LOGIN_ATTEMPTS_PREFIX}{key}'
            count = await client.incr(attempts_key)
            if count == 1:
                await client.expire(attempts_key, window_seconds)

            if count >= settings.LOGIN_MAX_ATTEMPTS:
                blocked_key = f'{LOGIN_BLOCKED_PREFIX}{key}'
                already_blocked = await client.get(blocked_key) is not None
                await client.setex(blocked_key, block_duration_seconds, '1')
                return not already_blocked
        except RedisError as e:
            logger.warning(
                'Redis register failed login failed for %s: %s', key, e
            )
            return mem_just_locked

    return mem_just_locked


async def reset_login_attempts_async(key: str) -> None:
    """Reset failed login attempts and unblock key in Redis and in-memory."""
    rate_limiter.reset_attempts(key)

    client = get_redis_client()
    if client:
        try:
            attempts_key = f'{LOGIN_ATTEMPTS_PREFIX}{key}'
            blocked_key = f'{LOGIN_BLOCKED_PREFIX}{key}'
            await client.delete(attempts_key, blocked_key)
        except RedisError as e:
            logger.warning(
                'Redis reset login attempts failed for %s: %s', key, e
            )


class _RequestRateLimiter:
    """In-memory sliding-window limiter for generic request counting.

    Each ``scope`` (a route group such as ``RATE_LIMIT_REGISTER``) counts
    requests per identifier (client IP and/or authenticated user). When the
    number of requests within the configured window reaches the limit, the
    next request is rejected with an HTTP 429 and a ``Retry-After`` estimate.

    In-memory state is per-process: with multiple app instances each keeps
    its own counters. A Redis-based backend should replace this for
    multi-instance deployments.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._events: dict[str, deque[float]] = {}

    def _prune(self, key: str, window_seconds: float, now: float) -> None:
        events = self._events.get(key)
        if events is None:
            return
        while events and events[0] <= now - window_seconds:
            events.popleft()
        if not events:
            self._events.pop(key, None)

    def check_and_consume(
        self,
        key: str,
        limit: int,
        window_seconds: float,
        now: float | None = None,
    ) -> int | None:
        """Record one request; return ``Retry-After`` seconds if over the limit.

        Returns ``None`` when the request is within the limit (and consumes
        it). The key stays blocked until the oldest event leaves the window.
        """
        now = time.monotonic() if now is None else now
        with self._lock:
            self._prune(key, window_seconds, now)
            events = self._events.setdefault(key, deque())
            if len(events) >= limit:
                retry_after = events[0] + window_seconds - now
                return max(1, int(retry_after) + 1)
            events.append(now)
            return None

    def prune_all_stale(
        self, window_seconds: float, now: float | None = None
    ) -> int:
        """Purge all expired events across tracked keys."""
        now = time.monotonic() if now is None else now
        pruned_count = 0
        with self._lock:
            for key in list(self._events.keys()):
                self._prune(key, window_seconds, now)
                if key not in self._events:
                    pruned_count += 1
        return pruned_count

    def reset(self, key: str) -> None:
        with self._lock:
            self._events.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._events.clear()


request_rate_limiter = _RequestRateLimiter()


# Redis-backed rate limiter functions (used when Redis is configured)
async def redis_check_and_consume(
    key: str,
    limit: int,
    window_seconds: int,
) -> int | None:
    """Redis-backed rate limit check. Falls back to in-memory if Redis unavailable."""
    return await rate_limit_check(key, limit, window_seconds)


async def redis_reset(key: str) -> None:
    """Reset a Redis rate limit key."""
    client = get_redis_client()
    if client:
        try:
            await client.delete(key)
        except RedisError:
            pass  # Best effort


_TIME_UNITS = {
    'second': 1.0,
    'minute': 60.0,
    'hour': 3600.0,
    'day': 86400.0,
}


def parse_rate_limit(value: str) -> tuple[int, float]:
    """Parse a ``"N/timeunit"`` limit into ``(count, window_seconds)``.

    Units: ``second``, ``minute``, ``hour``, ``day`` (or their ``s``
    plural forms). Examples: ``"10/minute"``, ``"100/hour"``, ``"2/second"``.
    """
    count_str, _, unit = value.strip().replace(' ', '').partition('/')
    if not count_str or not unit:
        raise ValueError(f'Invalid rate limit format: {value!r}')

    try:
        count = int(count_str)
    except ValueError:
        raise ValueError(f'Invalid rate limit count: {value!r}') from None

    normalized_unit = unit.lower()
    if normalized_unit.endswith('s') and normalized_unit != 's':
        normalized_unit = normalized_unit[:-1]

    if normalized_unit not in _TIME_UNITS:
        raise ValueError(f'Unsupported rate limit unit: {value!r}')
    if count <= 0:
        raise ValueError(f'Rate limit count must be positive: {value!r}')

    return count, _TIME_UNITS[normalized_unit]
