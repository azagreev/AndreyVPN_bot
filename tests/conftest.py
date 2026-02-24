import pytest
import pytest_asyncio
import aiosqlite
import os
from unittest.mock import AsyncMock, patch

@pytest_asyncio.fixture
async def temp_db():
    """
    Создает временную БД для тестов с актуальной схемой.
    """
    db_path = "test_bot_v4.db"
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        # Создаем необходимые таблицы
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                is_approved BOOLEAN DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS vpn_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                name TEXT,
                private_key TEXT,
                public_key TEXT,
                ipv4_address TEXT,
                monthly_offset_bytes INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(telegram_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS configs (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        await db.commit()
        yield db
    
    if os.path.exists(db_path):
        try:
            os.remove(db_path)
        except:
            pass

@pytest.fixture
def mock_subprocess():
    """
    Мок для asyncio.create_subprocess_exec (wg/awg calls).
    """
    with patch("asyncio.create_subprocess_exec") as mock:
        process = AsyncMock()
        # По умолчанию возвращает успешный пустой ответ
        process.communicate.return_value = (b"mock_stdout\n", b"")
        process.returncode = 0
        mock.return_value = process
        yield mock

@pytest.fixture
def encryption_key():
    """
    Валидный ключ Fernet для тестов.
    """
    from cryptography.fernet import Fernet
    return Fernet.generate_key().decode()
