"""
Юнит-тесты для AdminFilter.

Проверяют что фильтр корректно пропускает администратора
и блокирует всех остальных пользователей.
"""
import pytest
from unittest.mock import MagicMock

from tests.conftest import make_message, make_callback


@pytest.fixture(autouse=True)
def patch_admin_id(monkeypatch):
    from bot.core.config import settings
    monkeypatch.setattr(settings, "admin_id", 999, raising=False)


async def test_admin_filter_allows_admin():
    """AdminFilter возвращает True когда from_user.id == settings.admin_id."""
    from bot.filters.admin import AdminFilter

    event = MagicMock()
    event.from_user = MagicMock()
    event.from_user.id = 999

    result = await AdminFilter()(event)
    assert result is True, "AdminFilter должен пропускать администратора"


async def test_admin_filter_blocks_non_admin():
    """AdminFilter возвращает False когда from_user.id != settings.admin_id."""
    from bot.filters.admin import AdminFilter

    event = MagicMock()
    event.from_user = MagicMock()
    event.from_user.id = 12345

    result = await AdminFilter()(event)
    assert result is False, "AdminFilter должен блокировать не-администратора"


async def test_admin_filter_blocks_none_user():
    """AdminFilter возвращает False когда from_user is None."""
    from bot.filters.admin import AdminFilter

    event = MagicMock()
    event.from_user = None

    result = await AdminFilter()(event)
    assert result is False, "AdminFilter должен возвращать False при from_user=None"


async def test_admin_filter_with_message():
    """AdminFilter корректно работает с mock объектом типа Message."""
    from bot.filters.admin import AdminFilter

    message = make_message(user_id=999, text="/admin")
    result = await AdminFilter()(message)
    assert result is True, "AdminFilter должен пропускать сообщение от администратора"

    message_non_admin = make_message(user_id=111, text="/admin")
    result = await AdminFilter()(message_non_admin)
    assert result is False, "AdminFilter должен блокировать сообщение от обычного пользователя"


async def test_admin_filter_with_callback():
    """AdminFilter корректно работает с mock объектом типа CallbackQuery."""
    from bot.filters.admin import AdminFilter

    callback = make_callback(user_id=999, data="some:data")
    result = await AdminFilter()(callback)
    assert result is True, "AdminFilter должен пропускать callback от администратора"

    callback_non_admin = make_callback(user_id=777, data="some:data")
    result = await AdminFilter()(callback_non_admin)
    assert result is False, "AdminFilter должен блокировать callback от не-администратора"
