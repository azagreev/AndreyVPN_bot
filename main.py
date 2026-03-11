import asyncio
import os
import sys

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from loguru import logger

from bot.core.config import settings
from bot.core.logging import setup_logging
from bot.db.engine import init_db
from bot.middlewares.db_middleware import DbMiddleware
from bot.middlewares.access_middleware import AccessControlMiddleware
from bot.middlewares.throttling_middleware import ThrottlingMiddleware
from bot.handlers import setup_handlers


async def main():
    # Проверка .env до инициализации логирования, чтобы ошибка была видна
    if not os.path.exists(".env"):
        print(
            "CRITICAL | [STARTUP] Файл .env не найден. "
            "Скопируйте .env.example в .env и заполните его.",
            file=sys.stderr,
        )
        sys.exit(1)

    setup_logging(log_level=settings.log_level, log_path=settings.log_path)

    logger.info("[STARTUP] Инициализация | log_level={} log_path={}", settings.log_level, settings.log_path)
    logger.debug("[STARTUP] Настройки загружены | interface={} ip_range={} admin_id={}",
                 settings.wg_interface, settings.vpn_ip_range, settings.admin_id)

    # Проверка ключа шифрования
    if not settings.encryption_key:
        logger.critical("[STARTUP] ENCRYPTION_KEY не задан — приватные ключи WireGuard не будут зашифрованы")
        sys.exit(1)

    # Инициализация базы данных
    try:
        await init_db(settings.db_path)
        logger.info("[STARTUP] База данных инициализирована | path={}", settings.db_path)
    except Exception as e:
        logger.critical("[STARTUP] Не удалось инициализировать базу данных: {}", e)
        sys.exit(1)

    # FSM Storage: Redis (если задан REDIS_URL) или MemoryStorage
    if settings.redis_url:
        try:
            from aiogram.fsm.storage.redis import RedisStorage
            storage = RedisStorage.from_url(settings.redis_url)
            logger.info("[STARTUP] FSM Storage: Redis | url={}...", settings.redis_url[:30])
        except ImportError:
            logger.warning("[STARTUP] aiogram-redis не установлен, используется MemoryStorage")
            storage = MemoryStorage()
    else:
        storage = MemoryStorage()
        logger.warning(
            "[STARTUP] FSM Storage: MemoryStorage — состояния FSM теряются при рестарте. "
            "Для production задайте REDIS_URL в .env"
        )

    # Создание бота и диспетчера
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=storage)

    # Middleware: порядок важен — DbMiddleware должна быть первой (AccessControl зависит от db)
    dp.update.outer_middleware(DbMiddleware())
    dp.update.outer_middleware(AccessControlMiddleware())
    dp.update.outer_middleware(ThrottlingMiddleware(rate_limit=0.7))

    dp.include_router(setup_handlers())

    logger.info("[STARTUP] Бот запущен | admin_id={} interface={}", settings.admin_id, settings.wg_interface)

    try:
        await dp.start_polling(
            bot,
            allowed_updates=["message", "callback_query"],
            drop_pending_updates=True,
        )
    finally:
        await bot.session.close()
        logger.info("[SHUTDOWN] Бот остановлен")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
