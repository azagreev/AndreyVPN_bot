from aiogram import Router
from bot.handlers.onboarding import router as onboarding_router
from bot.handlers.admin import router as admin_router
from bot.handlers.profiles import router as profiles_router
from bot.handlers.monitoring import router as monitoring_router

def setup_handlers() -> Router:
    """
    Создает основной роутер и подключает в него все остальные.
    """
    main_router = Router()
    
    # Подключение роутеров
    main_router.include_router(onboarding_router)
    main_router.include_router(admin_router)
    main_router.include_router(profiles_router)
    main_router.include_router(monitoring_router)
    
    return main_router
