"""Unit tests for app/core/rate_limiter.py — #23 proteção contra tentativas excessivas.

Uses an explicit ``now`` parameter to simulate the passage of time without
sleeping.
"""
from __future__ import annotations

from app.core.rate_limiter import (
    rate_limiter,
)


def _within_limit(key: str, now: float) -> bool:
    return rate_limiter.check_blocked(key, now) is None


def test_allowed_within_limit() -> None:
    key = 'user@example.com'
    for attempt in range(4):
        rate_limiter.register_failed_attempt(key, now=1000 + attempt)
    assert _within_limit(key, now=1004) is True
    rate_limiter.clear()


def test_blocked_after_exceeding_limit() -> None:
    key = 'block@example.com'
    for attempt in range(5):
        rate_limiter.register_failed_attempt(key, now=2000 + attempt)

    blocked = rate_limiter.check_blocked(key, now=2005)
    assert blocked is not None
    assert blocked >= 1
    rate_limiter.clear()


def test_block_expires_after_duration() -> None:
    key = 'expire@example.com'
    for attempt in range(5):
        rate_limiter.register_failed_attempt(key, now=3000 + attempt)

    assert rate_limiter.check_blocked(key, now=3005) is not None
    # Block duration is 30 minutes by default; well past it -> allowed again.
    assert rate_limiter.check_blocked(key, now=5000) is None
    rate_limiter.clear()


def test_success_resets_counter() -> None:
    key = 'reset@example.com'
    for attempt in range(4):
        rate_limiter.register_failed_attempt(key, now=4000 + attempt)

    rate_limiter.reset_attempts(key)
    assert _within_limit(key, now=4004) is True
    rate_limiter.clear()


def test_old_attempts_pruned_from_window() -> None:
    key = 'window@example.com'
    # 4 failures just inside the 15-minute window
    for attempt in range(4):
        rate_limiter.register_failed_attempt(key, now=6000 + attempt)

    # After the window elapses, the old attempts should not count.
    assert _within_limit(key, now=6000 + 900 + 1) is True
    rate_limiter.clear()


def test_clear_removes_all_state() -> None:
    key = 'clear@example.com'
    rate_limiter.register_failed_attempt(key, now=1)
    rate_limiter.clear()
    assert _within_limit(key, now=2) is True
