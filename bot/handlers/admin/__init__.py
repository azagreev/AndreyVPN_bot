from aiogram import Router
from bot.handlers.admin import menu, approvals, users, stats


def setup_admin_handlers() -> Router:
    router = Router()
    router.include_router(menu.router)
    router.include_router(approvals.router)
    router.include_router(users.router)
    router.include_router(stats.router)
    return router
