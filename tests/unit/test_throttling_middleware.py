"""Тесты для ThrottlingMiddleware с LRU-кэшем."""
import asyncio
import time
import pytest
from unittest.mock import AsyncMock, MagicMock

from bot.middlewares.throttling_middleware import ThrottlingMiddleware, _LRUCache


class TestLRUCache:
    def test_get_default(self):
        cache = _LRUCache(maxsize=10)
        assert cache.get(1) == 0.0
        assert cache.get(1, default=5.0) == 5.0

    def test_set_and_get(self):
        cache = _LRUCache(maxsize=10)
        cache.set(1, 100.0)
        assert cache.get(1) == 100.0

    def test_lru_eviction(self):
        cache = _LRUCache(maxsize=3)
        cache.set(1, 1.0)
        cache.set(2, 2.0)
        cache.set(3, 3.0)
        # Добавить 4й элемент — должен вытеснить 1й (LRU)
        cache.set(4, 4.0)
        assert cache.get(1) == 0.0  # вытеснен
        assert cache.get(4) == 4.0

    def test_lru_move_to_end_on_get(self):
        cache = _LRUCache(maxsize=3)
        cache.set(1, 1.0)
        cache.set(2, 2.0)
        cache.set(3, 3.0)
        _ = cache.get(1)  # 1 теперь последний использованный
        cache.set(4, 4.0)  # вытеснит 2 (самый старый)
        assert cache.get(1) == 1.0  # 1 сохранился
        assert cache.get(2) == 0.0  # 2 вытеснен


@pytest.mark.asyncio
async def test_throttling_allows_first_message():
    middleware = ThrottlingMiddleware(rate_limit=1.0)
    handler = AsyncMock(return_value="ok")
    user = MagicMock()
    user.id = 1

    event = MagicMock()
    data = {"event_from_user": user}

    result = await middleware(handler, event, data)
    assert result == "ok"
    handler.assert_called_once()


@pytest.mark.asyncio
async def test_throttling_blocks_rapid_messages():
    middleware = ThrottlingMiddleware(rate_limit=10.0)
    handler = AsyncMock(return_value="ok")
    user = MagicMock()
    user.id = 2

    event = MagicMock()
    data = {"event_from_user": user}

    # Первый запрос проходит
    result1 = await middleware(handler, event, data)
    assert result1 == "ok"

    # Второй немедленный — блокируется
    result2 = await middleware(handler, event, data)
    assert result2 is None
    assert handler.call_count == 1


@pytest.mark.asyncio
async def test_throttling_allows_after_cooldown():
    middleware = ThrottlingMiddleware(rate_limit=0.05)
    handler = AsyncMock(return_value="ok")
    user = MagicMock()
    user.id = 3

    event = MagicMock()
    data = {"event_from_user": user}

    await middleware(handler, event, data)
    await asyncio.sleep(0.1)
    result = await middleware(handler, event, data)
    assert result == "ok"
    assert handler.call_count == 2


@pytest.mark.asyncio
async def test_throttling_different_users_independent():
    middleware = ThrottlingMiddleware(rate_limit=10.0)
    handler = AsyncMock(return_value="ok")

    user1 = MagicMock()
    user1.id = 10
    user2 = MagicMock()
    user2.id = 11

    event = MagicMock()

    result1 = await middleware(handler, event, {"event_from_user": user1})
    result2 = await middleware(handler, event, {"event_from_user": user2})
    assert result1 == "ok"
    assert result2 == "ok"


@pytest.mark.asyncio
async def test_throttling_no_user_passes():
    middleware = ThrottlingMiddleware(rate_limit=1.0)
    handler = AsyncMock(return_value="ok")
    event = MagicMock()
    data = {}  # нет event_from_user

    result = await middleware(handler, event, data)
    assert result == "ok"
