import aiosqlite
from loguru import logger
from bot.db.models import ALL_TABLES


async def init_db(db_path: str):
    """
    Инициализирует базу данных: создает таблицы, если они не существуют.
    
    :param db_path: Путь к файлу базы данных SQLite.
    """
    try:
        async with aiosqlite.connect(db_path) as db:
            logger.info(f"Подключение к базе данных по пути: {db_path}")
            
            for table_query in ALL_TABLES:
                await db.execute(table_query)
            
            await db.commit()
            logger.success("Инициализация базы данных успешно завершена. Все таблицы созданы.")
            
    except Exception as e:
        logger.error(f"Ошибка при инициализации базы данных: {e}")
        raise e
