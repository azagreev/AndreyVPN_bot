# Changelog

All notable changes to AndreyVPN_bot are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)
Versioning: [Semantic Versioning](https://semver.org/)

## [Unreleased]

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
