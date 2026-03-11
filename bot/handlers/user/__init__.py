from aiogram import Router
from bot.handlers.user import menu, profiles, status


def setup_user_handlers() -> Router:
    router = Router()
    router.include_router(menu.router)
    router.include_router(profiles.router)
    router.include_router(status.router)
    return router
