from __future__ import annotations

import threading
import time
from collections import deque

from app.core.config import get_settings


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
    ) -> None:
        now = time.monotonic() if now is None else now
        with self._lock:
            attempts = self._state.setdefault(key, deque())
            attempts.append(now)
            settings = get_settings()
            if len(attempts) >= settings.LOGIN_MAX_ATTEMPTS:
                self._blocked_until[key] = (
                    now + settings.LOGIN_BLOCK_DURATION_MINUTES * 60.0
                )

    def reset_attempts(self, key: str) -> None:
        with self._lock:
            self._state.pop(key, None)
            self._blocked_until.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._state.clear()
            self._blocked_until.clear()


rate_limiter = _LoginRateLimiter()


def build_login_key(email: str, client_ip: str | None = None) -> str:
    identifier = email.strip().lower()
    if client_ip:
        return f'{client_ip}|{identifier}'
    return identifier


def check_login_blocked(key: str, now: float | None = None) -> int | None:
    return rate_limiter.check_blocked(key, now)


def register_failed_login(key: str, now: float | None = None) -> None:
    rate_limiter.register_failed_attempt(key, now)


def reset_login_attempts(key: str) -> None:
    rate_limiter.reset_attempts(key)


class _RequestRateLimiter:
    """In-memory sliding-window limiter for generic request counting.

    Each ``scope`` (a route group such as ``RATE_LIMIT_REGISTER``) counts
    requests per identifier (client IP and/or authenticated user). When the
    number of requests within the configured window reaches the limit, the
    next request is rejected with an HTTP 429 and a ``Retry-After`` estimate.

    In-memory state is per-process: with multiple app instances each keeps
    its own counters. A Redis-based backend should replace this for
    multi-instance deployments (see README).
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

    def reset(self, key: str) -> None:
        with self._lock:
            self._events.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._events.clear()


request_rate_limiter = _RequestRateLimiter()

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
