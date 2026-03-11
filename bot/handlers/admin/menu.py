from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton

from bot.filters.admin import AdminFilter

router = Router()

BTN_USERS = "👥 Пользователи"
BTN_APPROVALS = "⏳ Заявки"
BTN_STATS = "📊 Статистика"
BTN_SERVER = "🖥️ Сервер"


def get_admin_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_USERS), KeyboardButton(text=BTN_APPROVALS)],
            [KeyboardButton(text=BTN_STATS), KeyboardButton(text=BTN_SERVER)],
        ],
        resize_keyboard=True,
    )


@router.message(Command("admin"), AdminFilter())
async def cmd_admin(message: Message):
    await message.answer(
        "🔐 <b>Панель администратора</b>\n\nВыберите раздел:",
        reply_markup=get_admin_keyboard(),
    )
