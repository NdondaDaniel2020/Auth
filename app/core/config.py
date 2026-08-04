from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class EnvironmentSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file='.env', env_file_encoding='utf-8', extra='ignore'
    )

    environment: Literal['development', 'test', 'production'] = Field(
        default='development',
        alias='ENVIRONMENT',
    )


class BaseAppSettings(BaseSettings):
    model_config = SettingsConfigDict(extra='ignore')

    app_name: str = Field(default='Auth API', alias='APP_NAME')
    app_version: str = Field(default='0.1.0', alias='APP_VERSION')
    app_description: str = Field(
        default='Base FastAPI built with uv.',
        alias='APP_DESCRIPTION',
    )
    debug: bool = Field(default=False, alias='DEBUG')
    database_url: str = Field(
        default='sqlite+aiosqlite:///./.data/app.db',
        alias='DATABASE_URL',
    )
    cors_origins: str = Field(default='*', alias='CORS_ORIGINS')
    secret_key: str = Field(
        default='dev-only-secret-change-me',
        alias='SECRET_KEY',
    )
    algorithm: str = Field(default='HS256', alias='ALGORITHM')
    jwt_access_minutes: int = Field(
        default=15,
        alias='JWT_ACCESS_MINUTES',
    )
    jwt_refresh_days: int = Field(
        default=7,
        alias='JWT_REFRESH_DAYS',
    )

    @property
    def cors_origins_list(self) -> list[str]:
        if self.cors_origins.strip() == '*':
            return ['*']

        return [
            origin.strip()
            for origin in self.cors_origins.split(',')
            if origin.strip()
        ]


class DevelopmentSettings(BaseAppSettings):
    model_config = SettingsConfigDict(
        env_file='.env', env_file_encoding='utf-8', extra='ignore'
    )

    debug: bool = Field(default=True, alias='DEBUG')
    database_url: str = Field(
        default='sqlite+aiosqlite:///./.data/app.db',
        alias='DATABASE_URL',
    )
    cors_origins: str = Field(default='*', alias='CORS_ORIGINS')
    secret_key: str = Field(
        default='dev-only-secret-change-me',
        alias='SECRET_KEY',
    )


class TestSettings(BaseAppSettings):
    model_config = SettingsConfigDict(
        env_file='.env', env_file_encoding='utf-8', extra='ignore'
    )

    debug: bool = Field(default=False, alias='DEBUG')
    database_url: str = Field(
        default='sqlite+aiosqlite:///./.data/test.db',
        alias='DATABASE_URL',
    )
    cors_origins: str = Field(default='*', alias='CORS_ORIGINS')
    secret_key: str = Field(
        default='test-only-secret-change-me',
        alias='SECRET_KEY',
    )


class ProductionSettings(BaseAppSettings):
    model_config = SettingsConfigDict(env_file=None, extra='ignore')

    database_url: str = Field(min_length=1, alias='DATABASE_URL')
    cors_origins: str = Field(min_length=1, alias='CORS_ORIGINS')
    secret_key: str = Field(min_length=1, alias='SECRET_KEY')


@lru_cache(maxsize=1)
def get_settings() -> BaseAppSettings:
    environment = EnvironmentSettings().environment

    settings_map = {
        'development': DevelopmentSettings,
        'test': TestSettings,
        'production': ProductionSettings,
    }

    settings_class = settings_map.get(environment)
    if settings_class is None:
        raise ValueError(f'Unsupported environment: {environment}')

    settings = settings_class()

    # Expose uppercase constant-style attributes for backward-compatibility
    # and to allow access like `settings.APP_NAME` as requested.
    try:
        data = settings.model_dump()
    except Exception:
        # Fallback to __dict__ if model_dump isn't available
        data = getattr(settings, '__dict__', {})

    for key, value in data.items():
        try:
            setattr(settings, key.upper(), value)
        except Exception:
            # Ignore attributes that can't be set
            pass

    # Expose computed properties that are not part of model_dump
    if hasattr(settings, 'cors_origins_list'):
        try:
            setattr(settings, 'CORS_ORIGINS_LIST', settings.cors_origins_list)
        except Exception:
            pass

    return settings
