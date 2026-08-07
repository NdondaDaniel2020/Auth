"""Tests for app/core/security.py — password hashing and JWT tokens.

Covers issues:
- #16 hashing de senha
- #17 login com JWT (token generation/signature)
- #18 refresh token (creation and type-segregated decoding)
"""
from __future__ import annotations

from datetime import timedelta

import jwt
import pytest

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    decode_refresh_token,
    hash_password,
    verify_password,
)


def test_hash_is_not_plain_text() -> None:
    hashed = hash_password('supersecret')
    assert hashed != 'supersecret'
    assert 'supersecret' not in hashed


def test_verify_password_success() -> None:
    hashed = hash_password('supersecret')
    assert verify_password('supersecret', hashed) is True


def test_verify_password_failure() -> None:
    hashed = hash_password('supersecret')
    assert verify_password('wrongpassword', hashed) is False


def test_same_password_produces_different_hashes() -> None:
    first = hash_password('supersecret')
    second = hash_password('supersecret')
    assert first != second


def test_access_token_roundtrip() -> None:
    token = create_access_token({'sub': 'user-123'})
    payload = decode_access_token(token)
    assert payload['sub'] == 'user-123'
    assert payload['type'] == 'access'
    assert 'exp' in payload
    assert 'iat' in payload


def test_expired_access_token_is_rejected() -> None:
    token = create_access_token(
        {'sub': 'user-123'},
        expires_delta=timedelta(seconds=-1),
    )
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(token)


def test_refresh_token_roundtrip() -> None:
    token = create_refresh_token({'sub': 'user-123', 'jti': 'jti-1'})
    payload = decode_refresh_token(token)
    assert payload['sub'] == 'user-123'
    assert payload['jti'] == 'jti-1'
    assert payload['type'] == 'refresh'


def test_access_token_cannot_be_used_as_refresh() -> None:
    access = create_access_token({'sub': 'user-123'})
    with pytest.raises(jwt.InvalidTokenError):
        decode_refresh_token(access)


def test_refresh_token_cannot_be_used_as_access() -> None:
    refresh = create_refresh_token({'sub': 'user-123', 'jti': 'jti-1'})
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(refresh)
