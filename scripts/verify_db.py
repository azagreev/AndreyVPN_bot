import asyncio
import os
import sqlite3
import sys
from loguru import logger

# Добавляем корневую директорию проекта в sys.path для импорта бота
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.core.config import settings


async def verify_db():
    """
    Проверяет существование необходимых таблиц в базе данных.
    """
    db_path = settings.db_path
    
    if not os.path.exists(db_path):
        logger.error(f"Файл базы данных '{db_path}' не найден.")
        return False
    
    expected_tables = ["users", "approvals", "daily_stats", "configs"]
    
    try:
        # Используем стандартный sqlite3 для простой синхронной проверки
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Получаем список всех существующих таблиц
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        existing_tables = [row[0] for row in cursor.fetchall()]
        
        missing_tables = []
        for table in expected_tables:
            if table not in existing_tables:
                missing_tables.append(table)
        
        if not missing_tables:
            logger.success(f"База данных '{db_path}' корректна. Все таблицы на месте: {', '.join(expected_tables)}.")
            return True
        else:
            logger.error(f"В базе данных отсутствуют таблицы: {', '.join(missing_tables)}.")
            return False
            
    except Exception as e:
        logger.error(f"Ошибка при проверке базы данных: {e}")
        return False
    finally:
        if 'conn' in locals():
            conn.close()


if __name__ == "__main__":
    asyncio.run(verify_db())
