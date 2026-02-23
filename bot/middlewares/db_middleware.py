import aiosqlite
from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from loguru import logger
from bot.core.config import settings


class DbMiddleware(BaseMiddleware):
    """
    Middleware для внедрения соединения с базой данных SQLite в каждый апдейт.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        # Открываем асинхронное соединение с базой данных
        async with aiosqlite.connect(settings.db_path) as db:
            # Устанавливаем фабрику строк для удобного доступа к полям через названия
            db.row_factory = aiosqlite.Row
            
            # Передаем объект соединения в данные, доступные в хендлерах
            data["db"] = db
            
            # Продолжаем обработку события
            return await handler(event, data)
