"""Tests for AuthResponse and GET /auth/me RBAC metadata serialization."""

from __future__ import annotations

import pytest

from app.models.user import User


def _login(
    api_client,
    email: str = 'rbac_user@example.com',
    password: str = 'T3st!Passw0rd',
):
    api_client.post(
        '/auth/register',
        json={'email': email, 'password': password},
    )
    response = api_client.post(
        '/auth/login',
        json={'email': email, 'password': password},
    )
    assert response.status_code == 200
    return response.json()


def test_login_returns_auth_response_with_rbac_user_metadata(
    api_client,
) -> None:
    auth_data = _login(api_client, email='rbac_response@example.com')

    assert 'access_token' in auth_data
    assert 'refresh_token' in auth_data
    assert 'user' in auth_data

    user_meta = auth_data['user']
    assert user_meta['email'] == 'rbac_response@example.com'
    assert 'roles' in user_meta
    assert 'permissions' in user_meta
    assert isinstance(user_meta['roles'], list)
    assert isinstance(user_meta['permissions'], list)


def test_auth_me_endpoint_returns_user_rbac_metadata(api_client) -> None:
    auth_data = _login(api_client, email='auth_me@example.com')
    access_token = auth_data['access_token']

    response = api_client.get(
        '/auth/me',
        headers={'Authorization': f'Bearer {access_token}'},
    )
    assert response.status_code == 200

    body = response.json()
    assert body['email'] == 'auth_me@example.com'
    assert 'roles' in body
    assert 'permissions' in body
    assert isinstance(body['roles'], list)
    assert isinstance(body['permissions'], list)


@pytest.mark.asyncio
async def test_superuser_rbac_metadata_includes_wildcard_permission(
    isolated_session_factory,
) -> None:
    from app.repositories.user_repository import UserRepository
    from app.services import user_service

    async with isolated_session_factory() as session:
        created_user = User(
            email='admin_wildcard@example.com',
            is_superuser=True,
            is_active=True,
        )
        session.add(created_user)
        await session.commit()

        user = await UserRepository(session).get_by_id(created_user.id)
        assert user is not None
        metadata = user_service.get_user_rbac_metadata(user)
        assert metadata.is_superuser is True
        assert '*' in metadata.permissions
