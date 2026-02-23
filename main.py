import asyncio
import os
import sys
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from loguru import logger
from bot.core.config import settings
from bot.db.engine import init_db
from bot.middlewares.db_middleware import DbMiddleware
from bot.middlewares.access_middleware import AccessControlMiddleware
from bot.handlers import setup_handlers


async def main():
    """
    Главная функция запуска бота.
    """
    # Настройка логирования через loguru
    logger.remove()
    logger.add(
        sys.stderr, 
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level="INFO"
    )
    
    # Проверка наличия .env файла перед запуском
    if not os.path.exists(".env"):
        logger.error("Файл .env не найден. Скопируйте .env.example в .env и заполните его.")
        sys.exit(1)
    
    # Инициализация базы данных
    try:
        await init_db(settings.db_path)
    except Exception as e:
        logger.error(f"Не удалось инициализировать базу данных: {e}")
        sys.exit(1)
    
    # Создание бота и диспетчера
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()
    
    # Регистрация Middlewares
    dp.update.outer_middleware(DbMiddleware())
    dp.update.outer_middleware(AccessControlMiddleware())
    
    # Регистрация Хендлеров
    dp.include_router(setup_handlers())
    
    # Запуск polling
    logger.info("Бот запущен и готов к работе.")
    
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен.")
