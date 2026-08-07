from __future__ import annotations

from functools import lru_cache
from typing import Literal
from urllib.parse import quote_plus

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class EnvironmentSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file='.env', env_file_encoding='utf-8', extra='ignore'
    )

    ENVIRONMENT: Literal['development', 'test', 'production'] = Field(
        default='development',
        alias='ENVIRONMENT',
    )


class BaseAppSettings(BaseSettings):
    model_config = SettingsConfigDict(extra='ignore')

    APP_NAME: str = Field(default='Auth API', alias='APP_NAME')
    APP_VERSION: str = Field(default='0.1.0', alias='APP_VERSION')
    APP_DESCRIPTION: str = Field(
        default='Base FastAPI built with uv.',
        alias='APP_DESCRIPTION',
    )
    DEBUG: bool = Field(default=False, alias='DEBUG')
    DATABASE_URL: str = Field(
        default='sqlite+aiosqlite:///./.data/app.db',
        alias='DATABASE_URL',
    )
    CORS_ORIGINS: str = Field(default='*', alias='CORS_ORIGINS')
    SECRET_KEY: str = Field(
        default='dev-only-secret-change-me',
        alias='SECRET_KEY',
    )
    ALGORITHM: str = Field(default='HS256', alias='ALGORITHM')
    JWT_ACCESS_MINUTES: int = Field(
        default=15,
        alias='JWT_ACCESS_MINUTES',
    )
    JWT_REFRESH_DAYS: int = Field(
        default=7,
        alias='JWT_REFRESH_DAYS',
    )
    REFRESH_SECRET_KEY: str = Field(
        default='',
        alias='REFRESH_SECRET_KEY',
    )
    PASSWORD_HASH_SCHEME: str = Field(
        default='argon2',
        alias='PASSWORD_HASH_SCHEME',
    )
    PASSWORD_MIN_LENGTH: int = Field(
        default=8,
        alias='PASSWORD_MIN_LENGTH',
    )
    LOGIN_MAX_ATTEMPTS: int = Field(
        default=5,
        alias='LOGIN_MAX_ATTEMPTS',
    )
    LOGIN_ATTEMPT_WINDOW_MINUTES: int = Field(
        default=15,
        alias='LOGIN_ATTEMPT_WINDOW_MINUTES',
    )
    LOGIN_BLOCK_DURATION_MINUTES: int = Field(
        default=30,
        alias='LOGIN_BLOCK_DURATION_MINUTES',
    )
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES: int = Field(
        default=30,
        alias='PASSWORD_RESET_TOKEN_EXPIRE_MINUTES',
    )
    EMAIL_VERIFICATION_TOKEN_EXPIRE_MINUTES: int = Field(
        default=1440,
        alias='EMAIL_VERIFICATION_TOKEN_EXPIRE_MINUTES',
    )
    APP_BASE_URL: str = Field(
        default='http://localhost:8001',
        alias='APP_BASE_URL',
    )
    SMTP_HOST: str = Field(default='', alias='SMTP_HOST')
    SMTP_PORT: int = Field(default=587, alias='SMTP_PORT')
    SMTP_USER: str = Field(default='', alias='SMTP_USER')
    SMTP_PASSWORD: str = Field(default='', alias='SMTP_PASSWORD')
    SMTP_FROM: str = Field(default='', alias='SMTP_FROM')
    SMTP_TLS: bool = Field(default=True, alias='SMTP_TLS')

    @property
    def REFRESH_SECRET_KEY_ACTIVE(self) -> str:
        return self.REFRESH_SECRET_KEY or self.SECRET_KEY
    DB_ENGINE: str = Field(default='', alias='DB_ENGINE')
    DB_USER: str = Field(default='', alias='DB_USER')
    DB_PASSWORD: str = Field(default='', alias='DB_PASSWORD')
    DB_HOST: str = Field(default='', alias='DB_HOST')
    DB_PORT: str = Field(default='', alias='DB_PORT')
    DB_NAME: str = Field(default='', alias='DB_NAME')

    # Seed configuration
    RUN_SEED_ON_STARTUP: bool = Field(default=False, alias='RUN_SEED_ON_STARTUP')
    ADMIN_EMAIL: str = Field(default='admin@example.com', alias='ADMIN_EMAIL')
    ADMIN_PASSWORD: str = Field(default='admin123', alias='ADMIN_PASSWORD')

    @property
    def CORS_ORIGINS_LIST(self) -> list[str]:
        if self.CORS_ORIGINS.strip() == '*':
            return ['*']

        return [
            origin.strip()
            for origin in self.CORS_ORIGINS.split(',')
            if origin.strip()
        ]

    def build_database_url(self) -> str:
        """Build DATABASE_URL from DB_* components when provided.

        Priority: if `DATABASE_URL` env var is provided (non-empty), return it.
        Otherwise, if DB_ENGINE or other DB_* vars are set, construct a URL.
        Supports sqlite (sqlite+aiosqlite) and postgresql (postgresql+asyncpg).
        """
        # prefer explicit DATABASE_URL when provided
        if self.DATABASE_URL and self.DATABASE_URL.strip():
            return self.DATABASE_URL

        # if no DB_ENGINE specified, return default DATABASE_URL
        engine = (self.DB_ENGINE or '').strip()
        if not engine:
            return self.DATABASE_URL

        # SQLite handling
        if 'sqlite' in engine:
            name = self.DB_NAME or './.data/app.db'
            if name == ':memory:':
                return 'sqlite+aiosqlite:///:memory:'
            if name.startswith('/'):
                return f'sqlite+aiosqlite:///{name}'
            return f'sqlite+aiosqlite:///{name}'

        # Postgres-like handling
        if 'postgres' in engine:
            scheme = engine
            if 'asyncpg' not in scheme:
                scheme = scheme.split('+')[0] + '+asyncpg'

            user = quote_plus(self.DB_USER) if self.DB_USER else ''
            pwd = quote_plus(self.DB_PASSWORD) if self.DB_PASSWORD else ''
            host = self.DB_HOST or 'localhost'
            port = f":{self.DB_PORT}" if self.DB_PORT else ''

            auth = ''
            if user or pwd:
                auth = f"{user}:{pwd}@"

            dbname = self.DB_NAME or ''
            return f"{scheme}://{auth}{host}{port}/{dbname}"

        return self.DATABASE_URL


class DevelopmentSettings(BaseAppSettings):
    model_config = SettingsConfigDict(
        env_file='.env', env_file_encoding='utf-8', extra='ignore'
    )

    DEBUG: bool = Field(default=True, alias='DEBUG')
    DATABASE_URL: str = Field(
        default='sqlite+aiosqlite:///./.data/app.db',
        alias='DATABASE_URL',
    )
    CORS_ORIGINS: str = Field(default='*', alias='CORS_ORIGINS')
    SECRET_KEY: str = Field(
        default='dev-only-secret-change-me',
        alias='SECRET_KEY',
    )


class TestSettings(BaseAppSettings):
    model_config = SettingsConfigDict(
        env_file='.env', env_file_encoding='utf-8', extra='ignore'
    )

    DEBUG: bool = Field(default=False, alias='DEBUG')
    DATABASE_URL: str = Field(
        default='sqlite+aiosqlite:///./.data/test.db',
        alias='DATABASE_URL',
    )
    CORS_ORIGINS: str = Field(default='*', alias='CORS_ORIGINS')
    SECRET_KEY: str = Field(
        default='test-only-secret-change-me',
        alias='SECRET_KEY',
    )


class ProductionSettings(BaseAppSettings):
    model_config = SettingsConfigDict(env_file=None, extra='ignore')

    DATABASE_URL: str = Field(min_length=1, alias='DATABASE_URL')
    CORS_ORIGINS: str = Field(min_length=1, alias='CORS_ORIGINS')
    SECRET_KEY: str = Field(min_length=1, alias='SECRET_KEY')


@lru_cache(maxsize=1)
def get_settings() -> BaseAppSettings:
    environment = EnvironmentSettings().ENVIRONMENT

    settings_map = {
        'development': DevelopmentSettings,
        'test': TestSettings,
        'production': ProductionSettings,
    }

    settings_class = settings_map.get(environment)
    if settings_class is None:
        raise ValueError(f'Unsupported environment: {environment}')

    settings = settings_class()

    try:
        settings.DATABASE_URL = settings.build_database_url()
    except Exception:
        pass

    try:
        data = settings.model_dump()
    except Exception:
        data = getattr(settings, '__dict__', {})

    for key, value in data.items():
        try:
            setattr(settings, key.upper(), value)
        except Exception:
            pass

    try:
        settings.CORS_ORIGINS_LIST = settings.CORS_ORIGINS_LIST
    except Exception:
        pass

    return settings
