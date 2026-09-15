"""Регистрация роутеров (пивот на You vs You)."""

from aiogram import Router

from handlers.common import router as common_router
from handlers.premium import router as premium_router
from handlers.start import router as start_router


def setup_routers() -> Router:
    root = Router()
    root.include_router(common_router)
    root.include_router(start_router)
    root.include_router(premium_router)
    return root
