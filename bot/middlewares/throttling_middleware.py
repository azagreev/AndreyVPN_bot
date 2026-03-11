"""
Middleware для защиты от флуда.

Апдейты, пришедшие раньше чем через rate_limit секунд после предыдущего
от того же пользователя, молча отбрасываются.
Счётчик хранится в LRU-кэше (maxsize=10_000), чтобы не было утечки памяти.
"""

import time
from collections import OrderedDict
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject


class _LRUCache:
    """Простой LRU-кэш с ограничением по размеру."""

    def __init__(self, maxsize: int) -> None:
        self._maxsize = maxsize
        self._cache: OrderedDict[int, float] = OrderedDict()

    def get(self, key: int, default: float = 0.0) -> float:
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        return default

    def set(self, key: int, value: float) -> None:
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = value
        if len(self._cache) > self._maxsize:
            self._cache.popitem(last=False)


class ThrottlingMiddleware(BaseMiddleware):
    """Ограничивает частоту обработки апдейтов от одного пользователя."""

    def __init__(self, rate_limit: float = 0.7, maxsize: int = 10_000) -> None:
        self.rate_limit = rate_limit
        self._last_time: _LRUCache = _LRUCache(maxsize=maxsize)

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user:
            now = time.monotonic()
            last = self._last_time.get(user.id)
            if now - last < self.rate_limit:
                return None
            self._last_time.set(user.id, now)
        return await handler(event, data)
