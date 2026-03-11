from aiogram import Router, F
from aiogram.types import CallbackQuery, ErrorEvent
from loguru import logger

from bot.handlers.common.start import router as start_router
from bot.handlers.user import setup_user_handlers
from bot.handlers.admin import setup_admin_handlers


def setup_handlers() -> Router:
    main_router = Router()

    # Заглушка для нажатий на некликабельные элементы списков
    @main_router.callback_query(F.data == "noop")
    async def handle_noop(callback: CallbackQuery):
        await callback.answer()

    # Глобальный обработчик необработанных исключений
    @main_router.errors()
    async def global_error_handler(event: ErrorEvent) -> bool:
        logger.error(
            "Необработанное исключение | update_type={} exception={}",
            event.update.event_type if event.update else "unknown",
            event.exception,
            exc_info=True,
        )
        return True

    # Сначала admin-роутеры (выше приоритет для admin_id)
    main_router.include_router(setup_admin_handlers())

    # Общие хендлеры (/start, капча)
    main_router.include_router(start_router)

    # Пользовательские хендлеры
    main_router.include_router(setup_user_handlers())

    return main_router
