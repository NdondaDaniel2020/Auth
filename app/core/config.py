from __future__ import annotations

from functools import lru_cache
from typing import Literal

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

    @property
    def CORS_ORIGINS_LIST(self) -> list[str]:
        if self.CORS_ORIGINS.strip() == '*':
            return ['*']

        return [
            origin.strip()
            for origin in self.CORS_ORIGINS.split(',')
            if origin.strip()
        ]


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
            settings.CORS_ORIGINS_LIST = settings.cors_origins_list
        except Exception:
            pass

    return settings
