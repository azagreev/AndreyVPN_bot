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
        yield db
