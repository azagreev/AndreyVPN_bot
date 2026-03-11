# Процедура обновления AndreyVPN_bot

## Быстрое обновление

```bash
./scripts/update.sh
```

Скрипт выполняет 7 этапов автоматически. При провале smoke-теста — **автоматический откат**.

## Ручной откат

```bash
# Откат к последнему бэкапу:
./scripts/rollback.sh

# Откат к конкретному бэкапу:
./scripts/rollback.sh backups/bot_data_20260312_143022.db

# Список доступных бэкапов:
ls -lh backups/*.db
```

## Что делает скрипт обновления

| Этап | Действие | При сбое |
|------|----------|----------|
| 1/7 | Проверка свободного места | Выход без изменений |
| 2/7 | Сохранение образа как `:previous` | Предупреждение, продолжение |
| 3/7 | Бэкап БД в `backups/` | Предупреждение, продолжение |
| 4/7 | `git pull` | Выход (set -e) |
| 5/7 | `docker compose build` | Выход (set -e) |
| 6/7 | `docker compose up -d bot` | Выход (set -e) |
| 7/7 | Smoke-тест (15с) | Автоматический откат |

## Smoke-тест

После перезапуска скрипт проверяет:
1. Контейнер в статусе `Up`
2. `RestartCount == 0` (нет crash-loop)
3. Нет строк `CRITICAL` в последних 50 строках лога

При провале любой проверки — откат к `:previous` образу и бэкапу БД.

## Dry run (проверка места без обновления)

```bash
./scripts/update.sh --dry-run
```

Только рассчитывает необходимое место и выходит.

## Миграции базы данных

Миграции запускаются **автоматически** при старте бота. Вручную их запускать не нужно.

Если нужно написать новую миграцию:

```python
# bot/db/migrations/m002_add_column.py
import aiosqlite

MIGRATION_ID = 2
DESCRIPTION = "Краткое описание изменения"

async def up(db: aiosqlite.Connection) -> None:
    await db.execute("ALTER TABLE users ADD COLUMN new_col TEXT")

async def down(db: aiosqlite.Connection) -> None:
    # SQLite не поддерживает DROP COLUMN до версии 3.35
    # Для старых версий — пересоздать таблицу без колонки
    await db.execute("CREATE TABLE users_new AS SELECT id, name FROM users")
    await db.execute("DROP TABLE users")
    await db.execute("ALTER TABLE users_new RENAME TO users")
```

Затем обновить `bot/version.py`:
```python
__schema_version__ = 2   # увеличить на 1
```

## Хранение бэкапов

Бэкапы хранятся в `backups/` и исключены из git.
Рекомендуется хранить последние 5–10 бэкапов и удалять старые:

```bash
# Удалить бэкапы старше 30 дней
find backups/ -name "*.db" -mtime +30 -delete
```

## Если что-то пошло не так

```bash
# Посмотреть логи
docker compose logs bot --tail=100

# Посмотреть только ошибки
docker compose exec bot tail -50 /app/logs/errors.log

# Ручной откат
./scripts/rollback.sh
```
