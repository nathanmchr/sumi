from fastapi import APIRouter

from app.routers.admin import router as admin_router
from app.routers.auth import router as auth_router
from app.routers.content import router as content_router
from app.routers.learning import router as learning_router
from app.routers.users import router as users_router
from app.routers.lessons import router as lessons_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(content_router)
api_router.include_router(learning_router)
api_router.include_router(admin_router)
api_router.include_router(lessons_router)
