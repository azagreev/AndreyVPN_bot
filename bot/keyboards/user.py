from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

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
