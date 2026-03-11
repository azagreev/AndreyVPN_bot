import logging
import asyncio
import os
import sqlite3
import sys

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# Mock logger.success for compatibility with existing code
def logger_success(msg):
    logger.info(f"SUCCESS: {msg}")

logger.success = logger_success

# Добавляем корневую директорию проекта в sys.path для импорта бота
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.core.config import settings
from bot.handlers import setup_handlers

async def verify_phase2():
    """
    Проверяет успешность выполнения Фазы 2.
    """
    logger.info("Начало верификации Фазы 2...")
    success = True

    # 1. Проверка роутеров
    try:
        main_router = setup_handlers()
        # В aiogram 3.x sub_routers - это список подключенных роутеров
        # Мы ожидаем как минимум 2: onboarding и admin
        routers_count = len(main_router.sub_routers)
        if routers_count >= 2:
            logger.success(f"Роутеры зарегистрированы корректно (всего: {routers_count})")
        else:
            logger.error(f"Недостаточно роутеров: ожидалось как минимум 2, найдено {routers_count}")
            success = False
    except Exception as e:
        logger.error(f"Ошибка при проверке роутеров: {e}")
        success = False

    # 2. Проверка базы данных
    db_path = settings.db_path
    if not os.path.exists(db_path):
        logger.error(f"Файл базы данных '{db_path}' не найден.")
        return False

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Проверка таблицы users и поля is_approved
        cursor.execute("PRAGMA table_info(users)")
        columns = {row['name']: row for row in cursor.fetchall()}
        
        if 'is_approved' in columns:
            logger.success("Таблица 'users' содержит поле 'is_approved'")
        else:
            logger.error("В таблице 'users' отсутствует поле 'is_approved'")
            success = False

        # Проверка таблицы approvals
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='approvals';")
        if cursor.fetchone():
            logger.success("Таблица 'approvals' существует")
        else:
            logger.error("Таблица 'approvals' отсутствует")
            success = False

        conn.close()
    except Exception as e:
        logger.error(f"Ошибка при проверке базы данных: {e}")
        success = False

    if success:
        logger.success("Верификация Фазы 2 пройдена успешно! 🎉")
    else:
        logger.error("Верификация Фазы 2 НЕ пройдена. ❌")
    
    return success

if __name__ == "__main__":
    result = asyncio.run(verify_phase2())
    sys.exit(0 if result else 1)
