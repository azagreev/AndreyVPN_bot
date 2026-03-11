"""
Middleware для защиты от флуда.

Апдейты, пришедшие раньше чем через rate_limit секунд после предыдущего
от того же пользователя, молча отбрасываются — handler не вызывается.
Счётчик хранится в памяти процесса (достаточно для single-instance бота).
"""

import time
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject


class ThrottlingMiddleware(BaseMiddleware):
    """Ограничивает частоту обработки апдейтов от одного пользователя."""

    def __init__(self, rate_limit: float = 0.7) -> None:
        self.rate_limit = rate_limit
        self._last_time: dict[int, float] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user:
            now = time.monotonic()
            last = self._last_time.get(user.id, 0.0)
            if now - last < self.rate_limit:
                return None  # отбрасываем — spinner остановится по таймауту
            self._last_time[user.id] = now
        return await handler(event, data)
