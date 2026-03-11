from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

BTN_USERS = "👥 Пользователи"
BTN_APPROVALS = "⏳ Заявки"
BTN_STATS = "📊 Статистика"
BTN_SERVER = "🖥️ Сервер"
BTN_VERSION = "🔖 Версия"


def get_admin_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_USERS), KeyboardButton(text=BTN_APPROVALS)],
            [KeyboardButton(text=BTN_STATS), KeyboardButton(text=BTN_SERVER)],
            [KeyboardButton(text=BTN_VERSION)],
        ],
        resize_keyboard=True,
    )
