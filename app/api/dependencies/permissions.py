from __future__ import annotations

from app.api.dependencies.auth import CurrentUserDep
from app.core.exceptions import PermissionDeniedError
from app.models.user import User

# Centralized authorization layer. Endpoints must NOT implement ad-hoc role
# or permission checks inline; they compose these dependency factories on
# top of ``get_current_user`` (see ``auth.py``):
#
#   Depends(require_role('admin'))
#   Depends(check_permission('users:delete'))
#
# Both factories keep a 403 semantic: the user is authenticated but lacks
# the required role/permission.


def require_role(*allowed_roles: str):
    """Dependency factory requiring at least one of the given roles."""

    async def _role_checker(current_user: CurrentUserDep) -> User:
        user_roles = {role.name for role in current_user.roles}
        if not user_roles.intersection(allowed_roles):
            raise PermissionDeniedError(
                message=(
                    'Access denied: requires one of the roles '
                    f'{", ".join(allowed_roles)}'
                ),
                code='INSUFFICIENT_ROLE',
            )
        return current_user

    return _role_checker


def check_permission(required_code: str):
    """Dependency factory requiring a specific permission code."""

    async def _permission_checker(current_user: CurrentUserDep) -> User:
        granted = {
            permission.code
            for role in current_user.roles
            for permission in role.permissions
        }
        if required_code not in granted:
            raise PermissionDeniedError(
                message=f'Access denied: requires the permission "{required_code}"',
                code='INSUFFICIENT_PERMISSION',
            )
        return current_user

    return _permission_checker
