from fastapi import APIRouter

from app.api.routers import auth

api_router = APIRouter()

api_router.include_router(auth.router)


@api_router.get('/health')
async def health_check() -> dict[str, str]:
    return {'status': 'ok'}
