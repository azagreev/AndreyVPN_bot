import asyncio
import os
import sys

import aiosqlite
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


def main() -> None:
    # Проверка .env до инициализации логирования.
    # В Docker переменные приходят из окружения — файл не нужен.
    if not os.path.exists(".env") and not os.environ.get("BOT_TOKEN"):
        print(
            "CRITICAL | [STARTUP] Файл .env не найден и переменные окружения не заданы. "
            "Скопируйте .env.example в .env и заполните его.",
            file=sys.stderr,
        )
        sys.exit(1)

    setup_logging(log_level=settings.log_level, log_path=settings.log_path)

    logger.info(
        "[STARTUP] Инициализация | log_level={} log_path={}",
        settings.log_level,
        settings.log_path,
    )

    if not settings.encryption_key:
        logger.critical("[STARTUP] ENCRYPTION_KEY не задан — приватные ключи WireGuard не будут зашифрованы")
        sys.exit(1)

    # FSM Storage
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

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=storage)

    # ── Lifecycle hooks ────────────────────────────────────────────────────────
    async def on_startup() -> None:
        # Инициализация БД
        try:
            await init_db(settings.db_path)
            logger.info("[STARTUP] База данных инициализирована | path={}", settings.db_path)
        except Exception as e:
            logger.critical("[STARTUP] Не удалось инициализировать базу данных: {}", e)
            sys.exit(1)

        # Открываем долгоживущее соединение
        db = await aiosqlite.connect(settings.db_path)
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute("PRAGMA journal_mode = WAL")
        dp["db"] = db

        # Регистрируем middlewares с готовым соединением
        dp.update.outer_middleware(DbMiddleware(db))
        dp.update.outer_middleware(AccessControlMiddleware())
        dp.update.outer_middleware(ThrottlingMiddleware(rate_limit=0.7))

        dp.include_router(setup_handlers())
        logger.info(
            "[STARTUP] Бот запущен | admin_id={} interface={} container={}",
            settings.admin_id,
            settings.wg_interface,
            settings.wg_container_name or "direct",
        )

    async def on_shutdown() -> None:
        db: aiosqlite.Connection | None = dp.get("db")
        if db:
            await db.close()
            logger.info("[SHUTDOWN] Соединение с БД закрыто")
        logger.info("[SHUTDOWN] Бот остановлен")

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    # run_polling — синхронная обёртка с правильным lifecycle management
    dp.run_polling(
        bot,
        allowed_updates=["message", "callback_query"],
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
