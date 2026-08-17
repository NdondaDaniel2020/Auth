from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import BaseAppSettings, ProductionSettings
from app.core.middleware import setup_cors_middleware


class _FakeSettings:
    def __init__(self) -> None:
        self.CORS_ALLOWED_ORIGINS_LIST = [
            'http://localhost:3000',
            'http://localhost:5173',
        ]
        self.CORS_ALLOW_CREDENTIALS = True
        self.CORS_ALLOWED_METHODS_LIST = ['GET', 'POST', 'OPTIONS']
        self.CORS_ALLOWED_HEADERS_LIST = ['Authorization', 'Content-Type']


def _build_app() -> FastAPI:
    app = FastAPI()

    @app.get('/health')
    async def health() -> dict[str, str]:
        return {'status': 'ok'}

    return app


def test_allowed_origin_gets_cors_headers(monkeypatch) -> None:
    monkeypatch.setattr(
        'app.core.middleware.get_settings', lambda: _FakeSettings()
    )

    app = _build_app()
    setup_cors_middleware(app)

    with TestClient(app) as client:
        response = client.get(
            '/health', headers={'Origin': 'http://localhost:3000'}
        )
        assert (
            response.headers.get('access-control-allow-origin')
            == 'http://localhost:3000'
        )
        assert (
            response.headers.get('access-control-allow-credentials') == 'true'
        )


def test_disallowed_origin_gets_no_cors_headers(monkeypatch) -> None:
    monkeypatch.setattr(
        'app.core.middleware.get_settings', lambda: _FakeSettings()
    )

    app = _build_app()
    setup_cors_middleware(app)

    with TestClient(app) as client:
        response = client.get(
            '/health', headers={'Origin': 'https://evil.example.com'}
        )
        assert 'access-control-allow-origin' not in response.headers


def test_preflight_from_allowed_origin(monkeypatch) -> None:
    monkeypatch.setattr(
        'app.core.middleware.get_settings', lambda: _FakeSettings()
    )

    app = _build_app()
    setup_cors_middleware(app)

    with TestClient(app) as client:
        response = client.options(
            '/health',
            headers={
                'Origin': 'http://localhost:5173',
                'Access-Control-Request-Method': 'GET',
                'Access-Control-Request-Headers': 'authorization',
            },
        )
        assert response.status_code == 200
        assert (
            response.headers.get('access-control-allow-origin')
            == 'http://localhost:5173'
        )
        assert 'GET' in response.headers.get(
            'access-control-allow-methods', ''
        )
        assert 'Authorization' in response.headers.get(
            'access-control-allow-headers', ''
        )


def test_preflight_from_disallowed_origin(monkeypatch) -> None:
    monkeypatch.setattr(
        'app.core.middleware.get_settings', lambda: _FakeSettings()
    )

    app = _build_app()
    setup_cors_middleware(app)

    with TestClient(app) as client:
        response = client.options(
            '/health',
            headers={
                'Origin': 'https://evil.example.com',
                'Access-Control-Request-Method': 'GET',
            },
        )
        assert 'access-control-allow-origin' not in response.headers


def test_wildcard_with_credentials_is_rejected(monkeypatch) -> None:
    settings = _FakeSettings()
    settings.CORS_ALLOWED_ORIGINS_LIST = ['*']
    settings.CORS_ALLOW_CREDENTIALS = True
    monkeypatch.setattr('app.core.middleware.get_settings', lambda: settings)

    app = _build_app()
    with pytest.raises(RuntimeError):
        setup_cors_middleware(app)


def test_production_settings_rejects_wildcard_with_credentials() -> None:
    with pytest.raises(ValueError):
        ProductionSettings(
            DATABASE_URL='sqlite+aiosqlite:///./.data/prod.db',
            CORS_ALLOWED_ORIGINS='*',
            SECRET_KEY='prod-secret-1234567890',
            REFRESH_SECRET_KEY='prod-refresh-secret-1234567890',
            ADMIN_PASSWORD='StrongAdminPassword123!',
        )


def test_production_settings_accepts_restricted_origins() -> None:
    settings = ProductionSettings(
        DATABASE_URL='sqlite+aiosqlite:///./.data/prod.db',
        CORS_ALLOWED_ORIGINS='https://app.meudominio.com',
        SECRET_KEY='prod-secret-1234567890',
        REFRESH_SECRET_KEY='prod-refresh-secret-1234567890',
        ADMIN_PASSWORD='StrongAdminPassword123!',
    )
    assert settings.CORS_ALLOWED_ORIGINS_LIST == ['https://app.meudominio.com']
    assert settings.CORS_ALLOW_CREDENTIALS is True


def test_origins_list_parsing() -> None:
    settings = BaseAppSettings(
        CORS_ALLOWED_ORIGINS='http://a.com, http://b.com ,'
    )
    assert settings.CORS_ALLOWED_ORIGINS_LIST == [
        'http://a.com',
        'http://b.com',
    ]

    wildcard = BaseAppSettings(CORS_ALLOWED_ORIGINS='*')
    assert wildcard.CORS_ALLOWED_ORIGINS_LIST == ['*']


def test_methods_and_headers_list_parsing() -> None:
    settings = BaseAppSettings(
        CORS_ALLOWED_METHODS='get, post ',
        CORS_ALLOWED_HEADERS='Authorization, Content-Type ',
    )
    assert settings.CORS_ALLOWED_METHODS_LIST == ['GET', 'POST']
    assert settings.CORS_ALLOWED_HEADERS_LIST == [
        'Authorization',
        'Content-Type',
    ]
