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
