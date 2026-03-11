# Интеграция DNS-proxy с AmneziaWG

## Архитектура

```
VPN-клиент
    │ WireGuard туннель (AllowedIPs = 0.0.0.0/0)
    │ DNS = 10.8.1.254  ← IP WG-интерфейса сервера
    ▼
amnezia-awg2 (сетевое пространство)
    ├── awg0: 10.8.1.254/24    ← WG-интерфейс
    ├── eth0: 172.x.x.x        ← Docker-сеть
    └── adguard-dnsproxy       ← container: network mode
          ├── слушает [::]:53 (все интерфейсы, включая 10.8.1.254)
          └── upstream: DoH → AdGuard DNS Private
                ▼
          94.140.14.14 / AdGuard DNS
```

DNS-proxy работает в `container:` network mode — разделяет сетевое
пространство с AWG-контейнером. Благодаря этому он слушает на `0.0.0.0:53`,
включая WG-интерфейс `10.8.1.254`. Клиентам достаточно указать этот IP как DNS.

## Почему такая архитектура правильная

| Свойство | Значение |
|----------|----------|
| Порт 53 НЕ публикуется на хост | Нет конфликта с systemd-resolved, нет открытого резолвера |
| DNS-proxy недоступен снаружи напрямую | Только через WG-туннель |
| MASQUERADE в PostUp AWG | DNS-ответы доходят обратно до клиентов |
| container: network mode | Нет отдельного IP-адреса, минимальная поверхность атаки |

## Настройка бота

В `.env` укажите IP WG-интерфейса сервера (значение `Address` из `wg0.conf`):

```bash
# Найти IP WG-интерфейса
docker exec amnezia-awg2 cat /opt/amnezia/awg/awg0.conf | grep "^Address"
# Address = 10.8.1.254/24  → DNS_SERVERS=10.8.1.254
```

```env
DNS_SERVERS=10.8.1.254
```

После изменения `.env` — перезапустить бота:

```bash
docker compose up -d bot
```

## Что происходит с уже выданными конфигами

WireGuard не пушит настройки клиенту (в отличие от OpenVPN). Поле `DNS`
прописывается в конфиг при генерации. Существующие клиенты продолжают
использовать старый DNS (`1.1.1.1`) до тех пор, пока не скачают новый конфиг.

**Действие:** попросите пользователей перевыпустить конфиги через бота
(`/profiles` → удалить → создать новый или скачать конфиг заново).

## Проверка

```bash
# 1. DNS-proxy отвечает на WG-интерфейсе сервера
docker exec amnezia-awg2 nslookup google.com 10.8.1.254

# 2. MASQUERADE активен (обязателен для обратной маршрутизации DNS-ответов)
docker exec amnezia-awg2 iptables -t nat -L POSTROUTING -n -v | grep MASQUERADE

# 3. DNS-proxy запущен и слушает
docker logs adguard-dnsproxy --tail 10 | grep "listening to"

# 4. На клиенте после подключения к VPN — DNS leak тест
# https://dnsleaktest.com → должен показать AdGuard DNS IP
```

## Конфигурация adguard-dnsproxy

### Текущие аргументы запуска

```
-l 0.0.0.0          # слушать на всех интерфейсах
-l 127.0.0.1        # и на loopback
-p 53               # порт DNS
-u https://d.adguard-dns.com/dns-query/<profile_id>   # DoH upstream (AdGuard Private DNS)
-b 94.140.14.14:53  # bootstrap для разрешения DoH hostname
```

### Рекомендуемые улучшения

**Включить кэш** (сейчас отключён — каждый запрос уходит в upstream):

```yaml
# В compose-файле adguard-dnsproxy добавить аргументы:
command:
  - "--listen=0.0.0.0"
  - "--port=53"
  - "--upstream=https://d.adguard-dns.com/dns-query/<profile_id>"
  - "--bootstrap=94.140.14.14:53"
  - "--cache"           # включить кэш
  - "--cache-size=4096" # 4096 записей
  - "--refuse-any"      # защита от DNS amplification
```

**Добавить резервный upstream** (на случай недоступности DoH):

```
--fallback=tls://94.140.14.14   # AdGuard DNS over TLS как fallback
```

## Связанные файлы

- `.env` → `DNS_SERVERS` — IP DNS-сервера, прописывается в клиентские конфиги
- `bot/services/vpn_service.py` → `generate_config_content()` — читает `settings.dns_servers`
- `bot/core/config.py` → `dns_servers: str` — настройка
