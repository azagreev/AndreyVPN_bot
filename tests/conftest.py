from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Callable
from unittest.mock import AsyncMock, MagicMock

import aiosqlite
import pytest
import pytest_asyncio
from aiogram import Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Chat, Message, User
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
        yield db


# ---------------------------------------------------------------------------
# aiogram mock fixtures for handler / middleware testing
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_bot() -> AsyncMock:
    bot = AsyncMock(spec=Bot)
    bot.send_message = AsyncMock()
    bot.send_photo = AsyncMock()
    bot.send_document = AsyncMock()
    return bot


@pytest.fixture
def mock_user() -> User:
    return User(id=12345, is_bot=False, first_name="Test", username="testuser")


@pytest.fixture
def admin_user() -> User:
    return User(id=settings.admin_id, is_bot=False, first_name="Admin", username="admin")


def _make_message(user: User, text: str = "") -> AsyncMock:
    msg = AsyncMock(spec=Message)
    msg.from_user = user
    msg.text = text
    msg.chat = MagicMock(spec=Chat)
    msg.chat.id = user.id
    msg.answer = AsyncMock()
    return msg


def _make_callback_query(user: User, data: str = "", message: AsyncMock | None = None) -> AsyncMock:
    cq = AsyncMock(spec=CallbackQuery)
    cq.from_user = user
    cq.data = data
    cq.answer = AsyncMock()
    cq.message = message or _make_message(user)
    cq.message.edit_text = AsyncMock()
    cq.message.answer = AsyncMock()
    cq.message.text = ""
    return cq


@pytest.fixture
def make_message() -> Callable[..., AsyncMock]:
    return _make_message


@pytest.fixture
def make_callback_query() -> Callable[..., AsyncMock]:
    return _make_callback_query


@pytest_asyncio.fixture
async def fsm_context() -> FSMContext:
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=12345, user_id=12345)
    return FSMContext(storage=storage, key=key)
