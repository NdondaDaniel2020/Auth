"""Endpoint tests for POST /auth/logout — #19 logout com revogação."""

from __future__ import annotations


def _login(api_client, email: str = 'logout@example.com'):
    assert (
        api_client.post(
            '/auth/register',
            json={'email': email, 'password': 'password123'},
        ).status_code
        == 201
    )
    response = api_client.post(
        '/auth/login',
        json={'email': email, 'password': 'password123'},
    )
    assert response.status_code == 200
    return response.json()


def test_logout_revokes_refresh_token(api_client) -> None:
    tokens = _login(api_client)

    logout = api_client.post(
        '/auth/logout', json={'refresh_token': tokens['refresh_token']}
    )
    assert logout.status_code == 204

    reuse = api_client.post(
        '/auth/refresh',
        json={'refresh_token': tokens['refresh_token']},
    )
    assert reuse.status_code == 401
    assert reuse.json()['error']['type'] == 'InvalidRefreshTokenError'


def test_logout_is_idempotent(api_client) -> None:
    tokens = _login(api_client)

    first = api_client.post(
        '/auth/logout', json={'refresh_token': tokens['refresh_token']}
    )
    second = api_client.post(
        '/auth/logout', json={'refresh_token': tokens['refresh_token']}
    )
    assert first.status_code == 204
    assert second.status_code == 204


def test_logout_with_malformed_token_rejected(api_client) -> None:
    response = api_client.post(
        '/auth/logout', json={'refresh_token': 'garbage-token'}
    )
    assert response.status_code == 401


def test_logout_with_unknown_token_rejected(api_client) -> None:

    from app.core.security import create_refresh_token

    unknown = create_refresh_token({'sub': 'x', 'jti': 'never-persisted'})
    response = api_client.post('/auth/logout', json={'refresh_token': unknown})
    assert response.status_code == 401
