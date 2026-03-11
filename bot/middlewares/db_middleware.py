import aiosqlite
from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
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
            db.row_factory = aiosqlite.Row
            # Включаем foreign keys для каждого соединения (SQLite PRAGMA действует per-connection)
            await db.execute("PRAGMA foreign_keys = ON")
            data["db"] = db
            return await handler(event, data)
