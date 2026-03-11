"""Тесты для MigrationRunner (bot/db/migrator.py)."""
from pathlib import Path

import aiosqlite
import pytest

from bot.db.migrator import MigrationRunner


# ── Вспомогательная функция ──────────────────────────────────────────────────

async def get_user_version(db: aiosqlite.Connection) -> int:
    cursor = await db.execute("PRAGMA user_version")
    row = await cursor.fetchone()
    return row[0] if row else 0


# ── Тесты ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fresh_db_has_version_zero(tmp_path: Path) -> None:
    """Новая БД имеет user_version = 0."""
    db_path = str(tmp_path / "test.db")
    async with aiosqlite.connect(db_path) as db:
        version = await get_user_version(db)
    assert version == 0


@pytest.mark.asyncio
async def test_run_pending_applies_migration(tmp_path: Path) -> None:
    """run_pending применяет m001 на пустой БД и возвращает 1."""
    db_path = str(tmp_path / "test.db")
    runner = MigrationRunner(db_path)
    async with aiosqlite.connect(db_path) as db:
        applied = await runner.run_pending(db)
    assert applied == 1


@pytest.mark.asyncio
async def test_run_pending_sets_user_version(tmp_path: Path) -> None:
    """После run_pending user_version == max MIGRATION_ID."""
    db_path = str(tmp_path / "test.db")
    runner = MigrationRunner(db_path)
    async with aiosqlite.connect(db_path) as db:
        await runner.run_pending(db)
        version = await get_user_version(db)
    assert version == 1


@pytest.mark.asyncio
async def test_run_pending_idempotent(tmp_path: Path) -> None:
    """Повторный run_pending возвращает 0 (нечего применять)."""
    db_path = str(tmp_path / "test.db")
    runner = MigrationRunner(db_path)
    async with aiosqlite.connect(db_path) as db:
        await runner.run_pending(db)
        applied = await runner.run_pending(db)
    assert applied == 0


@pytest.mark.asyncio
async def test_run_pending_creates_tables(tmp_path: Path) -> None:
    """После run_pending таблицы users и vpn_profiles существуют."""
    db_path = str(tmp_path / "test.db")
    runner = MigrationRunner(db_path)
    async with aiosqlite.connect(db_path) as db:
        await runner.run_pending(db)
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = {row["name"] for row in await cursor.fetchall()}
    assert "users" in tables
    assert "vpn_profiles" in tables
    assert "approvals" in tables


@pytest.mark.asyncio
async def test_rollback_to_zero(tmp_path: Path) -> None:
    """rollback_to(0) откатывает все таблицы и ставит user_version=0."""
    db_path = str(tmp_path / "test.db")
    runner = MigrationRunner(db_path)
    async with aiosqlite.connect(db_path) as db:
        await runner.run_pending(db)
        rolled = await runner.rollback_to(db, 0)
        version = await get_user_version(db)
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = {row[0] for row in await cursor.fetchall()}
    assert rolled == 1
    assert version == 0
    assert "users" not in tables


@pytest.mark.asyncio
async def test_rollback_noop_when_already_at_target(tmp_path: Path) -> None:
    """rollback_to(0) на пустой БД (version=0) возвращает 0."""
    db_path = str(tmp_path / "test.db")
    runner = MigrationRunner(db_path)
    async with aiosqlite.connect(db_path) as db:
        rolled = await runner.rollback_to(db, 0)
    assert rolled == 0


@pytest.mark.asyncio
async def test_backup_created_on_migration(tmp_path: Path) -> None:
    """run_pending создаёт бэкап рядом с БД (файл .bak_YYYYMMDD_HHMMSS.db)."""
    db_path = str(tmp_path / "test.db")
    # Создаём файл БД заранее — иначе бэкапить нечего
    Path(db_path).touch()
    runner = MigrationRunner(db_path)
    async with aiosqlite.connect(db_path) as db:
        await runner.run_pending(db)
    backups = list(tmp_path.glob("test.bak_*.db"))
    assert len(backups) >= 1


@pytest.mark.asyncio
async def test_dry_run_does_not_apply(tmp_path: Path) -> None:
    """dry_run не применяет миграции, версия остаётся 0."""
    db_path = str(tmp_path / "test.db")
    runner = MigrationRunner(db_path)
    async with aiosqlite.connect(db_path) as db:
        await runner.dry_run(db)
        version = await get_user_version(db)
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        tables = [row[0] for row in await cursor.fetchall()]
    assert version == 0
    assert "users" not in tables


@pytest.mark.asyncio
async def test_discover_returns_sorted_migrations(tmp_path: Path) -> None:
    """_discover() возвращает миграции в порядке возрастания MIGRATION_ID."""
    db_path = str(tmp_path / "test.db")
    runner = MigrationRunner(db_path)
    migrations = runner._discover()
    ids = [m.migration_id for m in migrations]
    assert ids == sorted(ids)
    assert len(ids) >= 1
