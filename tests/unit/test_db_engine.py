"""Тесты для init_db с WAL mode."""
import pytest
import aiosqlite
from pathlib import Path

from bot.db.engine import init_db


@pytest.mark.asyncio
async def test_init_db_creates_tables(tmp_path: Path) -> None:
    db_path = str(tmp_path / "test.db")
    await init_db(db_path)

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = {row["name"] for row in await cursor.fetchall()}

    assert "users" in tables
    assert "vpn_profiles" in tables
    assert "approvals" in tables
    assert "configs" in tables
    assert "daily_stats" in tables


@pytest.mark.asyncio
async def test_init_db_wal_mode(tmp_path: Path) -> None:
    db_path = str(tmp_path / "test_wal.db")
    await init_db(db_path)

    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute("PRAGMA journal_mode")
        row = await cursor.fetchone()
        assert row[0] == "wal"


@pytest.mark.asyncio
async def test_init_db_idempotent(tmp_path: Path) -> None:
    """Повторный вызов init_db не должен падать."""
    db_path = str(tmp_path / "test_idem.db")
    await init_db(db_path)
    await init_db(db_path)  # второй вызов — не должно быть ошибок


@pytest.mark.asyncio
async def test_init_db_sets_schema_version(tmp_path: Path) -> None:
    db_path = str(tmp_path / "test_version.db")
    await init_db(db_path)

    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute("PRAGMA user_version")
        row = await cursor.fetchone()
        version = row[0] if row else 0
    assert version >= 1
