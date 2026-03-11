# Changelog

All notable changes to AndreyVPN_bot are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)
Versioning: [Semantic Versioning](https://semver.org/)

## [Unreleased]

## [1.2.0] - 2026-03-12
### Fixed
- `create_profile`: профиль больше не сохраняется в БД если синхронизация с WireGuard провалилась — поднимается `RuntimeError`, транзакция откатывается
- `delete_profile`: профиль больше не удаляется из БД если peer не был удалён с WG-сервера (возвращает `False` вместо `True`)
- `get_profile_config`: расшифровка приватного ключа обёрнута в `try/except` — при повреждённом ключе возвращает `None` и логирует ошибку вместо необработанного исключения
- Хендлеры `.conf` и `QR`: при `get_profile_config == None` теперь показывают пользователю сообщение об ошибке вместо молчаливого возврата
- `Dockerfile`: убрана строка `COPY .env .` — секреты больше не попадают в слои образа; переменные передаются через `environment` в docker-compose
- `main.py`: проверка `.env` при старте теперь пропускается если переменные окружения уже заданы (Docker-сценарий)

### Tests
- Добавлен `test_create_profile_raises_when_sync_fails` — WG недоступен → профиль не создаётся в БД
- Добавлен `test_delete_profile_server_removal_fails` — ошибка WG → `False`, `delete_vpn_profile` не вызывается
- Добавлен `test_get_profile_config_decrypt_failure_returns_none` — повреждённый ключ → `None` без исключения

## [1.1.0] - 2026-03-12
### Added
- Docker support with multi-stage Dockerfile and docker-compose.yml
- `WG_CONTAINER_NAME` — docker exec adapter for AmneziaWG container
- `bot/keyboards/` module — eliminates circular imports between handlers
- `bot/db/repository.py` — all SQL queries centralized in one place
- WAL mode for SQLite (`PRAGMA journal_mode = WAL`)
- Schema versioning via `PRAGMA user_version`
- LRU cache in ThrottlingMiddleware — no memory leak
- Rate limiting for VPN profile requests
- `docs/DOCKER.md` — full deployment guide

### Fixed
- Removed `aiosqlite.py` from project root that was shadowing the real
  pip package and blocking the event loop with synchronous sqlite3 calls
- VPNService no longer opens its own DB connections — accepts `db` param
- `AccessControlMiddleware` null-check for `from_user`
- `diagnose=True` in loguru now only enabled when `LOG_LEVEL=DEBUG`

### Changed
- `main.py` refactored to use `dp.run_polling()` with lifecycle hooks
- `DbMiddleware` now uses a single persistent connection opened at startup
- All circular inline imports replaced with `bot/keyboards/` module

## [1.0.0] - 2026-02-24
### Added
- Initial release
- Telegram bot for AmneziaWG VPN management
- User registration with math CAPTCHA
- Admin approval workflow with inline keyboard
- VPN profile generation (keys, IP assignment, WireGuard sync)
- QR code and .conf file delivery
- Monthly traffic tracking
- Fernet encryption for private keys in SQLite
- Audit logging with custom AUDIT level
- Full test suite: unit, integration, functional, regression
