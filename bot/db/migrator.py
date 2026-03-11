"""
Движок миграций базы данных.

Использует PRAGMA user_version как версионный счётчик:
  - Атомарный (один int, встроен в SQLite)
  - Не зависит от таблиц (работает даже на пустой БД)
  - Обновляется в той же транзакции что и миграция

Использование:
    runner = MigrationRunner("/app/data/bot_data.db")
    await runner.run_pending(db)      # применить новые
    await runner.rollback_to(db, 0)  # откатить всё
    await runner.dry_run(db)         # показать план без применения
"""
from __future__ import annotations

import importlib
import shutil
from datetime import datetime
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING

import aiosqlite
from loguru import logger

if TYPE_CHECKING:
    pass

_MIGRATIONS_PKG = "bot.db.migrations"
_MIGRATIONS_DIR = Path(__file__).parent / "migrations"


class Migration:
    """Обёртка над модулем миграции."""

    def __init__(self, module: ModuleType) -> None:
        self._module = module
        self.migration_id: int = module.MIGRATION_ID
        self.description: str = module.DESCRIPTION

    async def up(self, db: aiosqlite.Connection) -> None:
        await self._module.up(db)

    async def down(self, db: aiosqlite.Connection) -> None:
        await self._module.down(db)

    def __repr__(self) -> str:
        return f"Migration({self.migration_id}: {self.description})"


class MigrationRunner:
    """Управляет применением и откатом миграций."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    # ── Вспомогательные ──────────────────────────────────────────────────────

    @staticmethod
    async def _get_version(db: aiosqlite.Connection) -> int:
        cursor = await db.execute("PRAGMA user_version")
        row = await cursor.fetchone()
        return row[0] if row else 0

    @staticmethod
    async def _set_version(db: aiosqlite.Connection, version: int) -> None:
        # PRAGMA нельзя параметризовать — используем f-string (только int!)
        await db.execute(f"PRAGMA user_version = {int(version)}")

    def _discover(self) -> list[Migration]:
        """Находит все файлы миграций, сортирует по MIGRATION_ID."""
        modules: list[Migration] = []
        for path in sorted(_MIGRATIONS_DIR.glob("m[0-9]*.py")):
            module_name = f"{_MIGRATIONS_PKG}.{path.stem}"
            try:
                module = importlib.import_module(module_name)
                if not hasattr(module, "MIGRATION_ID"):
                    logger.warning("Пропущен {}: нет MIGRATION_ID", path.name)
                    continue
                if not hasattr(module, "up") or not hasattr(module, "down"):
                    raise AttributeError(
                        f"{path.name}: обязательны функции up() и down()"
                    )
                modules.append(Migration(module))
            except Exception as exc:
                logger.error("Ошибка загрузки миграции {}: {}", path.name, exc)
                raise
        modules.sort(key=lambda m: m.migration_id)
        return modules

    async def _pending(
        self, db: aiosqlite.Connection
    ) -> tuple[int, list[Migration]]:
        current = await self._get_version(db)
        all_migrations = self._discover()
        pending = [m for m in all_migrations if m.migration_id > current]
        return current, pending

    def _backup(self) -> Path | None:
        """Создаёт резервную копию БД рядом с оригиналом."""
        src = Path(self._db_path)
        if not src.exists():
            return None
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dst = src.parent / f"{src.stem}.bak_{timestamp}{src.suffix}"
        shutil.copy2(src, dst)
        logger.info("[MIGRATION] Бэкап создан: {}", dst)
        return dst

    # ── Публичный API ─────────────────────────────────────────────────────────

    async def dry_run(self, db: aiosqlite.Connection) -> None:
        """Показывает план миграций без применения."""
        current, pending = await self._pending(db)
        if not pending:
            logger.info("[MIGRATION] Схема актуальна (user_version={})", current)
            return
        logger.info(
            "[MIGRATION] dry_run: текущая версия={}, ожидает {} миграций:",
            current, len(pending),
        )
        for m in pending:
            logger.info("  → [{}] {}", m.migration_id, m.description)

    async def run_pending(self, db: aiosqlite.Connection) -> int:
        """
        Применяет все pending-миграции.
        Создаёт бэкап перед первой миграцией.
        Каждая миграция — отдельная транзакция.
        Возвращает количество применённых миграций.
        """
        current, pending = await self._pending(db)
        if not pending:
            logger.debug("[MIGRATION] Схема актуальна (user_version={})", current)
            return 0

        logger.info(
            "[MIGRATION] Применяем {} миграций (текущая версия: {})",
            len(pending), current,
        )
        self._backup()

        applied = 0
        for migration in pending:
            logger.info(
                "[MIGRATION] → Применяем [{}] {}",
                migration.migration_id, migration.description,
            )
            try:
                await db.execute("BEGIN")
                await migration.up(db)
                await self._set_version(db, migration.migration_id)
                await db.execute("COMMIT")
                applied += 1
                logger.info(
                    "[MIGRATION] ✓ [{}] применена успешно",
                    migration.migration_id,
                )
            except Exception as exc:
                await db.execute("ROLLBACK")
                logger.error(
                    "[MIGRATION] ✗ [{}] провалена, откат: {}",
                    migration.migration_id, exc,
                )
                raise RuntimeError(
                    f"Migration {migration.migration_id} failed: {exc}"
                ) from exc

        logger.info(
            "[MIGRATION] Готово: применено {}, схема теперь версии {}",
            applied, migration.migration_id,
        )
        return applied

    async def rollback_to(
        self, db: aiosqlite.Connection, target_version: int
    ) -> int:
        """
        Откатывает схему до target_version включительно.
        Применяет down() в обратном порядке.
        Возвращает количество откаченных миграций.
        """
        current = await self._get_version(db)
        if current <= target_version:
            logger.info(
                "[MIGRATION] Откат не нужен: текущая={}, цель={}",
                current, target_version,
            )
            return 0

        all_migrations = self._discover()
        to_rollback = [
            m for m in reversed(all_migrations)
            if target_version < m.migration_id <= current
        ]

        logger.info(
            "[MIGRATION] Откат {} миграций с {} до {}",
            len(to_rollback), current, target_version,
        )
        self._backup()

        rolled_back = 0
        for migration in to_rollback:
            logger.info(
                "[MIGRATION] ← Откат [{}] {}",
                migration.migration_id, migration.description,
            )
            try:
                await db.execute("BEGIN")
                await migration.down(db)
                await self._set_version(db, migration.migration_id - 1)
                await db.execute("COMMIT")
                rolled_back += 1
                logger.info(
                    "[MIGRATION] ✓ [{}] откат успешен",
                    migration.migration_id,
                )
            except Exception as exc:
                await db.execute("ROLLBACK")
                logger.error(
                    "[MIGRATION] ✗ [{}] откат провалился: {}",
                    migration.migration_id, exc,
                )
                raise RuntimeError(
                    f"Rollback of migration {migration.migration_id} failed: {exc}"
                ) from exc

        logger.info(
            "[MIGRATION] Откат завершён: схема теперь версии {}",
            target_version,
        )
        return rolled_back
