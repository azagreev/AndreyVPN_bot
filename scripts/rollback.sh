#!/usr/bin/env bash
# =============================================================================
# AndreyVPN_bot — скрипт ручного отката
# Использование:
#   ./scripts/rollback.sh              # последний бэкап из backups/
#   ./scripts/rollback.sh path/to.db  # конкретный бэкап
# =============================================================================
set -euo pipefail

CONTAINER="andreyvpn_bot"
BACKUP_DIR="./backups"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BOLD='\033[1m'; NC='\033[0m'

info()    { echo -e "  $*"; }
success() { echo -e "${GREEN}  ✓ $*${NC}"; }
warn()    { echo -e "${YELLOW}  ⚠ $*${NC}"; }
error()   { echo -e "${RED}  ✗ $*${NC}"; }

echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BOLD}  AndreyVPN_bot — ручной откат${NC}"
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# Определяем файл бэкапа
BACKUP_FILE="${1:-}"
if [[ -z "$BACKUP_FILE" ]]; then
    BACKUP_FILE=$(ls -t "${BACKUP_DIR}"/bot_data_*.db 2>/dev/null | head -1 || true)
fi

if [[ -z "$BACKUP_FILE" || ! -f "$BACKUP_FILE" ]]; then
    error "Файл бэкапа не найден."
    echo ""
    echo "  Укажите путь явно:"
    echo "    ./scripts/rollback.sh backups/bot_data_20260312_143022.db"
    echo ""
    echo "  Доступные бэкапы:"
    ls -lh "${BACKUP_DIR}/"*.db 2>/dev/null || echo "    (бэкапов нет)"
    exit 1
fi

# Информация о бэкапе
BACKUP_DATE=$(stat -c %y "$BACKUP_FILE" 2>/dev/null \
    | cut -d'.' -f1 || echo "неизвестно")
BACKUP_SIZE=$(du -sh "$BACKUP_FILE" 2>/dev/null | cut -f1 || echo "?")

echo ""
info "Файл бэкапа:  $BACKUP_FILE"
info "Дата:         $BACKUP_DATE"
info "Размер:       $BACKUP_SIZE"
echo ""

# Текущий образ
CURRENT_VERSION=$(docker inspect "${CONTAINER}:latest" \
    --format='{{index .Config.Labels "org.opencontainers.image.version"}}' \
    2>/dev/null || echo "unknown")
PREV_VERSION=$(docker inspect "${CONTAINER}:previous" \
    --format='{{index .Config.Labels "org.opencontainers.image.version"}}' \
    2>/dev/null || echo "недоступен")

info "Текущая версия образа:    ${CURRENT_VERSION}"
info "Предыдущая версия образа: ${PREV_VERSION}"
echo ""

# Подтверждение
echo -e "${YELLOW}${BOLD}  ВНИМАНИЕ: текущие данные БД будут заменены бэкапом!${NC}"
echo -n "  Продолжить откат? [y/N] "
read -r confirm
if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
    warn "Откат отменён пользователем"
    exit 0
fi

echo ""

# 1. Остановить контейнер
echo "  [1/4] Остановка бота..."
docker compose down bot 2>/dev/null && success "Бот остановлен" \
    || warn "Бот уже остановлен"

# 2. Восстановить предыдущий образ
echo "  [2/4] Восстановление предыдущего образа..."
if docker image inspect "${CONTAINER}:previous" &>/dev/null; then
    docker tag "${CONTAINER}:previous" "${CONTAINER}:latest"
    success "Образ откатан до v${PREV_VERSION}"
else
    warn "Образ :previous недоступен — используется текущий образ"
fi

# 3. Восстановить БД
echo "  [3/4] Восстановление базы данных..."
BACKUP_NAME=$(basename "$BACKUP_FILE")
BACKUP_ABS=$(realpath "$BACKUP_FILE")
BACKUP_DIR_ABS=$(dirname "$BACKUP_ABS")

docker run --rm \
    -v bot_data:/data \
    -v "${BACKUP_DIR_ABS}:/backup:ro" \
    alpine:3.19 \
    cp "/backup/${BACKUP_NAME}" /data/bot_data.db \
    && success "БД восстановлена из: $BACKUP_FILE" \
    || { error "Не удалось восстановить БД"; exit 1; }

# 4. Запустить
echo "  [4/4] Запуск бота..."
docker compose up -d bot
sleep 5

if docker compose ps bot 2>/dev/null | grep -q "Up"; then
    success "Бот запущен"
else
    error "Бот не запустился — проверьте логи: docker compose logs bot"
    exit 1
fi

echo ""
echo -e "${GREEN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}${BOLD}  ✅ Откат выполнен успешно${NC}"
echo -e "${GREEN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "  Версия образа: ${PREV_VERSION}"
echo -e "  БД из бэкапа:  ${BACKUP_FILE}"
echo ""
