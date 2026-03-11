from aiogram.filters import BaseFilter
from aiogram.types import Message, CallbackQuery
from bot.core.config import settings


class AdminFilter(BaseFilter):
    async def __call__(self, event: Message | CallbackQuery) -> bool:
        if event.from_user is None:
            return False
        return event.from_user.id == settings.admin_id
