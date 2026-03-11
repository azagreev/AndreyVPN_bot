from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.filters.admin import AdminFilter
from bot.keyboards.admin import BTN_USERS, BTN_APPROVALS, BTN_STATS, BTN_SERVER, get_admin_keyboard

router = Router()


@router.message(Command("admin"), AdminFilter())
async def cmd_admin(message: Message):
    await message.answer(
        "🔐 <b>Панель администратора</b>\n\nВыберите раздел:",
        reply_markup=get_admin_keyboard(),
    )
