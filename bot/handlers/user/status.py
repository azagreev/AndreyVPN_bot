import html

from aiogram import Router, F
from aiogram.types import Message
import aiosqlite

from bot.keyboards.user import BTN_STATUS, BTN_TRAFFIC
from bot.services.vpn_service import VPNService

router = Router()


@router.message(F.text == BTN_STATUS)
async def handle_status(message: Message, db: aiosqlite.Connection):
    user_id = message.from_user.id

    cursor = await db.execute(
        "SELECT full_name, username, registered_at FROM users WHERE telegram_id = ?",
        (user_id,),
    )
    user = await cursor.fetchone()

    cursor = await db.execute(
        "SELECT COUNT(*) as cnt FROM vpn_profiles WHERE user_id = ?",
        (user_id,),
    )
    prof_count = (await cursor.fetchone())["cnt"]

    reg_date = user["registered_at"][:10] if user and user["registered_at"] else "—"
    full_name = html.escape(user["full_name"]) if user and user["full_name"] else "—"
    username = html.escape(user["username"]) if user and user["username"] else "—"

    await message.answer(
        f"ℹ️ <b>Ваш статус</b>\n\n"
        f"👤 {full_name}\n"
        f"🔗 @{username}\n"
        f"🆔 <code>{user_id}</code>\n"
        f"📅 Зарегистрирован: {reg_date}\n"
        f"🔑 Профилей: <b>{prof_count}</b>\n"
        f"✅ Статус: Одобрен"
    )


@router.message(F.text == BTN_TRAFFIC)
async def handle_traffic(message: Message, db: aiosqlite.Connection):
    user_id = message.from_user.id
    usage_data = await VPNService.get_monthly_usage(db, user_id)

    if not usage_data:
        await message.answer("📈 У вас нет активных VPN профилей.")
        return

    response = "📈 <b>Трафик за текущий месяц</b>\n\n"
    total = 0
    for p in usage_data:
        month_bytes = p["monthly_total"]
        total += month_bytes
        response += f"🔹 <b>{html.escape(p['name'])}</b> ({p['ip']})\n   {VPNService.format_bytes(month_bytes)}\n\n"

    if len(usage_data) > 1:
        response += f"📊 <b>Итого:</b> {VPNService.format_bytes(total)}\n\n"

    response += "<i>Сброс происходит 1-го числа каждого месяца.</i>"
    await message.answer(response)
