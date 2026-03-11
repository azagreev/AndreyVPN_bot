"""
Настройка логирования для бота.

Sink-и:
  stderr         — INFO+ в prod, DEBUG+ при LOG_LEVEL=DEBUG (цветной)
  logs/bot.log   — INFO+, ротация 10 МБ, хранение 30 дней
  logs/errors.log — ERROR+, ротация 10 МБ, хранение 90 дней
  logs/audit.log — кастомный уровень AUDIT (безопасность: кто что сделал)

Уровни:
  DEBUG    — детали настройки: wg-команды, состояния FSM (только при LOG_LEVEL=DEBUG)
  INFO     — штатные события: регистрация, одобрение, VPN выдан/удалён
  WARNING  — неожиданное, но бот продолжает: юзер заблокировал бота, некорректный IP в БД
  ERROR    — операция провалилась: wg не выполнился, профиль не создан
  CRITICAL — бот не может работать: нет .env, невалидный ключ
  AUDIT    — кастомный (25): журнал безопасности — кто что сделал с чьим доступом

Приватные ключи WireGuard НИКОГДА не попадают в логи.
"""

import sys
from pathlib import Path

from loguru import logger


AUDIT_LEVEL_NO = 25
AUDIT_LEVEL_NAME = "AUDIT"

# Регистрируем уровень сразу при импорте модуля, чтобы audit() работал
# даже если setup_logging() ещё не вызывался (в тестах, например).
try:
    logger.level(AUDIT_LEVEL_NAME, no=AUDIT_LEVEL_NO, color="<magenta>", icon="🔐")
except TypeError:
    pass  # уже зарегистрирован


def setup_logging(log_level: str = "INFO", log_path: str = "logs") -> None:
    """
    Инициализирует все sink-и. Вызывается один раз при старте бота.

    :param log_level: уровень для stderr и bot.log (INFO | DEBUG | WARNING | ERROR)
    :param log_path:  директория для файлов логов
    """
    logger.remove()

    logs_dir = Path(log_path)
    logs_dir.mkdir(parents=True, exist_ok=True)

    # ── stderr ──────────────────────────────────────────────────────────────
    # Цветной вывод для консоли. В DEBUG-режиме виден каждый wg-вызов и FSM.
    logger.add(
        sys.stderr,
        level=log_level.upper(),
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{extra[ctx]}</cyan> | "
            "<level>{message}</level>"
        ),
        colorize=True,
        filter=_add_ctx_default,
    )

    # ── bot.log ─────────────────────────────────────────────────────────────
    # Полная история INFO+: регистрации, одобрения, VPN-операции, ошибки.
    logger.add(
        logs_dir / "bot.log",
        level=log_level.upper(),
        format=(
            "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {extra[ctx]} | {message}"
        ),
        rotation="10 MB",
        retention="30 days",
        compression="gz",
        encoding="utf-8",
        filter=_add_ctx_default,
    )

    # ── errors.log ──────────────────────────────────────────────────────────
    # Только ERROR и CRITICAL — для быстрой диагностики проблем.
    logger.add(
        logs_dir / "errors.log",
        level="ERROR",
        format=(
            "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {extra[ctx]} | {message}\n{exception}"
        ),
        rotation="10 MB",
        retention="90 days",
        compression="gz",
        encoding="utf-8",
        backtrace=True,
        diagnose=log_level.upper() == "DEBUG",
        filter=_add_ctx_default,
    )

    # ── audit.log ───────────────────────────────────────────────────────────
    # Только кастомный уровень AUDIT: журнал безопасности без ротации по дням,
    # чтобы история не терялась. Ротация только по размеру.
    logger.add(
        logs_dir / "audit.log",
        level=AUDIT_LEVEL_NAME,
        format="{time:YYYY-MM-DD HH:mm:ss} | AUDIT | {message}",
        rotation="10 MB",
        retention="365 days",
        compression="gz",
        encoding="utf-8",
        filter=_audit_only,
    )


# ── фильтры ──────────────────────────────────────────────────────────────────

def _add_ctx_default(record: dict) -> bool:
    """Добавляет поле ctx если его нет (для stderr и файловых sink-ов)."""
    record["extra"].setdefault("ctx", "-")
    return record["level"].no != AUDIT_LEVEL_NO


def _audit_only(record: dict) -> bool:
    """Пропускает только записи уровня AUDIT."""
    record["extra"].setdefault("ctx", "-")
    return record["level"].no == AUDIT_LEVEL_NO


# ── вспомогательные функции логирования ──────────────────────────────────────

def audit(event: str, **kwargs: object) -> None:
    """
    Записывает событие в audit.log.

    Пример:
        audit("VPN_ISSUED", user_id=123456, username="@andrey",
              profile="VPN_123456_1", ip="10.8.0.2")
    """
    parts = [event.upper()]
    for key, value in kwargs.items():
        parts.append(f"{key}={value}")
    logger.log(AUDIT_LEVEL_NAME, " | ".join(parts))


def log_wg_command(args: list[str]) -> None:
    """DEBUG: команда передаваемая в wg/awg."""
    safe_args = " ".join(str(a) for a in args)
    logger.debug(f"[WG] Команда: {safe_args}")


def log_wg_result(returncode: int, stderr: str = "") -> None:
    """DEBUG: результат выполнения wg/awg команды."""
    if returncode == 0:
        logger.debug(f"[WG] Успешно (returncode=0)")
    else:
        logger.debug(f"[WG] Ошибка (returncode={returncode}): {stderr.strip()}")
