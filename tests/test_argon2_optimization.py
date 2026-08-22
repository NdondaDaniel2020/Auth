"""Tests for Argon2id async threadpool offloading & custom parameter configuration."""

from __future__ import annotations

import asyncio

import pytest

from app.core.config import get_settings
from app.core.security import (
    hash_password_async,
    verify_password_async,
)


@pytest.mark.asyncio
async def test_hash_and_verify_password_async() -> None:
    password = 'T3st!Password123'
    hashed = await hash_password_async(password)

    assert hashed is not None
    assert hashed.startswith('$argon2')

    valid = await verify_password_async(password, hashed)
    assert valid is True

    invalid = await verify_password_async('WrongPassword', hashed)
    assert invalid is False


@pytest.mark.asyncio
async def test_concurrent_password_verifications_non_blocking() -> None:
    password = 'ConcurrentTestPassword!123'
    hashed = await hash_password_async(password)

    # Run 5 concurrent password verification tasks
    tasks = [verify_password_async(password, hashed) for _ in range(5)]
    results = await asyncio.gather(*tasks)

    assert len(results) == 5
    assert all(results)


def test_argon2_settings_configuration() -> None:
    settings = get_settings()
    assert hasattr(settings, 'ARGON2_TIME_COST')
    assert hasattr(settings, 'ARGON2_MEMORY_COST')
    assert hasattr(settings, 'ARGON2_PARALLELISM')
