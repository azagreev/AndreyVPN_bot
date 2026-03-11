"""
Хендлер команды /version — показывает версию бота и схемы БД администратору.
"""
import platform
import sys

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message

from bot.filters.admin import AdminFilter
from bot.keyboards.admin import BTN_VERSION
from bot.version import __version__, __schema_version__

router = Router()


@router.message(Command("version"), AdminFilter())
async def cmd_version(message: Message) -> None:
    await _send_version(message)


@router.message(F.text == BTN_VERSION, AdminFilter())
async def handle_version_button(message: Message) -> None:
    await _send_version(message)


async def _send_version(message: Message) -> None:
    python_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    await message.answer(
        f"🤖 <b>Версия бота:</b> <code>{__version__}</code>\n"
        f"🗃 <b>Версия схемы БД:</b> <code>{__schema_version__}</code>\n"
        f"🐍 <b>Python:</b> <code>{python_ver}</code>\n"
        f"🖥 <b>Платформа:</b> <code>{platform.system()} {platform.release()}</code>"
    )
