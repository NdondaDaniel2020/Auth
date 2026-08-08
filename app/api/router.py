from fastapi import APIRouter

from app.api.routers import auth, google_auth, users

api_router = APIRouter()

api_router.include_router(auth.router)
api_router.include_router(google_auth.router)
api_router.include_router(users.router)


@api_router.get('/health')
async def health_check() -> dict[str, str]:
    return {'status': 'ok'}
