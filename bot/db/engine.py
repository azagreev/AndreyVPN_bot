import aiosqlite
from loguru import logger
from bot.db.models import ALL_TABLES
from bot.db.repository import get_schema_version, set_schema_version

CURRENT_SCHEMA_VERSION = 1


async def init_db(db_path: str) -> None:
    try:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA foreign_keys = ON")
            await db.execute("PRAGMA journal_mode = WAL")
            logger.info(f"Подключение к базе данных по пути: {db_path}")

            for table_query in ALL_TABLES:
                await db.execute(table_query)
            await db.commit()

            version = await get_schema_version(db)
            if version < CURRENT_SCHEMA_VERSION:
                await set_schema_version(db, CURRENT_SCHEMA_VERSION)
                logger.info(f"[STARTUP] Схема БД обновлена до версии {CURRENT_SCHEMA_VERSION}")

            logger.success("Инициализация базы данных успешно завершена. Все таблицы созданы.")

    except Exception as e:
        logger.error(f"Ошибка при инициализации базы данных: {e}")
        raise
