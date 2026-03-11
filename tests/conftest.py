import os

# Устанавливаем тестовые переменные окружения ДО импорта settings,
# чтобы pydantic-settings мог их подхватить при инициализации.
os.environ.setdefault("BOT_TOKEN", "1234567890:test_token_for_pytest")
os.environ.setdefault("ADMIN_ID", "999")
os.environ.setdefault("ENCRYPTION_KEY", "dGVzdF9lbmNyeXB0aW9uX2tleV8zMl9ieXRlc18=")

from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import aiosqlite
import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from pydantic import SecretStr

from bot.core.config import settings
from bot.db.engine import init_db
from bot.services.vpn_service import VPNService


@pytest.fixture
def fernet_key() -> str:
    return Fernet.generate_key().decode("utf-8")


@pytest.fixture(autouse=True)
def reset_vpn_service_cache() -> Iterator[None]:
    VPNService.reset_cache()
    yield
    VPNService.reset_cache()


@pytest.fixture
def test_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, fernet_key: str) -> Path:
    db_path = tmp_path / "test_bot_v6.db"
    monkeypatch.setattr(settings, "db_path", str(db_path), raising=False)
    monkeypatch.setattr(settings, "vpn_ip_range", "10.0.0.0/29", raising=False)
    monkeypatch.setattr(settings, "encryption_key", SecretStr(fernet_key), raising=False)
    monkeypatch.setattr(settings, "wg_interface", "awg0", raising=False)
    monkeypatch.setattr(settings, "server_pub_key", "test_server_public_key", raising=False)
    monkeypatch.setattr(settings, "server_endpoint", "198.51.100.10:51820", raising=False)
    monkeypatch.setattr(settings, "dns_servers", "1.1.1.1, 8.8.8.8", raising=False)
    return db_path


@pytest_asyncio.fixture
async def prepared_db(test_settings: Path) -> AsyncIterator[Path]:
    await init_db(str(test_settings))
    yield test_settings


@pytest_asyncio.fixture
async def db_connection(prepared_db: Path) -> AsyncIterator[aiosqlite.Connection]:
    async with aiosqlite.connect(prepared_db) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA journal_mode = WAL")
        yield db


# ---------------------------------------------------------------------------
# Вспомогательные фабрики и фикстуры для юнит/интеграционных тестов
# ---------------------------------------------------------------------------

import pytest
from unittest.mock import AsyncMock, MagicMock
from aiogram.types import Message, CallbackQuery


@pytest.fixture
def admin_id(monkeypatch):
    """Фиксированный admin_id для тестов."""
    from bot.core.config import settings
    monkeypatch.setattr(settings, "admin_id", 999, raising=False)
    return 999


def make_user(user_id: int, username: str = None, full_name: str = "Test User"):
    user = MagicMock()
    user.id = user_id
    user.username = username
    user.full_name = full_name
    return user


def make_message(user_id: int, text: str = "", username: str = None, full_name: str = "Test User"):
    # spec=Message позволяет isinstance(mock, Message) вернуть True
    message = MagicMock(spec=Message)
    message.from_user = make_user(user_id, username, full_name)
    message.text = text
    message.answer = AsyncMock()
    return message


def make_callback(user_id: int, data: str = "", message_text: str = "Test"):
    # spec=CallbackQuery позволяет isinstance(mock, CallbackQuery) вернуть True
    callback = MagicMock(spec=CallbackQuery)
    callback.from_user = make_user(user_id)
    callback.data = data
    callback.message = MagicMock()
    callback.message.text = message_text
    callback.message.edit_text = AsyncMock()
    callback.message.edit_reply_markup = AsyncMock()
    callback.message.answer = AsyncMock()
    callback.answer = AsyncMock()
    return callback


def make_bot():
    bot = AsyncMock()
    bot.send_message = AsyncMock()
    bot.send_photo = AsyncMock()
    bot.send_document = AsyncMock()
    return bot


def make_state():
    state = AsyncMock()
    state.get_state = AsyncMock(return_value=None)
    state.get_data = AsyncMock(return_value={})
    state.update_data = AsyncMock()
    state.set_state = AsyncMock()
    state.clear = AsyncMock()
    return state


@pytest.fixture
def bot():
    return make_bot()


@pytest.fixture
def mock_message():
    return make_message


@pytest.fixture
def mock_callback():
    return make_callback
