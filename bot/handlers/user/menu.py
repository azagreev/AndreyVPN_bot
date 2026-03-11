from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton

router = Router()

BTN_PROFILES = "🔑 Мои профили"
BTN_TRAFFIC = "📈 Трафик"
BTN_STATUS = "ℹ️ Статус"
BTN_HELP = "❓ Помощь"


def get_user_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_PROFILES), KeyboardButton(text=BTN_TRAFFIC)],
            [KeyboardButton(text=BTN_STATUS), KeyboardButton(text=BTN_HELP)],
        ],
        resize_keyboard=True,
    )


@router.message(Command("menu"))
async def cmd_menu(message: Message):
    await message.answer("Главное меню:", reply_markup=get_user_keyboard())


@router.message(F.text == BTN_HELP)
async def handle_help(message: Message):
    await message.answer(
        "❓ <b>Помощь</b>\n\n"
        "Этот бот управляет VPN-профилями на базе AmneziaWG.\n\n"
        "<b>Что можно делать:</b>\n"
        "🔑 <b>Мои профили</b> — просмотр, скачивание, удаление профилей\n"
        "📈 <b>Трафик</b> — статистика потребления за месяц\n"
        "ℹ️ <b>Статус</b> — информация о вашем аккаунте\n\n"
        "<b>Как подключиться:</b>\n"
        "1. Установите приложение <b>AmneziaWG</b>\n"
        "2. Запросите профиль в разделе «Мои профили»\n"
        "3. Отсканируйте QR-код или импортируйте .conf файл\n\n"
        "<b>Команды:</b>\n"
        "/start — главное меню\n"
        "/menu — вернуться в меню"
    )
