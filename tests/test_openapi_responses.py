from __future__ import annotations

from app.main import app


def test_openapi_schema_contains_custom_error_responses():
    """Valida se o esquema OpenAPI inclui ErrorResponse e ErrorDetail e documenta os códigos HTTP 401, 403 e 429 nas rotas de autenticação, utilizadores, google e mfa."""
    openapi_schema = app.openapi()

    # 1. Componentes de Schema
    schemas = openapi_schema.get('components', {}).get('schemas', {})
    assert 'ErrorResponse' in schemas
    assert 'ErrorDetail' in schemas

    error_response_properties = schemas['ErrorResponse']['properties']
    assert 'error' in error_response_properties
    assert 'status' in error_response_properties
    assert 'path' in error_response_properties
    assert 'method' in error_response_properties

    # 2. Respostas nas rotas de Autenticação e Usuários
    paths = openapi_schema.get('paths', {})

    # Rota protegida /api/auth/me
    auth_me_responses = paths['/api/auth/me']['get']['responses']
    assert '401' in auth_me_responses
    assert '403' in auth_me_responses

    # Rota /api/auth/login
    login_responses = paths['/api/auth/login']['post']['responses']
    assert '401' in login_responses
    assert '429' in login_responses

    # Rota /api/users/{user_id}
    user_by_id_responses = paths['/api/users/{user_id}']['get']['responses']
    assert '401' in user_by_id_responses
    assert '403' in user_by_id_responses
    assert '404' in user_by_id_responses

    # Rota /api/auth/google/url
    google_url_responses = paths['/api/auth/google/url']['get']['responses']
    assert '403' in google_url_responses
    assert '429' in google_url_responses

    # Rota /api/mfa/totp/setup
    mfa_setup_responses = paths['/api/mfa/totp/setup']['post']['responses']
    assert '401' in mfa_setup_responses
    assert '403' in mfa_setup_responses
