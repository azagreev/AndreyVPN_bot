from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware, types
from aiogram.types import Message, CallbackQuery
from bot.core.config import settings
import aiosqlite

class AccessControlMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[types.TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: types.TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        # Пропускаем только сообщения и коллбэки
        if not isinstance(event, (Message, CallbackQuery)):
            return await handler(event, data)

        user_id = event.from_user.id

        # Администратор всегда имеет доступ
        if user_id == settings.admin_id:
            return await handler(event, data)

        # Пропускаем команду /start
        if isinstance(event, Message) and event.text and event.text.startswith("/start"):
            return await handler(event, data)

        # Пропускаем, если пользователь находится в процессе прохождения капчи
        state = data.get("state")
        if state:
            current_state = await state.get_state()
            if current_state == "CaptchaStates:waiting_for_answer":
                return await handler(event, data)

        # Проверяем одобрение в базе данных
        db: aiosqlite.Connection = data.get("db")
        if not db:
             # На случай, если DbMiddleware еще не отработал
             return await handler(event, data)

        cursor = await db.execute("SELECT is_approved FROM users WHERE telegram_id = ?", (user_id,))
        row = await cursor.fetchone()
        
        if row and row['is_approved']:
            return await handler(event, data)

        # Если не одобрен или не найден в базе
        if isinstance(event, Message):
            await event.answer("🚫 Доступ ограничен. Ожидайте одобрения администратором.")
        elif isinstance(event, CallbackQuery):
            await event.answer("🚫 Доступ ограничен.", show_alert=True)
        
        return
