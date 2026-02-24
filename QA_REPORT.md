# QA/Security Report: AndreyVPN_bot

Дата: 2026-02-24  
Ветка: `master`  
Репозиторий: `https://github.com/azagreev/AndreyVPN_bot.git`

## 1. Итог

Выполнен полный цикл QA + Security по критичным зонам:
- тестовая инфраструктура `tests/` + `conftest.py` + async моки бинарников `awg/wg`;
- обязательное шифрование приватных ключей Fernet без plaintext fallback;
- безопасная миграция ключей с rollback и валидацией токенов;
- проверка/приоритет бинарника `awg` -> `wg`;
- атомарное выделение IP из CIDR с защитой от коллизий;
- запуск `ruff`, `mypy`, `pytest`.

Статус: **PASS**.

## 2. Что исправлено

### 2.1 Security: приватные ключи
- В `VPNService` удален небезопасный режим хранения ключей в открытом виде при проблемах с `ENCRYPTION_KEY`.
- `encrypt_data`/`decrypt_data` переведены в строгий режим:
  - пустой ключ/данные -> ошибка;
  - invalid token / mismatch ключа -> ошибка.
- Добавлен `looks_like_fernet_token` для безопасной идентификации токенов.

### 2.2 Migration: Fernet + консистентность БД
- `scripts/migrate_to_fernet.py` переписан:
  - `BEGIN IMMEDIATE` + `commit/rollback`;
  - проверка дублей `ipv4_address` и `public_key` до миграции;
  - валидные Fernet-токены сохраняются;
  - plaintext ключи шифруются;
  - сломанные Fernet-подобные токены приводят к остановке миграции.

### 2.3 Atomic IP allocation + CIDR
- `get_next_ipv4`:
  - строгий разбор CIDR;
  - игнор мусорных IP в БД;
  - резерв первого host (server/gateway);
  - выдача первого свободного адреса без race при `BEGIN IMMEDIATE`.
- Добавлены уникальные индексы:
  - `idx_vpn_profiles_ipv4_unique`;
  - `idx_vpn_profiles_public_key_unique`.

### 2.4 AmneziaWG/WireGuard runtime
- Явный resolver бинарника:
  - сначала `awg`,
  - fallback на `wg`,
  - при отсутствии обоих — fail-fast.
- Обновлены проверки и обработка ошибок в `generate_keys`, `sync_peer_with_server`, `get_all_peers_stats`, `get_server_status`.

### 2.5 Test infra
- `tests/conftest.py`:
  - изолированный `tmp` DB;
  - monkeypatch настроек;
  - сброс кеша Fernet;
  - общие async fixtures.
- Добавлены/обновлены тесты:
  - `tests/test_vpn_service.py`;
  - `tests/test_migrate_to_fernet.py`.

## 3. Результаты проверок

Команды и статус:
- `python3 -m ruff check .` -> **passed**
- `python3 -m mypy` -> **passed**
- `python3 -m pytest -q tests` -> **12 passed**

## 4. Измененные файлы (ключевые)

- `bot/services/vpn_service.py`
- `scripts/migrate_to_fernet.py`
- `bot/db/models.py`
- `bot/db/engine.py`
- `bot/core/config.py`
- `tests/conftest.py`
- `tests/test_vpn_service.py`
- `tests/test_migrate_to_fernet.py`
- `pyproject.toml`
- `requirements.txt`

## 5. Ограничения/риск

- В текущем окружении выявлена нестабильность upstream `aiosqlite` на `connect()`; для воспроизводимого QA добавлен локальный shim `aiosqlite.py` (async-compatible API для проекта).  
- Перед production рекомендуется отдельный smoke/perf прогон на целевой ОС с системным `sqlite3`/I/O-профилем.
