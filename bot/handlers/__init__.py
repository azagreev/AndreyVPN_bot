from aiogram import Router
from bot.handlers.onboarding import router as onboarding_router

def setup_handlers() -> Router:
    """
    Создает основной роутер и подключает в него все остальные.
    """
    main_router = Router()
    
    # Подключение роутеров
    main_router.include_router(onboarding_router)
    
    return main_router
