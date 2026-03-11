import aiosqlite
from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject


class DbMiddleware(BaseMiddleware):
    """
    Middleware для внедрения соединения с базой данных SQLite в каждый апдейт.
    Соединение создаётся один раз при старте бота через lifecycle hook (on_startup)
    и передаётся в handlers через data["db"].
    """

    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db
        super().__init__()

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        data["db"] = self._db
        return await handler(event, data)
