from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import get_settings


def setup_cors_middleware(app: FastAPI) -> None:
    settings = get_settings()

    origins = getattr(settings, 'CORS_ORIGINS_LIST', settings.cors_origins_list)

    allow_credentials = False if origins == ["*"] else True

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )
