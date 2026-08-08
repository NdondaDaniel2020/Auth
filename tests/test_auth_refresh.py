"""Endpoint tests for POST /auth/refresh — #18 refresh token, #24 rotação."""

from __future__ import annotations

from datetime import timedelta

from app.core.security import create_refresh_token


def _login(
    api_client,
    email: str = 'refresh@example.com',
    password: str = 'T3st!Passw0rd',
):
    assert (
        api_client.post(
            '/auth/register',
            json={'email': email, 'password': password},
        ).status_code
        == 201
    )
    response = api_client.post(
        '/auth/login',
        json={'email': email, 'password': password},
    )
    assert response.status_code == 200
    return response.json()


def test_refresh_rotates_tokens(api_client) -> None:
    tokens = _login(api_client)

    response = api_client.post(
        '/auth/refresh',
        json={'refresh_token': tokens['refresh_token']},
    )
    assert response.status_code == 200

    body = response.json()
    # The refresh token is rotated on every use; the old one is invalidated.
    assert body['refresh_token'] != tokens['refresh_token']
    from app.core.security import decode_access_token

    assert (
        decode_access_token(body['access_token'])['sub']
        == decode_access_token(tokens['access_token'])['sub']
    )


def test_refresh_token_is_single_use(api_client) -> None:
    tokens = _login(api_client)

    first = api_client.post(
        '/auth/refresh',
        json={'refresh_token': tokens['refresh_token']},
    )
    assert first.status_code == 200

    reuse = api_client.post(
        '/auth/refresh',
        json={'refresh_token': tokens['refresh_token']},
    )
    assert reuse.status_code == 401
    assert reuse.json()['error']['type'] == 'InvalidRefreshTokenError'
    assert reuse.json()['error']['code'] == 'INVALID_REFRESH_TOKEN'


def test_refresh_with_access_token_rejected(api_client) -> None:
    tokens = _login(api_client)

    response = api_client.post(
        '/auth/refresh',
        json={'refresh_token': tokens['access_token']},
    )
    assert response.status_code == 401
    assert response.json()['error']['type'] == 'InvalidRefreshTokenError'
    assert response.json()['error']['code'] == 'INVALID_REFRESH_TOKEN'


def test_refresh_with_malformed_token_rejected(api_client) -> None:
    response = api_client.post(
        '/auth/refresh',
        json={'refresh_token': 'not-a-real-token'},
    )
    assert response.status_code == 401


def test_refresh_with_expired_token_rejected(api_client) -> None:
    expired = create_refresh_token(
        {'sub': 'whatever', 'jti': 'whatever'},
        expires_delta=timedelta(days=-1),
    )
    response = api_client.post(
        '/auth/refresh',
        json={'refresh_token': expired},
    )
    assert response.status_code == 401


def test_refresh_with_unknown_jti_rejected(api_client) -> None:
    # Signed correctly, but the jti was never persisted.
    unknown = create_refresh_token({'sub': 'ghost-user', 'jti': 'ghost-jti'})
    response = api_client.post(
        '/auth/refresh',
        json={'refresh_token': unknown},
    )
    assert response.status_code == 401
    assert response.json()['error']['type'] == 'InvalidRefreshTokenError'
    assert response.json()['error']['code'] == 'INVALID_REFRESH_TOKEN'
