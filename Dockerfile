# ── Stage 1: builder ──────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /app

ARG BOT_VERSION=dev

# Системные зависимости для сборки
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Stage 2: runtime ─────────────────────────────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

ARG BOT_VERSION=dev
LABEL org.opencontainers.image.title="AndreyVPN_bot"
LABEL org.opencontainers.image.version=$BOT_VERSION
LABEL org.opencontainers.image.description="Telegram bot for AmneziaWG VPN management"

# Docker CLI для docker exec в AWG контейнер (если используется WG_CONTAINER_NAME)
RUN apt-get update && apt-get install -y --no-install-recommends \
    docker.io \
    && rm -rf /var/lib/apt/lists/*

# Копируем установленные зависимости из builder
COPY --from=builder /install /usr/local

# Копируем исходный код
COPY bot/ bot/
COPY main.py .
COPY .env .

# Данные и логи — volume
VOLUME ["/app/data", "/app/logs"]

# Пользователь без root-прав (кроме docker socket доступа)
RUN groupadd -r botuser && useradd -r -g botuser botuser
RUN chown -R botuser:botuser /app
USER botuser

CMD ["python", "main.py"]
