# DNS-proxy интеграция с AmneziaWG в Docker

**Исследовано:** 2026-03-12
**Домен:** Docker networking, WireGuard DNS routing, Container DNS architecture
**Уверенность:** HIGH (подтверждено официальной документацией Docker, Arch Wiki WireGuard, реальным проектом Wiregate)

---

## Архитектурные варианты интеграции

### Вариант 1: DNS-proxy с фиксированным IP в Docker-сети (РЕКОМЕНДУЕМЫЙ)

**Описание:** DNS-proxy контейнер получает статический IP в `vpn_network`. AWG-контейнер прописывает этот IP как DNS для клиентов через переменную `DNS_SERVERS`. Клиенты получают конфиг с `DNS = 10.88.0.53` (статический IP dns-proxy в Docker-сети).

```
+---------------------------------------------+
|            vpn_network (10.88.0.0/24)        |
|                                              |
|  amneziawg  <---- WG tunnel ----  Client    |
|  10.88.0.2          |               |        |
|     |               |  DNS query    |        |
|     |               v               v        |
|  dns-proxy    <- 10.88.0.53 --------         |
|  10.88.0.53         |                        |
|     |               v                        |
|     +------> AdGuard DNS (94.140.14.14)     |
|              (внешний, DoH/DoT)              |
+---------------------------------------------+
```

**Как работает маршрутизация DNS:**
WireGuard клиент получает конфиг с `DNS = 10.88.0.53` и `AllowedIPs = 0.0.0.0/0`. Когда клиент активирует туннель, wg-quick через resolvconf устанавливает DNS-сервером `10.88.0.53`. Все DNS-запросы уходят через туннель (потому что `AllowedIPs = 0.0.0.0/0` тянет весь трафик, включая UDP/53 к `10.88.0.53` через туннель). AWG-сервер получает DNS-запрос из туннеля, форвардит его в Docker-сеть к `10.88.0.53`, DNS-proxy отвечает.

**Плюсы:**
- Простота: никаких iptables DNAT не нужно
- Прямая маршрутизация через Docker bridge
- Стабильный IP (статический через `ipv4_address`)
- Именно так реализовано в Wiregate (production-проект AmneziaWG + AdGuard)

**Минусы:**
- Нужно задать подсеть для `vpn_network` с явным CIDR (иначе Docker сам выбирает адреса и они меняются)
- AWG-контейнер должен иметь MASQUERADE правило (без него ответный DNS-пакет не вернётся к клиенту)

---

### Вариант 2: DNAT iptables на AWG-сервере (перехват DNS)

**Описание:** AWG-контейнер через PostUp добавляет iptables DNAT правило: весь UDP/TCP трафик от WG-клиентов на порт 53 перенаправляется на DNS-proxy.

```
PostUp = iptables -t nat -I PREROUTING -s 10.8.0.0/24 -p udp --dport 53 -j DNAT --to-destination 10.88.0.53
PostUp = iptables -t nat -I PREROUTING -s 10.8.0.0/24 -p tcp --dport 53 -j DNAT --to-destination 10.88.0.53
PostDown = iptables -t nat -D PREROUTING -s 10.8.0.0/24 -p udp --dport 53 -j DNAT --to-destination 10.88.0.53
PostDown = iptables -t nat -D PREROUTING -s 10.8.0.0/24 -p tcp --dport 53 -j DNAT --to-destination 10.88.0.53
```

При этом клиентам прописывается `DNS = 10.8.0.1` (IP шлюза WG-сети), а DNAT переадресует запросы на реальный DNS-proxy.

**Плюсы:**
- Клиент "видит" DNS как часть VPN-сети (10.8.0.1)
- Позволяет принудительно перехватывать DNS даже если клиент не следует конфигу
- Полная защита от DNS leak на уровне сервера

**Минусы:**
- Сложнее: нужен правильный ip_forward и MASQUERADE уже настроен
- AWG-контейнер нуждается в `NET_ADMIN` и `SYS_MODULE` capabilities (обычно уже есть)
- Не работает для DNS-over-HTTPS (DoH) — порт 443 не перехватывается
- Дополнительная сложность при отладке

---

### Вариант 3: Использование Docker DNS (127.0.0.11) — НЕ РАБОТАЕТ для VPN

**Описание:** AWG-клиентам прописывается `DNS = 127.0.0.11` (Docker embedded DNS).

**Почему не работает:**
- `127.0.0.11` — адрес внутри контейнера (loopback), не маршрутизируется через WG-туннель
- Клиент не может достучаться до loopback AWG-контейнера из внешней сети
- Этот вариант категорически не подходит для VPN-клиентов

---

### Вариант 4: Host network mode — не рекомендуется

**Плюсы:** Нет проблем с Docker-сетями
**Минусы:** Нарушает изоляцию контейнеров, DNS-proxy доступен с хоста (security risk), не вписывается в архитектуру.

---

## Критические проблемы и подводные камни

### Проблема 1: Нестабильный IP DNS-proxy (КРИТИЧЕСКАЯ)

**Корень проблемы:** Если `vpn_network` не имеет явного CIDR в docker-compose, Docker сам назначает подсеть при каждом `docker compose up`. IP контейнеров в такой сети непредсказуемы.

**Симптомы:** После перезапуска `docker compose` DNS-proxy получает другой IP. Клиенты, у которых зашит старый IP в конфиг, теряют DNS-разрешение навсегда (пока не перегенерируют конфиг).

**Решение:** Обязательно задать CIDR для `vpn_network` через `ipam` + `subnet`, и присвоить DNS-proxy статический IP через `ipv4_address`. Без этого вся интеграция нестабильна.

---

### Проблема 2: Отсутствие MASQUERADE — DNS ответы не возвращаются

**Корень проблемы:** Клиент шлёт DNS-запрос (src: `10.8.0.X`), AWG получает его через туннель и форвардит к DNS-proxy (`10.88.0.53`). DNS-proxy видит source `10.8.0.X` — Docker-сеть не знает маршрута обратно в `10.8.0.0/24` (это WG-подсеть, не Docker-подсеть). Пакет теряется.

**Симптомы:** DNS-запросы уходят, ответы не возвращаются. Клиент "завис" при резолвинге доменов.

**Решение:** В `wg0.conf` сервера должно быть:
```
PostUp = iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE
```
MASQUERADE заменяет source IP клиента на IP AWG-контейнера в Docker-сети. DNS-proxy отвечает AWG-контейнеру, AWG возвращает ответ клиенту через туннель.

---

### Проблема 3: Конфликт DNS-proxy с systemd-resolved на хосте

**Корень проблемы:** На Ubuntu/Debian хост слушает `127.0.0.53:53` через `systemd-resolved`. Если DNS-proxy пытается публиковать порт `53:53` на хосте — получит `bind: address already in use`.

**Симптомы:** `docker compose up` падает с ошибкой при попытке запустить DNS-proxy с `ports: "53:53/udp"`.

**Решение:** Если DNS-proxy нужен только внутри Docker-сети, публиковать порт 53 наружу не нужно. DNS-proxy слушает только внутри Docker bridge на своём статическом IP. Секция `ports` в сервисе `dns-proxy` — убрать полностью.

---

### Проблема 4: DNS поле в WG — не серверная настройка

**Корень проблемы:** `DNS` в `[Interface]` клиентского конфига — это не "push" от сервера как в OpenVPN. WireGuard вообще не имеет механизма push options. DNS прописывается в клиентский конфиг при генерации.

**Следствие:** Существующие клиенты с `DNS = 1.1.1.1, 8.8.8.8` продолжат использовать публичные DNS даже после настройки DNS-proxy на сервере. Нужно перегенерировать конфиги.

**Решение:** Изменить `DNS_SERVERS` в `.env`, затем предупредить пользователей о необходимости обновить конфиг (или реализовать команду "переиздать конфиг" в боте).

---

### Проблема 5: DNS leak при split-tunnel конфигурации

**Корень проблемы:** Если клиент использует `AllowedIPs` отличные от `0.0.0.0/0` (split tunnel) и IP DNS-proxy (`10.88.0.53`) не входит в разрешённые диапазоны — DNS запросы пойдут в обход туннеля.

**Текущий статус:** Код `vpn_service.py::generate_config_content()` генерирует `AllowedIPs = 0.0.0.0/0` — это full tunnel, DNS leak невозможен. Изменять не нужно.

---

### Проблема 6: DNS-over-HTTPS клиенты не управляемы через port 53

**Корень проблемы:** Браузеры (Chrome, Firefox) и некоторые приложения используют встроенный DoH (порт 443). Iptables DNAT на порт 53 их не перехватит.

**Следствие:** При Варианте 1 (без DNAT) такие приложения пойдут через туннель к своим DoH серверам напрямую — но это нормально для full-tunnel VPN, трафик всё равно шифруется.

---

## Рекомендуемый подход

**Вариант 1 с фиксированным IP** — минимальные изменения, максимальная надёжность.

### Принцип работы:

1. DNS-proxy получает статический IP `10.88.0.53` в `vpn_network`
2. `DNS_SERVERS=10.88.0.53` в `.env` бота
3. Новые VPN-конфиги генерируются с `DNS = 10.88.0.53`
4. Клиент подключается к AWG, получает DNS в конфиге при первом подключении
5. Все DNS-запросы клиента идут через WG-туннель (AllowedIPs=0/0) к AWG-серверу
6. AWG-сервер получает запрос, MASQUERADE меняет source, форвард через Docker bridge к DNS-proxy
7. DNS-proxy отвечает (upstream: AdGuard DNS `94.140.14.14`)
8. Ответ возвращается через туннель к клиенту

---

## Конкретные конфигурационные изменения

### 1. docker-compose.yml

```yaml
version: "3.9"

services:
  bot:
    build:
      context: .
      dockerfile: Dockerfile
      args:
        BOT_VERSION: ${BOT_VERSION:-dev}
    container_name: andreyvpn_bot
    restart: unless-stopped
    stop_grace_period: 30s
    healthcheck:
      test: ["CMD", "python", "-c", "import sys; open('/app/data/bot_data.db'); sys.exit(0)"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 15s

    environment:
      - BOT_TOKEN=${BOT_TOKEN}
      - ADMIN_ID=${ADMIN_ID}
      - ENCRYPTION_KEY=${ENCRYPTION_KEY}
      - SERVER_PUB_KEY=${SERVER_PUB_KEY}
      - SERVER_ENDPOINT=${SERVER_ENDPOINT}
      - DB_PATH=/app/data/bot_data.db
      - LOG_PATH=/app/logs
      - LOG_LEVEL=${LOG_LEVEL:-INFO}
      - WG_INTERFACE=${WG_INTERFACE:-awg0}
      - WG_CONTAINER_NAME=${WG_CONTAINER_NAME:-amneziawg}
      - VPN_IP_RANGE=${VPN_IP_RANGE:-10.8.0.0/24}
      # ИЗМЕНЕНО: DNS-proxy вместо публичных DNS
      - DNS_SERVERS=${DNS_SERVERS:-10.88.0.53}
      - JC=${JC:-4}
      - JMIN=${JMIN:-40}
      - JMAX=${JMAX:-70}
      - S1=${S1:-44}
      - S2=${S2:-148}
      - H1=${H1:-12345678}
      - H2=${H2:-87654321}
      - H3=${H3:-13572468}
      - H4=${H4:-24681357}

    volumes:
      - bot_data:/app/data
      - bot_logs:/app/logs
      - /var/run/docker.sock:/var/run/docker.sock

    networks:
      - vpn_network

    depends_on:
      - amneziawg
      - dns-proxy  # ДОБАВЛЕНО

  amneziawg:
    # Замени alpine на реальный образ AmneziaWG
    image: alpine:3.19
    container_name: amneziawg
    command: ["sh", "-c", "echo 'AmneziaWG placeholder' && tail -f /dev/null"]
    networks:
      vpn_network:
        ipv4_address: 10.88.0.2  # ДОБАВЛЕНО: статический IP AWG

  # ДОБАВЛЕНО: DNS-proxy контейнер
  dns-proxy:
    image: adguard/dnsproxy:latest
    container_name: dns_proxy
    restart: unless-stopped
    command:
      - "--listen=0.0.0.0"
      - "--port=53"
      - "--upstream=94.140.14.14"   # AdGuard DNS primary
      - "--upstream=94.140.15.15"   # AdGuard DNS fallback
      - "--cache"
      - "--refuse-any"
    # НЕТ секции ports — только внутри Docker-сети, порт 53 не публикуется наружу
    networks:
      vpn_network:
        ipv4_address: 10.88.0.53  # СТАТИЧЕСКИЙ IP — ключевое требование

volumes:
  bot_data:
  bot_logs:

networks:
  vpn_network:
    driver: bridge
    # ДОБАВЛЕНО: явный CIDR для стабильных IP (без этого IP меняются при рестарте)
    ipam:
      config:
        - subnet: 10.88.0.0/24
          gateway: 10.88.0.1
```

### Выбор подсети 10.88.0.0/24

Избегаем конфликтов:
- `10.8.0.0/24` — WireGuard VPN-клиентская подсеть
- `172.17.0.0/16` — дефолтный Docker bridge
- `192.168.x.x` — типичные домашние/серверные сети

Адреса:
- `.1` — шлюз (gateway)
- `.2` — amneziawg контейнер
- `.3` и далее — bot и другие контейнеры (динамически)
- `.53` — dns-proxy (мнемонически совпадает с портом DNS)

---

### 2. .env файл

```bash
# Было:
DNS_SERVERS=1.1.1.1, 8.8.8.8

# Стало:
DNS_SERVERS=10.88.0.53
```

---

### 3. AWG server wg0.conf — PostUp правила

Нужно убедиться что в конфиге AWG-сервера (внутри AWG-контейнера) есть:

```ini
[Interface]
PrivateKey = <SERVER_PRIVATE_KEY>
Address = 10.8.0.1/24
ListenPort = 51820
Jc = 4
Jmin = 40
Jmax = 70
S1 = 44
S2 = 148
H1 = 12345678
H2 = 87654321
H3 = 13572468
H4 = 24681357

# Форвардинг и NAT (eth0 — интерфейс AWG-контейнера в vpn_network)
PostUp = iptables -A FORWARD -i %i -j ACCEPT
PostUp = iptables -A FORWARD -o %i -j ACCEPT
PostUp = iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE
PostDown = iptables -D FORWARD -i %i -j ACCEPT
PostDown = iptables -D FORWARD -o %i -j ACCEPT
PostDown = iptables -t nat -D POSTROUTING -o eth0 -j MASQUERADE
```

MASQUERADE критичен: без него DNS ответы от dns-proxy не вернутся к WG-клиентам (Docker-сеть не знает маршрут в `10.8.0.0/24`).

---

### 4. Клиентский конфиг — результат после изменений

Метод `vpn_service.py::generate_config_content()` не требует изменений. После обновления `.env` генерирует:

```ini
[Interface]
PrivateKey = <CLIENT_PRIVATE_KEY>
Address = 10.8.0.2/32
DNS = 10.88.0.53
Jc = 4
...

[Peer]
PublicKey = <SERVER_PUB_KEY>
Endpoint = <SERVER_ENDPOINT>
AllowedIPs = 0.0.0.0/0
```

Изменений в коде не требуется. Нужно только:
1. Обновить `.env` (`DNS_SERVERS=10.88.0.53`)
2. Обновить `docker-compose.yml` (добавить dns-proxy, ipam, статические IP)
3. Убедиться что AWG-сервер имеет PostUp MASQUERADE правило
4. Предупредить существующих пользователей о необходимости перегенерировать конфиги

---

## Дополнительные замечания

### Docker embedded DNS (127.0.0.11) не мешает

Docker embedded DNS работает только для разрешения имён контейнеров внутри Docker-сети. Он не конфликтует с DNS-proxy на `10.88.0.53:53`. Когда dns-proxy хочет разрешить имя контейнера (если нужно) — он может использовать `127.0.0.11` как форвард. В нашем случае dns-proxy форвардит только к AdGuard upstream, Docker DNS не задействован.

### Проверка корректности после деплоя

```bash
# Из AWG-контейнера — проверить достижимость DNS-proxy
docker exec amneziawg nslookup google.com 10.88.0.53

# Проверить что DNS-proxy отвечает
docker exec amneziawg nc -u 10.88.0.53 53

# Проверить статический IP dns-proxy
docker inspect dns_proxy | grep IPAddress
```

### DNS leak тест для клиентов

После подключения клиента к VPN с новым конфигом:
- Зайти на `dnsleaktest.com` — должен показать AdGuard DNS (94.140.14.14/94.140.15.15)
- Зайти на `ipleak.net` — DNS серверы должны совпадать с VPN-сервером

---

## Источники

### HIGH confidence
- [WireGuard DNS Configuration — Arch Wiki](https://wiki.archlinux.org/title/WireGuard)
- [Wiregate — AmneziaWG + AdGuard production setup](https://github.com/NOXCIS/Wiregate)
- [AdGuard dnsproxy — Official GitHub](https://github.com/AdguardTeam/dnsproxy)
- [AdGuard dnsproxy — Docker Hub](https://hub.docker.com/r/adguard/dnsproxy)
- [Docker Compose Networks — Official Docs](https://docs.docker.com/reference/compose-file/networks/)

### MEDIUM confidence
- [WireGuard Remote Access to Docker Containers — Pro Custodibus](https://www.procustodibus.com/blog/2022/02/wireguard-remote-access-to-docker-containers/)
- [Assign Static IP to Docker Container — Baeldung](https://www.baeldung.com/ops/docker-assign-static-ip-container)
- [DNS leak prevention in WireGuard — EngineerWorkshop](https://engineerworkshop.com/blog/dont-let-wireguard-dns-leaks-on-windows-compromise-your-security-learn-how-to-fix-it/)
- [iptables DNAT for DNS — nixCraft WireGuard Firewall Rules](https://www.cyberciti.biz/faq/how-to-set-up-wireguard-firewall-rules-in-linux/)
