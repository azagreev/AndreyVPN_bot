# Changelog

All notable changes to AndreyVPN_bot are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)
Versioning: [Semantic Versioning](https://semver.org/)

## [Unreleased]

## [1.2.1] - 2026-03-12
### Fixed (Incident: полная деградация VPN-сервиса после рестарта)
- **Docker binary resolution:** `_resolve_wg_binary()` теперь возвращает bare `"awg"` в Docker-режиме (`WG_CONTAINER_NAME` задан) вместо поиска бинарника на хосте через `shutil.which`
- **Docker exec stdin:** `_build_command()` поддерживает флаг `interactive=True`, добавляющий `-i` к `docker exec` для команд, читающих stdin (`awg pubkey`)
- **Docker socket permissions:** `Dockerfile` принимает `DOCKER_GID` build arg и создаёт группу `dockerhost` для доступа к `/var/run/docker.sock`
- **Peer persistence:** новый метод `save_interface_config()` сохраняет runtime-состояние WG через `awg-quick save` после каждого `sync_peer_with_server()` и `remove_peer_from_server()` — пиры больше не теряются при рестарте контейнера
- **Peer recovery on startup:** `recover_all_peers()` при старте бота пересинхронизирует все профили из БД на WG-сервер с одним вызовом `awg-quick save` в конце
- **SERVER_PUB_KEY validation:** формат ключа проверяется как base64 (44 символа) при старте; при запуске выполняется runtime-сверка с `awg show <interface> public-key` — несоответствие логируется как WARNING

### Added
- Параметры обфускации `S3`, `S4`, `I1` (AmneziaWG extensions) — условно включаются в клиентский конфиг когда значение ≠ 0
- `_resolve_wg_quick_binary()` для команд `awg-quick` / `wg-quick`
- `get_all_active_profiles()` в `repository.py` — для peer recovery при старте
- `DOCKER_GID` в `.env.example` и `docker-compose.yml`
- `S3`, `S4`, `I1` в `.env.example` и `docker-compose.yml`

### Tests
- 19 новых тестов в `tests/test_incident_fixes.py`: Docker-mode binary resolution, `-i` flag, S3/S4/I1 config, `save_interface_config`, `recover_all_peers`, SERVER_PUB_KEY format
- `conftest.py`: `wg_container_name=""` в `test_settings` для обратной совместимости
- Итого: **183 теста** (было 165)

## [1.2.0] - 2026-03-12
### Added
- Лимит VPN профилей на пользователя: `MAX_PROFILES_PER_USER` (по умолч. 3). Проверка на стороне пользователя (при запросе) и на стороне администратора (при выдаче)
- TTL 24ч для `_pending_vpn_requests`: после истечения пользователь может повторно запросить профиль без участия администратора. При достижении лимита профилей TTL не устанавливается
- Валидация конфигурации WireGuard при старте: `VPN_IP_RANGE` (корректный CIDR с ≥2 хостами), `SERVER_PUB_KEY` (непустой), `SERVER_ENDPOINT` (формат host:port) — бот падает с CRITICAL и понятным сообщением
- Redis поддержка: `redis>=5.0.0` добавлен в зависимости; `docker-compose.yml` содержит закомментированный Redis сервис с инструкцией

### Fixed
- `create_profile`: профиль больше не сохраняется в БД если синхронизация с WireGuard провалилась — поднимается `RuntimeError`, транзакция откатывается
- `delete_profile`: профиль больше не удаляется из БД если peer не был удалён с WG-сервера (возвращает `False` вместо `True`)
- `get_profile_config`: расшифровка приватного ключа обёрнута в `try/except` — при повреждённом ключе возвращает `None` и логирует ошибку вместо необработанного исключения
- Хендлеры `.conf` и `QR`: при `get_profile_config == None` теперь показывают пользователю сообщение об ошибке вместо молчаливого возврата
- `Dockerfile`: убрана строка `COPY .env .` — секреты больше не попадают в слои образа; переменные передаются через `environment` в docker-compose
- `main.py`: проверка `.env` при старте теперь пропускается если переменные окружения уже заданы (Docker-сценарий)
- Исправлен AttributeError в `approvals.py`: `_pending_vpn_requests.discard()` заменён на `.pop(user_id, None)` после смены типа с set на dict

### Tests
- `test_create_profile_raises_when_sync_fails` — WG недоступен → профиль не создаётся в БД
- `test_delete_profile_server_removal_fails` — ошибка WG → `False`, `delete_vpn_profile` не вызывается
- `test_get_profile_config_decrypt_failure_returns_none` — повреждённый ключ → `None` без исключения
- `test_vpn_request_blocked_within_ttl` — повторный запрос в течение 24ч заблокирован
- `test_vpn_request_allowed_after_ttl_expired` — после истечения TTL запрос проходит
- `test_vpn_request_blocked_at_profile_limit` — при лимите профилей запрос заблокирован, TTL не устанавливается
- `test_startup_validation_invalid_cidr/too_small_cidr/empty_server_fields` — документируют правила валидации конфигурации
- Итого: **165 тестов** (было 159)

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
