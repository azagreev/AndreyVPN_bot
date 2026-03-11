# Деплой AndreyVPN_bot в Docker

## Архитектура

```
+-------------------------------------+
|           Docker Host               |
|                                     |
|  +--------------+  +-------------+  |
|  |  amneziawg   |  |     bot     |  |
|  |  (AmneziaWG  |  |  (Python /  |  |
|  |   сервер)    |  |  aiogram)   |  |
|  +--------------+  +------+------+  |
|                           |         |
|              /var/run/docker.sock   |
|         (docker exec для awg CLI)   |
+-------------------------------------+
```

Бот управляет AmneziaWG через `docker exec amneziawg awg ...` — без root-прав внутри бот-контейнера.

## Быстрый старт

### 1. Настройка .env

```bash
cp .env.example .env
```

Заполнить обязательные поля:

```env
BOT_TOKEN=токен_от_BotFather
ADMIN_ID=ваш_telegram_id
SERVER_PUB_KEY=публичный_ключ_сервера_amnezia
SERVER_ENDPOINT=ip_сервера:51820
WG_CONTAINER_NAME=amneziawg   # имя вашего AWG контейнера
```

Сгенерировать ENCRYPTION_KEY:
```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### 2. Сборка и запуск

```bash
# Сборка образа
docker compose build

# Запуск
docker compose up -d

# Логи
docker compose logs -f bot
```

### 3. Интеграция с существующим AWG контейнером

Если AmneziaWG уже запущен отдельно:

```bash
# Узнать имя контейнера
docker ps --format "table {{.Names}}\t{{.Image}}" | grep -i amnezia
```

Указать имя в `.env`:
```env
WG_CONTAINER_NAME=имя_вашего_контейнера
```

Бот автоматически будет вызывать `docker exec {имя} awg ...` вместо прямых вызовов.

Если контейнеры в разных compose-проектах, добавить бот-контейнер в сеть AWG:
```bash
docker network connect <awg_network> andreyvpn_bot
```

### 4. Прямой режим (без docker exec)

Если бот запускается напрямую на хосте с установленным `awg`:
```env
WG_CONTAINER_NAME=   # оставить пустым
```

### 5. Volumes

| Volume | Путь в контейнере | Содержимое |
|--------|-------------------|------------|
| `bot_data` | `/app/data` | SQLite БД (`bot_data.db`) |
| `bot_logs` | `/app/logs` | Логи (`bot.log`, `errors.log`, `audit.log`) |

Резервная копия БД:
```bash
docker cp andreyvpn_bot:/app/data/bot_data.db ./backup_$(date +%Y%m%d).db
```

### 6. Переменные окружения

| Переменная | Обязательная | Описание |
|------------|:---:|---------|
| `BOT_TOKEN` | да | Токен от @BotFather |
| `ADMIN_ID` | да | Telegram ID администратора |
| `ENCRYPTION_KEY` | да | Fernet-ключ для шифрования WG-ключей |
| `SERVER_PUB_KEY` | да | Публичный ключ AmneziaWG сервера |
| `SERVER_ENDPOINT` | да | `IP:PORT` сервера |
| `WG_CONTAINER_NAME` | нет | Имя Docker-контейнера AWG (если пусто — прямые вызовы) |
| `WG_INTERFACE` | нет | Имя интерфейса (по умолч. `awg0`) |
| `DB_PATH` | нет | Путь к БД (по умолч. `/app/data/bot_data.db`) |
| `LOG_PATH` | нет | Директория логов (по умолч. `/app/logs`) |
| `LOG_LEVEL` | нет | `DEBUG`/`INFO`/`WARNING`/`ERROR` |
| `VPN_IP_RANGE` | нет | CIDR пул адресов |
| `MAX_PROFILES_PER_USER` | нет | Лимит профилей на пользователя (по умолч. `3`) |
| `REDIS_URL` | нет | URL Redis для FSM storage (напр. `redis://redis:6379/0`) |

### 7. DNS-proxy (AdGuard DNS фильтрация)

Если рядом с AWG запущен `adguard-dnsproxy` в `container:` network mode
(разделяет сеть с AWG-контейнером), клиенты могут получить фильтрацию через AdGuard DNS.

Укажите IP WG-интерфейса сервера как DNS:
```bash
# Узнать IP WG-интерфейса (поле Address в wg0.conf)
docker exec <awg_container> cat /opt/amnezia/awg/awg0.conf | grep "^Address"
```

```env
# .env
DNS_SERVERS=10.8.1.254   # замените на ваш Address без /24
```

Подробнее: [docs/DNS_PROXY.md](DNS_PROXY.md)

### 8. Обновление бота

```bash
git pull
docker compose build --no-cache
docker compose up -d
```

### 8. Мониторинг

```bash
# Статус контейнера
docker compose ps

# Последние ошибки
docker compose exec bot tail -50 /app/logs/errors.log

# Журнал безопасности
docker compose exec bot tail -100 /app/logs/audit.log
```

### 9. Redis (FSM Storage)

По умолчанию FSM-состояния (капча регистрации) хранятся в памяти и теряются при рестарте бота.

Для production рекомендуется Redis. Раскомментируй в `docker-compose.yml`:

```yaml
  redis:
    image: redis:7-alpine
    container_name: andreyvpn_redis
    restart: unless-stopped
    volumes:
      - redis_data:/data
    networks:
      - vpn_network
```

И добавь в `.env`:
```env
REDIS_URL=redis://redis:6379/0
```
