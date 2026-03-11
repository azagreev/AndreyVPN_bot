import random
from aiogram import Router, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message
import aiosqlite
from bot.core.config import settings

router = Router()

class CaptchaStates(StatesGroup):
    waiting_for_answer = State()

@router.message(Command("start"))
async def cmd_start(message: Message, db: aiosqlite.Connection, state: FSMContext):
    """
    Обработка команды /start. Если пользователь новый — выдает капчу.
    Если уже зарегистрирован — сообщает статус.
    """
    # Проверка, существует ли пользователь и одобрен ли он
    cursor = await db.execute("SELECT is_approved FROM users WHERE telegram_id = ?", (message.from_user.id,))
    row = await cursor.fetchone()
    
    if row:
        if row['is_approved']:
            from bot.handlers.profiles import get_main_keyboard
            await message.answer(
                "С возвращением! Бот активен и готов к работе. 🚀\n\n"
                "Используйте кнопку ниже для перехода в меню:",
                reply_markup=get_main_keyboard()
            )
            return
        else:
            await message.answer("Ваша заявка все еще находится на рассмотрении. Пожалуйста, ожидайте. ⏳")
            return

    # Генерация капчи
    a = random.randint(1, 20)
    b = random.randint(1, 20)
    answer = a + b
    
    await state.update_data(captcha_answer=answer)
    await state.set_state(CaptchaStates.waiting_for_answer)
    
    await message.answer(
        f"Добро пожаловать в VPN-бот! 🛡️\n\n"
        f"Для предотвращения автоматических регистраций, пожалуйста, решите простой пример:\n"
        f"Сколько будет {a} + {b}?"
    )

@router.message(CaptchaStates.waiting_for_answer)
async def process_captcha(message: Message, db: aiosqlite.Connection, state: FSMContext, bot: Bot):
    """
    Проверка ответа на капчу. При успехе регистрирует пользователя и уведомляет админа.
    """
    data = await state.get_data()
    correct_answer = data.get("captcha_answer")
    
    user_answer = message.text
    if not user_answer or not user_answer.isdigit() or int(user_answer) != correct_answer:
        # Генерируем новый пример при ошибке
        a = random.randint(1, 20)
        b = random.randint(1, 20)
        answer = a + b
        await state.update_data(captcha_answer=answer)
        await message.answer(f"❌ Неверно. Попробуйте еще раз:\nСколько будет {a} + {b}?")
        return

    # Капча пройдена
    await state.clear()
    
    # Регистрируем пользователя (по умолчанию не одобрен)
    await db.execute(
        "INSERT OR IGNORE INTO users (telegram_id, username, full_name, is_approved) VALUES (?, ?, ?, 0)",
        (message.from_user.id, message.from_user.username, message.from_user.full_name)
    )
    
    # Создаем запись о запросе одобрения
    await db.execute(
        "INSERT INTO approvals (user_id, status) VALUES (?, 'pending')",
        (message.from_user.id,)
    )
    
    await db.commit()
    
    await message.answer(
        "✅ Верно! Ваша заявка отправлена администратору. ⏳\n"
        "Мы сообщим вам, когда доступ будет одобрен."
    )
    
    # Уведомление администратора
    from bot.handlers.admin import get_admin_keyboard
    try:
        await bot.send_message(
            settings.admin_id,
            f"👤 Новый пользователь ожидает одобрения:\n\n"
            f"ID: {message.from_user.id}\n"
            f"Имя: {message.from_user.full_name}\n"
            f"Username: @{message.from_user.username or 'отсутствует'}",
            reply_markup=get_admin_keyboard(message.from_user.id)
        )
    except Exception as e:
        print(f"Ошибка при уведомлении администратора: {e}")
    
