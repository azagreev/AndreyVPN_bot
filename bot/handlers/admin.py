from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters.callback_data import CallbackData
import aiosqlite
from bot.core.config import settings

router = Router()

class ApproveCallback(CallbackData, prefix="approve"):
    user_id: int
    action: str  # "accept" or "reject"

def get_admin_keyboard(user_id: int) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text="✅ Одобрить", callback_data=ApproveCallback(user_id=user_id, action="accept").pack()),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=ApproveCallback(user_id=user_id, action="reject").pack())
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

@router.callback_query(ApproveCallback.filter(F.action == "accept"))
async def handle_approve(callback_query: CallbackQuery, callback_data: ApproveCallback, db: aiosqlite.Connection, bot: Bot):
    user_id = callback_data.user_id
    
    # Обновляем статус пользователя
    await db.execute("UPDATE users SET is_approved = 1 WHERE telegram_id = ?", (user_id,))
    await db.execute(
        "UPDATE approvals SET status = 'approved', admin_id = ? WHERE user_id = ? AND status = 'pending'",
        (callback_query.from_user.id, user_id)
    )
    await db.commit()
    
    await callback_query.answer("Пользователь одобрен!")
    await callback_query.message.edit_text(
        callback_query.message.text + "

✅ Одобрено."
    )
    
    # Уведомляем пользователя
    try:
        await bot.send_message(user_id, "✅ Ваш доступ был одобрен администратором! Теперь вы можете пользоваться всеми функциями бота.")
    except Exception as e:
        print(f"Не удалось уведомить пользователя {user_id}: {e}")

@router.callback_query(ApproveCallback.filter(F.action == "reject"))
async def handle_reject(callback_query: CallbackQuery, callback_data: ApproveCallback, db: aiosqlite.Connection, bot: Bot):
    user_id = callback_data.user_id
    
    # Обновляем статус в таблице заявок
    await db.execute(
        "UPDATE approvals SET status = 'rejected', admin_id = ? WHERE user_id = ? AND status = 'pending'",
        (callback_query.from_user.id, user_id)
    )
    await db.commit()
    
    await callback_query.answer("Пользователь отклонен.")
    await callback_query.message.edit_text(
        callback_query.message.text + "

❌ Отклонено."
    )
    
    # Уведомляем пользователя
    try:
        await bot.send_message(user_id, "❌ Ваша заявка на доступ была отклонена администратором.")
    except Exception as e:
        print(f"Не удалось уведомить пользователя {user_id}: {e}")
