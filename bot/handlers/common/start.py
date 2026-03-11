import html
import random

from aiogram import Router, Bot
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message
from loguru import logger
import aiosqlite

from bot.core.config import settings
from bot.core.logging import audit

router = Router()


class CaptchaStates(StatesGroup):
    waiting_for_answer = State()


@router.message(Command("cancel"), StateFilter(CaptchaStates))
async def cmd_cancel(message: Message, state: FSMContext):
    """Отмена процесса регистрации из любого состояния капчи."""
    await state.clear()
    user_id = message.from_user.id
    logger.info("[REGISTRATION] Пользователь отменил капчу | user_id={}", user_id)
    await message.answer(
        "Регистрация отменена.\n\nОтправьте /start чтобы попробовать снова."
    )


@router.message(Command("start"))
async def cmd_start(message: Message, db: aiosqlite.Connection, state: FSMContext):
    from bot.handlers.user.menu import get_user_keyboard
    from bot.handlers.admin.menu import get_admin_keyboard

    user_id = message.from_user.id
    username = f"@{message.from_user.username}" if message.from_user.username else "без username"

    if user_id == settings.admin_id:
        cursor = await db.execute("SELECT telegram_id FROM users WHERE telegram_id = ?", (user_id,))
        if not await cursor.fetchone():
            await db.execute(
                "INSERT OR IGNORE INTO users (telegram_id, username, full_name, is_admin, is_approved) VALUES (?, ?, ?, 1, 1)",
                (user_id, message.from_user.username, message.from_user.full_name),
            )
            await db.commit()
            logger.info("[STARTUP] Администратор добавлен в БД | user_id={} username={}", user_id, username)
        await message.answer(
            "👋 Добро пожаловать!\n\n"
            "Используйте /admin для панели управления или /menu для пользовательского меню.",
            reply_markup=get_admin_keyboard(),
        )
        return

    cursor = await db.execute("SELECT is_approved FROM users WHERE telegram_id = ?", (user_id,))
    row = await cursor.fetchone()

    if row:
        if row["is_approved"]:
            logger.debug("[REGISTRATION] Повторный /start | user_id={} username={}", user_id, username)
            await message.answer("С возвращением! 🚀", reply_markup=get_user_keyboard())
        else:
            logger.debug("[REGISTRATION] Повторный /start, заявка pending | user_id={} username={}", user_id, username)
            await message.answer("⏳ Ваша заявка всё ещё рассматривается. Ожидайте.")
        return

    # Новый пользователь — капча
    a = random.randint(1, 20)
    b = random.randint(1, 20)
    await state.update_data(captcha_answer=a + b)
    await state.set_state(CaptchaStates.waiting_for_answer)
    logger.info("[REGISTRATION] Новый пользователь, капча выдана | user_id={} username={}", user_id, username)
    await message.answer(
        f"👋 Добро пожаловать в VPN-бот!\n\n"
        f"Для защиты от ботов решите пример:\n"
        f"<b>{a} + {b} = ?</b>\n\n"
        f"<i>Для отмены отправьте /cancel</i>"
    )


@router.message(CaptchaStates.waiting_for_answer)
async def process_captcha(message: Message, db: aiosqlite.Connection, state: FSMContext, bot: Bot):
    user_id = message.from_user.id
    username = f"@{message.from_user.username}" if message.from_user.username else "без username"
    data = await state.get_data()
    correct = data.get("captcha_answer")

    text = message.text or ""
    if not text.isdigit() or int(text) != correct:
        a = random.randint(1, 20)
        b = random.randint(1, 20)
        await state.update_data(captcha_answer=a + b)
        logger.debug("[REGISTRATION] Неверный ответ на капчу | user_id={} username={} answer={!r}", user_id, username, text)
        await message.answer(f"❌ Неверно. Попробуйте ещё раз:\n<b>{a} + {b} = ?</b>")
        return

    await state.clear()

    await db.execute(
        "INSERT OR IGNORE INTO users (telegram_id, username, full_name, is_approved) VALUES (?, ?, ?, 0)",
        (user_id, message.from_user.username, message.from_user.full_name),
    )
    await db.execute(
        "INSERT INTO approvals (user_id, status) VALUES (?, 'pending')",
        (user_id,),
    )
    await db.commit()

    logger.info("[REGISTRATION] Капча пройдена, заявка создана | user_id={} username={}", user_id, username)
    audit("REGISTER", user_id=user_id, username=username)

    await message.answer(
        "✅ Верно!\n\n"
        "Ваша заявка отправлена администратору. ⏳\n"
        "Вы получите уведомление после рассмотрения."
    )

    from bot.handlers.admin.approvals import get_approval_keyboard

    try:
        await bot.send_message(
            settings.admin_id,
            f"🔔 <b>Новая заявка на доступ</b>\n\n"
            f"👤 {html.escape(message.from_user.full_name)}\n"
            f"🔗 @{html.escape(message.from_user.username or '—')}\n"
            f"🆔 <code>{user_id}</code>",
            reply_markup=get_approval_keyboard(user_id),
        )
    except Exception as e:
        logger.warning("[REGISTRATION] Не удалось уведомить администратора | admin_id={} error={}", settings.admin_id, e)
