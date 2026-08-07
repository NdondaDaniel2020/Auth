from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.dependencies.database import SessionDep
from app.core.config import get_settings
from app.core.exceptions import GoogleLoginDisabledError
from app.schemas.auth import Token
from app.schemas.google import GoogleAuthUrlResponse, GoogleLoginRequest
from app.services import google_auth_service

router = APIRouter(prefix='/auth/google', tags=['google-auth'])


@router.get('/url', response_model=GoogleAuthUrlResponse)
async def google_auth_url() -> GoogleAuthUrlResponse:
    """Return the Google consent-screen URL plus the signed CSRF state.

    The client redirects the browser to ``authorization_url``; Google calls
    back at ``GOOGLE_REDIRECT_URI`` with a ``code`` that the client then
    submits to ``POST /auth/google/callback`` together with ``state``.
    """
    if not get_settings().GOOGLE_LOGIN_ENABLED:
        raise GoogleLoginDisabledError()

    state = google_auth_service.create_google_state()
    return GoogleAuthUrlResponse(
        authorization_url=google_auth_service.build_authorization_url(state),
        state=state,
    )


@router.post('/callback', response_model=Token)
async def google_callback(
    data: GoogleLoginRequest, request: Request, db: SessionDep
) -> Token:
    """Complete Google login with the authorization code (or an id_token).

    New users are auto-registered as verified; existing users are linked and
    authenticated. Returns the app's ``access_token``/``refresh_token`` pair.
    """
    client_ip = request.client.host if request.client else None
    return await google_auth_service.google_login(
        db,
        code=data.code,
        id_token=data.id_token,
        state=data.state,
        client_ip=client_ip,
    )
