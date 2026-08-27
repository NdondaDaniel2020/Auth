from __future__ import annotations

from typing import Any

from app.schemas.error import ErrorResponse

COMMON_UNAUTHORIZED_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {
        'model': ErrorResponse,
        'description': (
            'Não autenticado ou token inválido/expirado (códigos: NOT_AUTHENTICATED, '
            'TOKEN_EXPIRED, TOKEN_INVALID, ACCOUNT_INACTIVE).'
        ),
        'content': {
            'application/json': {
                'examples': {
                    'not_authenticated': {
                        'summary': 'Token não fornecido',
                        'value': {
                            'error': {
                                'type': 'NotAuthenticatedError',
                                'message': 'Not authenticated',
                                'code': 'NOT_AUTHENTICATED',
                            },
                            'status': 401,
                            'path': '/api/users/me',
                            'method': 'GET',
                        },
                    },
                    'token_expired': {
                        'summary': 'Token expirado',
                        'value': {
                            'error': {
                                'type': 'TokenExpiredError',
                                'message': 'Access token expired',
                                'code': 'TOKEN_EXPIRED',
                            },
                            'status': 401,
                            'path': '/api/users/me',
                            'method': 'GET',
                        },
                    },
                    'token_invalid': {
                        'summary': 'Token inválido',
                        'value': {
                            'error': {
                                'type': 'TokenInvalidError',
                                'message': 'Invalid token signature',
                                'code': 'TOKEN_INVALID',
                            },
                            'status': 401,
                            'path': '/api/users/me',
                            'method': 'GET',
                        },
                    },
                    'account_inactive': {
                        'summary': 'Conta desativada',
                        'value': {
                            'error': {
                                'type': 'AccountInactiveError',
                                'message': 'User account is inactive',
                                'code': 'ACCOUNT_INACTIVE',
                            },
                            'status': 401,
                            'path': '/api/users/me',
                            'method': 'GET',
                        },
                    },
                }
            }
        },
    }
}

COMMON_FORBIDDEN_RESPONSES: dict[int | str, dict[str, Any]] = {
    403: {
        'model': ErrorResponse,
        'description': (
            'Acesso proibido ou permissões insuficientes (códigos: INSUFFICIENT_ROLE, '
            'INSUFFICIENT_PERMISSION, GOOGLE_LOGIN_DISABLED).'
        ),
        'content': {
            'application/json': {
                'examples': {
                    'insufficient_role': {
                        'summary': 'Role Insuficiente',
                        'value': {
                            'error': {
                                'type': 'PermissionDeniedError',
                                'message': 'Insufficient role',
                                'code': 'INSUFFICIENT_ROLE',
                            },
                            'status': 403,
                            'path': '/api/users',
                            'method': 'GET',
                        },
                    },
                    'insufficient_permission': {
                        'summary': 'Permissão Insuficiente',
                        'value': {
                            'error': {
                                'type': 'PermissionDeniedError',
                                'message': 'Permission denied',
                                'code': 'INSUFFICIENT_PERMISSION',
                            },
                            'status': 403,
                            'path': '/api/users',
                            'method': 'GET',
                        },
                    },
                }
            }
        },
    }
}

COMMON_RATE_LIMIT_RESPONSES: dict[int | str, dict[str, Any]] = {
    429: {
        'model': ErrorResponse,
        'description': (
            'Limite de requisições excedido (códigos: RATE_LIMIT_EXCEEDED, TOO_MANY_ATTEMPTS).'
        ),
        'content': {
            'application/json': {
                'examples': {
                    'too_many_attempts': {
                        'summary': 'Muitas tentativas de login',
                        'value': {
                            'error': {
                                'type': 'TooManyLoginAttemptsError',
                                'message': 'Too many login attempts. Please try again later.',
                                'code': 'TOO_MANY_ATTEMPTS',
                            },
                            'status': 429,
                            'path': '/api/auth/login',
                            'method': 'POST',
                        },
                    },
                    'rate_limit_exceeded': {
                        'summary': 'Rate limit de rota excedido',
                        'value': {
                            'error': {
                                'type': 'RateLimitExceededError',
                                'message': 'Rate limit exceeded. Try again in 60s.',
                                'code': 'RATE_LIMIT_EXCEEDED',
                            },
                            'status': 429,
                            'path': '/api/auth/register',
                            'method': 'POST',
                        },
                    },
                }
            }
        },
    }
}

COMMON_NOT_FOUND_RESPONSES: dict[int | str, dict[str, Any]] = {
    404: {
        'model': ErrorResponse,
        'description': (
            'Recurso não encontrado (códigos: NOT_FOUND, USER_NOT_FOUND, ROLE_NOT_FOUND).'
        ),
        'content': {
            'application/json': {
                'examples': {
                    'user_not_found': {
                        'summary': 'Usuário não encontrado',
                        'value': {
                            'error': {
                                'type': 'UserNotFoundError',
                                'message': 'User not found',
                                'code': 'USER_NOT_FOUND',
                            },
                            'status': 404,
                            'path': '/api/users/00000000-0000-0000-0000-000000000000',
                            'method': 'GET',
                        },
                    }
                }
            }
        },
    }
}

# Agregações úteis para importação rápida nos routers
COMMON_AUTH_RESPONSES: dict[int | str, dict[str, Any]] = {
    **COMMON_UNAUTHORIZED_RESPONSES,
    **COMMON_FORBIDDEN_RESPONSES,
    **COMMON_RATE_LIMIT_RESPONSES,
}
