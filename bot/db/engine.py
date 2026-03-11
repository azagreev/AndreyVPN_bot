import aiosqlite
from loguru import logger

from bot.db.migrator import MigrationRunner


async def init_db(db_path: str) -> None:
    """
    Инициализирует базу данных и применяет все pending-миграции.

    Порядок:
      1. PRAGMA journal_mode = WAL  (concurrent reads)
      2. PRAGMA foreign_keys = ON   (referential integrity)
      3. MigrationRunner.run_pending() — создаёт таблицы и накатывает схему
    """
    try:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA journal_mode = WAL")
            await db.execute("PRAGMA foreign_keys = ON")

            runner = MigrationRunner(db_path)
            applied = await runner.run_pending(db)

            if applied == 0:
                logger.info("[STARTUP] База данных актуальна | path={}", db_path)
            else:
                logger.info(
                    "[STARTUP] База данных обновлена | path={} migrations={}",
                    db_path, applied,
                )

    except Exception as exc:
        logger.error("Ошибка при инициализации базы данных: {}", exc)
        raise
