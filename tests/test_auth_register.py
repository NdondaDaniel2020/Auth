"""Endpoint tests for POST /auth/register — #15 registro de usuário."""

from __future__ import annotations

from sqlalchemy import select

from app.core.security import verify_password
from app.models.user import User
from tests.conftest import run_in_isolated_db


def test_register_success(api_client, isolated_db_path) -> None:
    response = api_client.post(
        '/auth/register',
        json={
            'email': 'new@example.com',
            'password': 'T3st!Passw0rd',
            'full_name': 'New User',
        },
    )
    assert response.status_code == 201

    body = response.json()
    assert body['id']
    assert body['email'] == 'new@example.com'
    assert body['full_name'] == 'New User'
    assert body['is_active'] is True
    assert body['is_verified'] is False

    assert 'password' not in body
    assert 'hashed_password' not in body


def test_register_stores_password_hash_only(
    api_client, isolated_db_path
) -> None:
    api_client.post(
        '/auth/register',
        json={'email': 'hash@example.com', 'password': 'T3st!Passw0rd'},
    )

    async def _check(factory):
        async with factory() as session:
            user = (await session.execute(select(User))).scalar_one()
            assert user.email == 'hash@example.com'
            assert user.hashed_password != 'T3st!Passw0rd'
            assert verify_password('T3st!Passw0rd', user.hashed_password) is True

    run_in_isolated_db(isolated_db_path, _check)


def test_register_duplicate_email_rejected(api_client) -> None:
    payload = {'email': 'dup@example.com', 'password': 'T3st!Passw0rd'}
    first = api_client.post('/auth/register', json=payload)
    assert first.status_code == 201

    second = api_client.post('/auth/register', json=payload)
    assert second.status_code == 409
    body = second.json()
    assert body['error']['type'] == 'EmailAlreadyExistsError'


def test_register_weak_password_rejected(api_client) -> None:
    response = api_client.post(
        '/auth/register',
        json={'email': 'weak@example.com', 'password': 'short'},
    )
    assert response.status_code == 422


def test_register_invalid_email_rejected(api_client) -> None:
    response = api_client.post(
        '/auth/register',
        json={'email': 'not-an-email', 'password': 'T3st!Passw0rd'},
    )
    assert response.status_code == 422
