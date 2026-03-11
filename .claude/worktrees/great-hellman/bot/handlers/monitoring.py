import aiosqlite
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.core.config import settings
from bot.services.vpn_service import VPNService

router = Router()

@router.message(Command("stats"))
async def cmd_stats(message: Message, db: aiosqlite.Connection) -> None:
    """
    Показывает пользователю его статистику потребления трафика за текущий месяц.
    """
    user_id = message.from_user.id
    
    # Получаем расчетные данные за месяц
    usage_data = await VPNService.get_monthly_usage(db, user_id)
    
    if not usage_data:
        await message.answer("У вас еще нет активных VPN-профилей. 🛡️")
        return

    response = "📊 <b>Ваша статистика трафика за текущий месяц</b>\n\n"
    total_month = 0
    
    for profile in usage_data:
        name = profile['name']
        ip = profile['ip']
        month_bytes = profile['monthly_total']
        total_month += month_bytes
        
        response += (
            f"🔹 <b>{name}</b> ({ip})\n"
            f"   🚀 Потреблено в этом месяце: <b>{VPNService.format_bytes(month_bytes)}</b>\n\n"
        )
    
    if len(usage_data) > 1:
        response += f"📈 <b>Итого за месяц:</b> {VPNService.format_bytes(total_month)}"
    
    response += "\n\n<i>Примечание: Статистика обновляется при каждом запросе. Сброс происходит 1-го числа каждого месяца.</i>"
    
    await message.answer(response)

@router.message(Command("server"))
async def cmd_server_status(message: Message) -> None:
    """
    Показывает администратору статус VPN-сервера.
    """
    if message.from_user.id != settings.admin_id:
        return # Игнорируем, если не админ (хотя middleware должен поймать)

    status_data = await VPNService.get_server_status()
    
    if status_data["status"] == "online":
        status_icon = "🟢"
        status_text = "Работает"
    elif status_data["status"] == "offline":
        status_icon = "🔴"
        status_text = "Остановлен"
    else:
        status_icon = "⚠️"
        status_text = f"Ошибка: {status_data.get('message', 'Неизвестно')}"
    
    response = (
        f"🖥️ <b>Статус сервера</b>\n\n"
        f"Состояние: {status_icon} {status_text}\n"
        f"Интерфейс: <code>{status_data.get('interface', 'n/a')}</code>\n"
        f"Активных пиров: {status_data.get('active_peers_count', 0)}"
    )
    
    await message.answer(response)
