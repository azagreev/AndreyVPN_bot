#!/usr/bin/env bash
# =============================================================================
# AndreyVPN_bot — скрипт обновления
# Использование: ./scripts/update.sh [--dry-run]
# =============================================================================
set -euo pipefail

CONTAINER="andreyvpn_bot"
BACKUP_DIR="./backups"
BACKUP_FILE=""
PREV_VERSION="unknown"
DRY_RUN=false

[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=true

# Цвета
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'

info()    { echo -e "${BLUE}  $*${NC}"; }
success() { echo -e "${GREEN}  ✓ $*${NC}"; }
warn()    { echo -e "${YELLOW}  ⚠ $*${NC}"; }
error()   { echo -e "${RED}  ✗ $*${NC}"; }
step()    { echo -e "\n${BOLD}$*${NC}"; }

# -----------------------------------------------------------------------------
# Утилиты
# -----------------------------------------------------------------------------

bytes_human() {
    local bytes=$1
    if   (( bytes >= 1073741824 )); then
        awk "BEGIN {printf \"%.1f GB\", $bytes/1073741824}"
    elif (( bytes >= 1048576 )); then
        awk "BEGIN {printf \"%.1f MB\", $bytes/1048576}"
    elif (( bytes >= 1024 )); then
        awk "BEGIN {printf \"%.1f KB\", $bytes/1024}"
    else
        echo "${bytes} B"
    fi
}

container_running() {
    docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^${CONTAINER}$"
}

# -----------------------------------------------------------------------------
# Этап 1: Проверка свободного места
# -----------------------------------------------------------------------------

check_disk_space() {
    step "[1/7] Проверка свободного места..."

    # Раздел где хранит данные Docker
    local docker_root
    docker_root=$(docker info --format '{{.DockerRootDir}}' 2>/dev/null \
        || echo "/var/lib/docker")

    # Свободно в байтах
    local free_bytes
    free_bytes=$(df --output=avail -B1 "$docker_root" 2>/dev/null | tail -1 \
        || df -k "$docker_root" | awk 'NR==2{print $4*1024}')

    # Размер БД (бэкап будет такого же размера)
    local db_bytes=0
    if container_running; then
        db_bytes=$(docker exec "$CONTAINER" \
            stat -c%s /app/data/bot_data.db 2>/dev/null || echo 0)
    else
        db_bytes=$(docker run --rm \
            -v bot_data:/data alpine:3.19 \
            stat -c%s /data/bot_data.db 2>/dev/null || echo 0)
    fi

    # Размер текущего образа
    local image_bytes=0
    image_bytes=$(docker image inspect "${CONTAINER}:latest" \
        --format='{{.Size}}' 2>/dev/null || echo 0)

    # Overhead сборки: ~50% образа + 100MB для pip/слоёв
    local build_overhead=$(( image_bytes / 2 + 100 * 1024 * 1024 ))

    # Итого с запасом 1.5×
    local required=$(( db_bytes + image_bytes + build_overhead ))
    local required_safe=$(( required * 3 / 2 ))

    echo ""
    info "💾 Свободно на диске Docker:   $(bytes_human $free_bytes)"
    info "📦 Размер бэкапа БД:           $(bytes_human $db_bytes)"
    info "🐳 Текущий Docker-образ:       $(bytes_human $image_bytes)"
    info "🔧 Overhead сборки (оценка):   $(bytes_human $build_overhead)"
    echo "  ──────────────────────────────────────────────"
    info "📊 Необходимо (с запасом 1.5×): $(bytes_human $required_safe)"
    info "✅ Доступно:                    $(bytes_human $free_bytes)"
    echo ""

    if (( free_bytes < required_safe )); then
        local deficit=$(( required_safe - free_bytes ))
        error "НЕДОСТАТОЧНО МЕСТА — не хватает $(bytes_human $deficit)"
        echo ""
        echo "  Советы:"
        echo "    docker image prune -f       # удалить неиспользуемые образы"
        echo "    docker system prune -f      # очистить всё неиспользуемое"
        echo "    du -sh $BACKUP_DIR/*        # проверить старые бэкапы"
        echo ""
        exit 1
    fi

    success "Места достаточно — продолжаем"

    $DRY_RUN && { warn "DRY RUN: дальше не идём"; exit 0; }
}

# -----------------------------------------------------------------------------
# Этап 2: Сохранение предыдущего образа
# -----------------------------------------------------------------------------

save_previous_image() {
    step "[2/7] Сохранение предыдущего образа..."

    if docker image inspect "${CONTAINER}:latest" &>/dev/null; then
        docker tag "${CONTAINER}:latest" "${CONTAINER}:previous"
        PREV_VERSION=$(docker inspect "${CONTAINER}:previous" \
            --format='{{index .Config.Labels "org.opencontainers.image.version"}}' \
            2>/dev/null || echo "unknown")
        success "Образ помечен как :previous (была версия: ${PREV_VERSION})"
    else
        warn "Предыдущий образ не найден — вероятно, первая установка"
        PREV_VERSION="none"
    fi
}

# -----------------------------------------------------------------------------
# Этап 3: Бэкап базы данных
# -----------------------------------------------------------------------------

backup_database() {
    step "[3/7] Бэкап базы данных..."

    mkdir -p "$BACKUP_DIR"
    local timestamp
    timestamp=$(date +%Y%m%d_%H%M%S)
    BACKUP_FILE="${BACKUP_DIR}/bot_data_${timestamp}.db"

    if container_running; then
        docker cp "${CONTAINER}:/app/data/bot_data.db" "$BACKUP_FILE" 2>/dev/null \
            && success "Бэкап сохранён: $BACKUP_FILE" \
            || warn "Не удалось скопировать БД из контейнера — пропускаем"
    else
        # Контейнер не запущен — читаем из volume
        docker run --rm \
            -v bot_data:/data \
            -v "$(pwd)/${BACKUP_DIR}:/backup" \
            alpine:3.19 \
            cp /data/bot_data.db "/backup/$(basename "$BACKUP_FILE")" 2>/dev/null \
            && success "Бэкап из volume: $BACKUP_FILE" \
            || warn "Бэкап не создан (volume пуст или недоступен)"
    fi
}

# -----------------------------------------------------------------------------
# Этап 4: git pull
# -----------------------------------------------------------------------------

pull_code() {
    step "[4/7] Получение нового кода (git pull)..."
    git pull
    success "Код обновлён"
}

# -----------------------------------------------------------------------------
# Этап 5: Сборка нового образа
# -----------------------------------------------------------------------------

build_image() {
    step "[5/7] Сборка нового образа..."

    local new_version
    new_version=$(python3 -c \
        "from bot.version import __version__; print(__version__)" \
        2>/dev/null || echo "dev")

    info "Версия: ${new_version}"
    docker compose build --build-arg BOT_VERSION="$new_version"
    success "Образ собран: ${CONTAINER}:latest (v${new_version})"

    NEW_VERSION="$new_version"
}

# -----------------------------------------------------------------------------
# Этап 6: Перезапуск
# -----------------------------------------------------------------------------

restart_bot() {
    step "[6/7] Перезапуск бота..."
    docker compose up -d bot
    success "Контейнер запущен"
}

# -----------------------------------------------------------------------------
# Этап 7: Smoke-тест
# -----------------------------------------------------------------------------

smoke_test() {
    step "[7/7] Smoke-тест (ждём 15с)..."
    sleep 15

    local failed=false

    # Проверка 1: контейнер запущен
    if docker compose ps bot 2>/dev/null | grep -q "Up"; then
        success "Проверка 1/3: контейнер запущен"
    else
        error "Проверка 1/3: контейнер НЕ запущен"
        failed=true
    fi

    # Проверка 2: нет crash-loop
    local restarts
    restarts=$(docker inspect "$CONTAINER" \
        --format='{{.RestartCount}}' 2>/dev/null || echo 0)
    if (( restarts == 0 )); then
        success "Проверка 2/3: нет перезапусков"
    else
        error "Проверка 2/3: обнаружено перезапусков: ${restarts}"
        failed=true
    fi

    # Проверка 3: нет CRITICAL в логах
    if ! docker compose logs bot --tail=50 2>&1 | grep -q "CRITICAL"; then
        success "Проверка 3/3: нет CRITICAL в логах"
    else
        error "Проверка 3/3: найдены CRITICAL ошибки в логах"
        docker compose logs bot --tail=30
        failed=true
    fi

    $failed && return 1 || return 0
}

# -----------------------------------------------------------------------------
# Откат
# -----------------------------------------------------------------------------

rollback() {
    echo ""
    echo -e "${RED}${BOLD}━━━ АВТОМАТИЧЕСКИЙ ОТКАТ ━━━${NC}"
    warn "Smoke-тест провалился — откатываемся к версии ${PREV_VERSION}"

    # 1. Остановить новый контейнер
    docker compose down bot 2>/dev/null || true

    # 2. Восстановить предыдущий образ
    if docker image inspect "${CONTAINER}:previous" &>/dev/null; then
        docker tag "${CONTAINER}:previous" "${CONTAINER}:latest"
        success "Образ откатан до :previous (v${PREV_VERSION})"
    else
        warn "Образ :previous недоступен — откат образа невозможен"
    fi

    # 3. Восстановить БД из бэкапа
    if [[ -n "$BACKUP_FILE" && -f "$BACKUP_FILE" ]]; then
        local backup_name
        backup_name=$(basename "$BACKUP_FILE")
        docker run --rm \
            -v bot_data:/data \
            -v "$(pwd)/${BACKUP_DIR}:/backup" \
            alpine:3.19 \
            cp "/backup/${backup_name}" /data/bot_data.db \
            && success "БД восстановлена из: $BACKUP_FILE" \
            || error "Не удалось восстановить БД — восстановите вручную из: $BACKUP_FILE"
    else
        warn "Файл бэкапа недоступен: ${BACKUP_FILE:-не задан}"
        warn "Восстановите БД вручную с помощью scripts/rollback.sh"
    fi

    # 4. Запустить предыдущую версию
    docker compose up -d bot 2>/dev/null \
        && success "Предыдущая версия запущена" \
        || error "Не удалось запустить предыдущую версию — проверьте вручную"

    echo ""
    echo -e "${RED}${BOLD}❌ Обновление отменено.${NC}"
    echo -e "   Бот работает на версии: ${PREV_VERSION}"
    echo -e "   Бэкап БД:               ${BACKUP_FILE:-отсутствует}"
    echo -e "   Ручной откат:           ./scripts/rollback.sh"
    exit 1
}

# -----------------------------------------------------------------------------
# main
# -----------------------------------------------------------------------------

echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BOLD}  AndreyVPN_bot — обновление${NC}"
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
$DRY_RUN && warn "Режим DRY RUN: реальных изменений не будет"

check_disk_space
save_previous_image
backup_database
pull_code
build_image
restart_bot

smoke_test || rollback

echo ""
echo -e "${GREEN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}${BOLD}  ✅ Обновление успешно завершено!${NC}"
echo -e "${GREEN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "  ${PREV_VERSION} → ${NEW_VERSION:-dev}"
echo -e "  Бэкап БД: ${BACKUP_FILE:-не создан}"
echo ""
