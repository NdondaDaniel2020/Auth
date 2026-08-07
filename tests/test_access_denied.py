"""Transversal negative-access suite — #49.

Every protected route must refuse requests the same way: missing, malformed,
expired or user-inactive tokens yield HTTP 401 (authentication), while a
missing role yields HTTP 403 (authorization). Error bodies must follow the
standard ``{error, status, path, method}`` schema and must never leak
internal details.

To add a new protected route, append an entry to ``ROUTES`` — the whole
parametrized suite picks it up automatically.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.security import create_access_token, hash_password
from app.models.user import User
from tests.conftest import run_in_isolated_db

VALID_USER_ID = '00000000-0000-0000-0000-000000000000'

# (method, path, role required or None). ``{user_id}`` is substituted at
# request time with a valid UUID so auth (401/403) is reached before any 422.
ROUTES: list[tuple[str, str, str | None]] = [
    ('GET', '/users/me', None),
    ('PATCH', '/users/me', None),
    ('GET', '/users', 'admin'),
    ('GET', '/users/{user_id}', 'admin'),
    ('PATCH', '/users/{user_id}/deactivate', 'admin'),
    ('PATCH', '/users/{user_id}/activate', 'admin'),
    ('PUT', '/users/{user_id}/roles', 'admin'),
]


def _body_for(method: str, path: str) -> dict | None:
    if path == '/users/me':
        return {}
    if path == '/users/{user_id}/roles':
        return {'role_ids': []}
    return None


def _call(
    client: TestClient,
    method: str,
    path: str,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict]:
    url = path.format(user_id=VALID_USER_ID)
    response = client.request(method, url, headers=headers, json=_body_for(method, path))
    return response.status_code, response.json()


def _seed_user(isolated_db_path: str, *, email: str, is_active: bool = True) -> str:
    out: dict[str, str] = {}

    async def _coro(factory):
        async with factory() as session:
            session.add(
                User(
                    email=email,
                    hashed_password=hash_password('T3st!Passw0rd'),
                    is_active=is_active,
                )
            )
            await session.commit()
            user = (
                await session.execute(select(User).where(User.email == email))
            ).scalar_one()
            out['id'] = user.id

    run_in_isolated_db(isolated_db_path, _coro)
    return out['id']


def _assert_error_schema(body: dict, *, status: int) -> None:
    assert body['status'] == status
    assert isinstance(body['path'], str) and body['path'].startswith('/')
    assert isinstance(body['method'], str)
    error = body['error']
    assert set(error) >= {'type', 'message', 'code'}
    assert isinstance(error['type'], str)
    assert isinstance(error['message'], str)
    assert isinstance(error['code'], str)


@pytest.mark.parametrize(
    ('method', 'path', 'role'),
    ROUTES,
    ids=[f'{m} {p}' for m, p, _ in ROUTES],
)
def test_no_token_returns_401(full_client, method, path, role) -> None:
    status, body = _call(full_client, method, path)
    assert status == 401
    assert body['error']['code'] == 'NOT_AUTHENTICATED'
    assert body['error']['type'] == 'NotAuthenticatedError'
    _assert_error_schema(body, status=401)


@pytest.mark.parametrize(
    ('method', 'path', 'role'),
    ROUTES,
    ids=[f'{m} {p}' for m, p, _ in ROUTES],
)
def test_malformed_token_returns_401(full_client, method, path, role) -> None:
    status, body = _call(
        full_client, method, path, headers={'Authorization': 'Bearer not-a-jwt'}
    )
    assert status == 401
    assert body['error']['code'] == 'TOKEN_INVALID'
    _assert_error_schema(body, status=401)


@pytest.mark.parametrize(
    ('method', 'path', 'role'),
    ROUTES,
    ids=[f'{m} {p}' for m, p, _ in ROUTES],
)
def test_expired_token_returns_401(full_client, method, path, role) -> None:
    expired = create_access_token(
        {'sub': VALID_USER_ID}, expires_delta=timedelta(minutes=-5)
    )
    status, body = _call(
        full_client, method, path, headers={'Authorization': f'Bearer {expired}'}
    )
    assert status == 401
    assert body['error']['code'] == 'TOKEN_EXPIRED'
    _assert_error_schema(body, status=401)


@pytest.mark.parametrize(
    ('method', 'path', 'role'),
    ROUTES,
    ids=[f'{m} {p}' for m, p, _ in ROUTES],
)
def test_inactive_user_token_returns_401(
    full_client, isolated_db_path, method, path, role
) -> None:
    user_id = _seed_user(
        isolated_db_path, email='inactive-access@example.com', is_active=False
    )
    token = create_access_token({'sub': user_id})
    status, body = _call(
        full_client, method, path, headers={'Authorization': f'Bearer {token}'}
    )
    assert status == 401
    assert body['error']['code'] == 'ACCOUNT_INACTIVE'
    _assert_error_schema(body, status=401)


@pytest.mark.parametrize(
    ('method', 'path', 'role'),
    ROUTES,
    ids=[f'{m} {p}' for m, p, _ in ROUTES],
)
def test_authenticated_route_reachable_by_regular_user(
    full_client, isolated_db_path, method, path, role
) -> None:
    if role is not None:
        pytest.skip('admin-required route; regular user must be denied')

    user_id = _seed_user(
        isolated_db_path, email='regular@example.com', is_active=True
    )
    token = create_access_token({'sub': user_id})
    status, _ = _call(
        full_client, method, path, headers={'Authorization': f'Bearer {token}'}
    )
    assert status == 200


@pytest.mark.parametrize(
    ('method', 'path', 'role'),
    [(m, p, r) for m, p, r in ROUTES if r is not None],
    ids=[f'{m} {p}' for m, p, r in ROUTES if r is not None],
)
def test_missing_role_returns_403(
    full_client, isolated_db_path, method, path, role
) -> None:
    user_id = _seed_user(
        isolated_db_path, email='noadmin@example.com', is_active=True
    )
    token = create_access_token({'sub': user_id})
    status, body = _call(
        full_client, method, path, headers={'Authorization': f'Bearer {token}'}
    )
    assert status == 403
    assert body['error']['code'] == 'INSUFFICIENT_ROLE'
    _assert_error_schema(body, status=403)


def test_authentication_precedes_authorization(full_client) -> None:
    """Unauthenticated users always get 401, never 403."""
    status, body = _call(full_client, 'GET', '/users')
    assert status == 401
    assert body['error']['code'] == 'NOT_AUTHENTICATED'


def test_error_messages_do_not_leak_internals(full_client) -> None:
    _, body = _call(full_client, 'GET', '/users')
    message = body['error']['message']
    assert 'Traceback' not in message
    assert 'hash' not in message.lower()
    assert 'password' not in message.lower()
