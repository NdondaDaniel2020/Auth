"""Multi-role/multi-permission RBAC scenarios — #48.

Single-role and single-permission coverage lives in
``test_auth_dependencies.py``; this module fills the combinatorial gaps:
users with several roles, routes that accept several roles, and permission
sets spread across multiple roles.

Note: ``check_permission`` accepts a single permission code per dependency
(AND-combinations are not part of the API surface), so "route requiring
multiple permissions" is intentionally not covered here.
"""

from __future__ import annotations

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies.auth import CurrentUserDep
from app.api.dependencies.permissions import check_permission, require_role
from app.core.error_handlers import register_exception_handlers
from app.core.security import create_access_token
from app.db.session import get_db
from app.models.permission import Permission
from app.models.role import Role
from app.models.user import User
from tests.conftest import run_in_isolated_db


def _make_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get('/staff')
    async def staff(user: CurrentUserDep) -> dict:
        return {'id': user.id}

    @app.get('/admin-or-manager')
    async def admin_or_manager(
        user=Depends(require_role('admin', 'manager')),
    ) -> dict:
        return {'id': user.id}

    @app.get('/read-anything')
    async def read_anything(
        user=Depends(check_permission('users:read')),
    ) -> dict:
        return {'id': user.id}

    return app


@pytest.fixture
def rbac_client(isolated_session_factory) -> TestClient:
    app = _make_app()

    async def _override_get_db():
        async with isolated_session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db

    with TestClient(app) as test_client:
        yield test_client


def _seed_user(
    isolated_db_path: str,
    *,
    email: str,
    role_permissions: dict[str, tuple[str, ...]] | None = None,
) -> str:
    """Create a user with roles, each mapped to its permission codes."""
    out: dict[str, str] = {}

    async def _coro(factory):
        async with factory() as session:
            user = User(email=email, hashed_password='not-a-real-hash')

            for role_name, permission_codes in (role_permissions or {}).items():
                role = Role(name=role_name)
                for code in permission_codes:
                    role.permissions.append(Permission(code=code))
                user.roles.append(role)

            session.add(user)
            await session.commit()
            out['id'] = user.id

    run_in_isolated_db(isolated_db_path, _coro)
    return out['id']


def _headers(token: str) -> dict[str, str]:
    return {'Authorization': f'Bearer {token}'}


def test_user_with_required_role_among_many_is_allowed(
    rbac_client, isolated_db_path
) -> None:
    user_id = _seed_user(
        isolated_db_path,
        email='multi@example.com',
        role_permissions={
            'user': (),
            'editor': (),
            'admin': ('users:read',),
        },
    )
    token = create_access_token({'sub': user_id})

    response = rbac_client.get('/admin-or-manager', headers=_headers(token))
    assert response.status_code == 200
    assert response.json()['id'] == user_id


def test_route_accepting_multiple_roles_allows_any_of_them(
    rbac_client, isolated_db_path
) -> None:
    manager_id = _seed_user(
        isolated_db_path,
        email='manager@example.com',
        role_permissions={'manager': ()},
    )
    admin_id = _seed_user(
        isolated_db_path,
        email='admin@example.com',
        role_permissions={'admin': ()},
    )

    manager = rbac_client.get(
        '/admin-or-manager',
        headers=_headers(create_access_token({'sub': manager_id})),
    )
    assert manager.status_code == 200

    admin = rbac_client.get(
        '/admin-or-manager',
        headers=_headers(create_access_token({'sub': admin_id})),
    )
    assert admin.status_code == 200


def test_route_accepting_multiple_roles_denies_others(
    rbac_client, isolated_db_path
) -> None:
    support_id = _seed_user(
        isolated_db_path,
        email='support@example.com',
        role_permissions={'support': ()},
    )

    response = rbac_client.get(
        '/admin-or-manager',
        headers=_headers(create_access_token({'sub': support_id})),
    )
    assert response.status_code == 403
    assert response.json()['error']['code'] == 'INSUFFICIENT_ROLE'


def test_permission_covered_across_multiple_roles_allowed(
    rbac_client, isolated_db_path
) -> None:
    user_id = _seed_user(
        isolated_db_path,
        email='split@example.com',
        role_permissions={
            'reader': ('users:read',),
            'extra': ('users:write',),
        },
    )

    response = rbac_client.get(
        '/read-anything',
        headers=_headers(create_access_token({'sub': user_id})),
    )
    assert response.status_code == 200


def test_permission_not_covered_by_any_role_denied(
    rbac_client, isolated_db_path
) -> None:
    user_id = _seed_user(
        isolated_db_path,
        email='noperm@example.com',
        role_permissions={'viewer': ('posts:read',)},
    )

    response = rbac_client.get(
        '/read-anything',
        headers=_headers(create_access_token({'sub': user_id})),
    )
    assert response.status_code == 403
    assert response.json()['error']['code'] == 'INSUFFICIENT_PERMISSION'


def test_unauthenticated_request_to_rbac_route_returns_401(rbac_client) -> None:
    response = rbac_client.get('/admin-or-manager')
    assert response.status_code == 401
    assert response.json()['error']['code'] == 'NOT_AUTHENTICATED'
