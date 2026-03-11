from aiogram import Router, F
from aiogram.types import Message
import aiosqlite

from bot.filters.admin import AdminFilter
from bot.keyboards.admin import BTN_STATS, BTN_SERVER
from bot.services.vpn_service import VPNService
from bot.db import repository

router = Router()


@router.message(F.text == BTN_STATS, AdminFilter())
async def handle_stats(message: Message, db: aiosqlite.Connection):
    row = await repository.get_global_stats(db)

    await message.answer(
        f"📊 <b>Статистика</b>\n\n"
        f"👥 Всего пользователей: <b>{row['total_users']}</b>\n"
        f"✅ Одобрено: <b>{row['approved']}</b>\n"
        f"⏳ Ожидает одобрения: <b>{row['pending']}</b>\n\n"
        f"🔑 VPN профилей: <b>{row['total_profiles']}</b>\n\n"
        f"🆕 Новых сегодня: <b>{row['new_today']}</b>\n"
        f"📅 Новых за неделю: <b>{row['new_week']}</b>"
    )


@router.message(F.text == BTN_SERVER, AdminFilter())
async def handle_server(message: Message):
    status_data = await VPNService.get_server_status()

    icons = {"online": "🟢", "offline": "🔴"}
    labels = {"online": "Работает", "offline": "Остановлен"}

    icon = icons.get(status_data["status"], "⚠️")
    label = labels.get(status_data["status"], f"Ошибка: {status_data.get('message', '—')}")

    await message.answer(
        f"🖥️ <b>Статус сервера</b>\n\n"
        f"Состояние: {icon} {label}\n"
        f"Интерфейс: <code>{status_data.get('interface', '—')}</code>\n"
        f"Активных пиров: <b>{status_data.get('active_peers_count', 0)}</b>"
    )
