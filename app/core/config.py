from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Any, Literal
from urllib.parse import quote_plus

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


def _read_secret_file(env_var: str) -> str | None:
    """Read secret from file if corresponding _FILE env var is set."""
    file_env = f'{env_var}_FILE'
    file_path = os.getenv(file_env)
    if file_path:
        try:
            with open(file_path) as f:
                return f.read().strip()
        except OSError as e:
            logger.warning('Could not read secret file %s: %s', file_path, e)
    return None


class EnvironmentSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file='.env', env_file_encoding='utf-8', extra='ignore'
    )

    ENVIRONMENT: Literal['development', 'test', 'staging', 'production'] = (
        Field(
            default='development',
            alias='ENVIRONMENT',
        )
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
    DATABASE_URL: str = Field(default='', alias='DATABASE_URL')
    CORS_ALLOWED_ORIGINS: str = Field(
        default='http://localhost:3000,http://localhost:5173',
        alias='CORS_ALLOWED_ORIGINS',
    )
    CORS_ALLOW_CREDENTIALS: bool = Field(
        default=True,
        alias='CORS_ALLOW_CREDENTIALS',
    )
    CORS_ALLOWED_METHODS: str = Field(
        default='GET,POST,PUT,PATCH,DELETE,OPTIONS,HEAD',
        alias='CORS_ALLOWED_METHODS',
    )
    CORS_ALLOWED_HEADERS: str = Field(
        default='Authorization,Content-Type,Origin,Accept',
        alias='CORS_ALLOWED_HEADERS',
    )
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
    PASSWORD_MAX_LENGTH: int = Field(
        default=128,
        alias='PASSWORD_MAX_LENGTH',
    )
    PASSWORD_REQUIRE_UPPERCASE: bool = Field(
        default=True,
        alias='PASSWORD_REQUIRE_UPPERCASE',
    )
    PASSWORD_REQUIRE_LOWERCASE: bool = Field(
        default=True,
        alias='PASSWORD_REQUIRE_LOWERCASE',
    )
    PASSWORD_REQUIRE_DIGIT: bool = Field(
        default=True,
        alias='PASSWORD_REQUIRE_DIGIT',
    )
    PASSWORD_REQUIRE_SPECIAL: bool = Field(
        default=True,
        alias='PASSWORD_REQUIRE_SPECIAL',
    )
    PASSWORD_REJECT_COMMON: bool = Field(
        default=True,
        alias='PASSWORD_REJECT_COMMON',
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
    RATE_LIMIT_DEFAULT: str = Field(
        default='60/minute',
        alias='RATE_LIMIT_DEFAULT',
    )
    RATE_LIMIT_REGISTER: str = Field(
        default='10/minute',
        alias='RATE_LIMIT_REGISTER',
    )
    RATE_LIMIT_PASSWORD_RESET: str = Field(
        default='5/minute',
        alias='RATE_LIMIT_PASSWORD_RESET',
    )
    RATE_LIMIT_EMAIL_RESEND: str = Field(
        default='3/minute',
        alias='RATE_LIMIT_EMAIL_RESEND',
    )
    RATE_LIMIT_WEBSOCKET: str = Field(
        default='30/minute',
        alias='RATE_LIMIT_WEBSOCKET',
    )
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES: int = Field(
        default=30,
        alias='PASSWORD_RESET_TOKEN_EXPIRE_MINUTES',
    )
    EMAIL_VERIFICATION_TOKEN_EXPIRE_MINUTES: int = Field(
        default=1440,
        alias='EMAIL_VERIFICATION_TOKEN_EXPIRE_MINUTES',
    )
    TOKEN_CLEANUP_INTERVAL_MINUTES: int = Field(
        default=60,
        alias='TOKEN_CLEANUP_INTERVAL_MINUTES',
    )
    PAGE_SIZE_DEFAULT: int = Field(default=20, alias='PAGE_SIZE_DEFAULT')
    PAGE_SIZE_MAX: int = Field(default=100, alias='PAGE_SIZE_MAX')
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

    # Google OAuth 2.0 / OpenID Connect
    GOOGLE_LOGIN_ENABLED: bool = Field(
        default=False, alias='GOOGLE_LOGIN_ENABLED'
    )
    GOOGLE_CLIENT_ID: str = Field(default='', alias='GOOGLE_CLIENT_ID')
    GOOGLE_CLIENT_SECRET: str = Field(default='', alias='GOOGLE_CLIENT_SECRET')
    GOOGLE_REDIRECT_URI: str = Field(default='', alias='GOOGLE_REDIRECT_URI')
    GOOGLE_AUTH_URL: str = Field(
        default='https://accounts.google.com/o/oauth2/v2/auth',
        alias='GOOGLE_AUTH_URL',
    )
    GOOGLE_TOKEN_URL: str = Field(
        default='https://oauth2.googleapis.com/token',
        alias='GOOGLE_TOKEN_URL',
    )
    GOOGLE_CERTS_URL: str = Field(
        default='https://www.googleapis.com/oauth2/v3/certs',
        alias='GOOGLE_CERTS_URL',
    )
    GOOGLE_ISSUER: str = Field(
        default='https://accounts.google.com',
        alias='GOOGLE_ISSUER',
    )
    GOOGLE_STATE_TTL_MINUTES: int = Field(
        default=10, alias='GOOGLE_STATE_TTL_MINUTES'
    )
    GOOGLE_CERTS_CACHE_TTL_SECONDS: int = Field(
        default=300, alias='GOOGLE_CERTS_CACHE_TTL_SECONDS'
    )

    # Redis
    REDIS_URL: str = Field(default='', alias='REDIS_URL')
    REDIS_MAX_CONNECTIONS: int = Field(
        default=10, alias='REDIS_MAX_CONNECTIONS'
    )

    # Message Broker (RabbitMQ / Kafka)
    MESSAGE_BROKER_URL: str = Field(default='', alias='MESSAGE_BROKER_URL')
    MESSAGE_BROKER_TYPE: str = Field(
        default='rabbitmq', alias='MESSAGE_BROKER_TYPE'
    )
    MESSAGE_BROKER_EXCHANGE: str = Field(
        default='auth_events', alias='MESSAGE_BROKER_EXCHANGE'
    )
    MESSAGE_BROKER_EXCHANGE_TYPE: str = Field(
        default='topic', alias='MESSAGE_BROKER_EXCHANGE_TYPE'
    )
    MESSAGE_BROKER_BOOTSTRAP_SERVERS: str = Field(
        default='', alias='MESSAGE_BROKER_BOOTSTRAP_SERVERS'
    )
    MESSAGE_BROKER_CONSUMER_GROUP: str = Field(
        default='auth-api', alias='MESSAGE_BROKER_CONSUMER_GROUP'
    )
    MESSAGE_BROKER_SSL: bool = Field(default=False, alias='MESSAGE_BROKER_SSL')
    MESSAGE_BROKER_SSL_CA_FILE: str = Field(
        default='', alias='MESSAGE_BROKER_SSL_CA_FILE'
    )
    MESSAGE_BROKER_SSL_CERT_FILE: str = Field(
        default='', alias='MESSAGE_BROKER_SSL_CERT_FILE'
    )
    MESSAGE_BROKER_SSL_KEY_FILE: str = Field(
        default='', alias='MESSAGE_BROKER_SSL_KEY_FILE'
    )

    @model_validator(mode='before')
    @classmethod
    def _load_secrets_from_files(cls, data: Any) -> Any:
        """Load secret values from files specified via *_FILE environment variables."""
        if not isinstance(data, dict):
            return data

        secret_fields = [
            'SECRET_KEY',
            'REFRESH_SECRET_KEY',
            'DB_USER',
            'DB_PASSWORD',
            'SMTP_PASSWORD',
            'GOOGLE_CLIENT_SECRET',
            'ADMIN_PASSWORD',
            'DB_NAME',
            'GOOGLE_CLIENT_ID',
        ]
        for field in secret_fields:
            file_value = _read_secret_file(field)
            if file_value and not data.get(field):
                data[field] = file_value
        return data

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
    RUN_SEED_ON_STARTUP: bool = Field(
        default=False, alias='RUN_SEED_ON_STARTUP'
    )
    ADMIN_EMAIL: str = Field(default='admin@example.com', alias='ADMIN_EMAIL')
    ADMIN_PASSWORD: str = Field(default='admin123', alias='ADMIN_PASSWORD')

    @property
    def CORS_ALLOWED_ORIGINS_LIST(self) -> list[str]:
        if self.CORS_ALLOWED_ORIGINS.strip() == '*':
            return ['*']

        return [
            origin.strip()
            for origin in self.CORS_ALLOWED_ORIGINS.split(',')
            if origin.strip()
        ]

    @property
    def CORS_ALLOWED_METHODS_LIST(self) -> list[str]:
        return [
            method.strip().upper()
            for method in self.CORS_ALLOWED_METHODS.split(',')
            if method.strip()
        ]

    @property
    def CORS_ALLOWED_HEADERS_LIST(self) -> list[str]:
        return [
            header.strip()
            for header in self.CORS_ALLOWED_HEADERS.split(',')
            if header.strip()
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
            return 'sqlite+aiosqlite:///./.data/app.db'

        # SQLite handling
        if 'sqlite' in engine:
            name = self.DB_NAME or './.data/app.db'
            if name == ':memory:':
                return 'sqlite+aiosqlite:///:memory:'
            return f'sqlite+aiosqlite:///{name}'

        # Postgres-like handling
        if 'postgres' in engine:
            scheme = engine
            if 'asyncpg' not in scheme:
                scheme = scheme.split('+')[0] + '+asyncpg'

            user = quote_plus(self.DB_USER) if self.DB_USER else ''
            pwd = quote_plus(self.DB_PASSWORD) if self.DB_PASSWORD else ''
            host = self.DB_HOST or 'localhost'
            port = f':{self.DB_PORT}' if self.DB_PORT else ''

            auth = ''
            if user or pwd:
                auth = f'{user}:{pwd}@'

            dbname = self.DB_NAME or ''
            return f'{scheme}://{auth}{host}{port}/{dbname}'

        return self.DATABASE_URL or 'sqlite+aiosqlite:///./.data/app.db'


class DevelopmentSettings(BaseAppSettings):
    model_config = SettingsConfigDict(
        env_file='.env', env_file_encoding='utf-8', extra='ignore'
    )

    DEBUG: bool = Field(default=True, alias='DEBUG')
    DATABASE_URL: str = Field(default='', alias='DATABASE_URL')
    SECRET_KEY: str = Field(
        default='dev-only-secret-change-me',
        alias='SECRET_KEY',
    )


class TestSettings(BaseAppSettings):
    model_config = SettingsConfigDict(
        env_file='.env', env_file_encoding='utf-8', extra='ignore'
    )

    DEBUG: bool = Field(default=False, alias='DEBUG')
    DATABASE_URL: str = Field(default='', alias='DATABASE_URL')
    CORS_ALLOWED_ORIGINS: str = Field(
        default='*', alias='CORS_ALLOWED_ORIGINS'
    )
    CORS_ALLOW_CREDENTIALS: bool = Field(
        default=False,
        alias='CORS_ALLOW_CREDENTIALS',
    )
    SECRET_KEY: str = Field(
        default='test-only-secret-change-me',
        alias='SECRET_KEY',
    )


class ProductionSettings(BaseAppSettings):
    model_config = SettingsConfigDict(env_file=None, extra='ignore')

    DATABASE_URL: str = Field(min_length=1, alias='DATABASE_URL')
    CORS_ALLOWED_ORIGINS: str = Field(
        min_length=1, alias='CORS_ALLOWED_ORIGINS'
    )
    SECRET_KEY: str = Field(min_length=1, alias='SECRET_KEY')

    @model_validator(mode='after')
    def _reject_wildcard_with_credentials(self) -> ProductionSettings:
        if (
            '*' in self.CORS_ALLOWED_ORIGINS_LIST
            and self.CORS_ALLOW_CREDENTIALS
        ):
            raise ValueError(
                "CORS_ALLOWED_ORIGINS cannot be '*' when "
                'CORS_ALLOW_CREDENTIALS is enabled'
            )
        return self


class StagingSettings(BaseAppSettings):
    model_config = SettingsConfigDict(env_file=None, extra='ignore')

    DEBUG: bool = Field(default=False, alias='DEBUG')
    CORS_ALLOWED_ORIGINS: str = Field(
        min_length=1, alias='CORS_ALLOWED_ORIGINS'
    )
    SECRET_KEY: str = Field(min_length=1, alias='SECRET_KEY')


@lru_cache(maxsize=1)
def get_settings() -> BaseAppSettings:
    environment = EnvironmentSettings().ENVIRONMENT

    settings_map: dict[str, type[BaseAppSettings]] = {
        'development': DevelopmentSettings,
        'test': TestSettings,
        'staging': StagingSettings,
        'production': ProductionSettings,
    }

    settings_class = settings_map.get(environment)
    if settings_class is None:
        raise ValueError(f'Unsupported environment: {environment}')

    settings = settings_class()

    try:
        settings.DATABASE_URL = settings.build_database_url()
    except Exception:
        logger.warning(
            'Could not build DATABASE_URL from DB_* parts', exc_info=True
        )

    try:
        data = settings.model_dump()
    except Exception:
        logger.warning(
            'Could not dump settings; falling back to __dict__', exc_info=True
        )
        data = getattr(settings, '__dict__', {})

    for key, value in data.items():
        try:
            setattr(settings, key.upper(), value)
        except Exception:
            logger.debug(
                'Could not set attribute %r on settings', key, exc_info=True
            )

    return settings
