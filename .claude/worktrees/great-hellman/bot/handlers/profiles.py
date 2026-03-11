from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.filters.callback_data import CallbackData
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from loguru import logger

from bot.core.config import settings
from bot.services.vpn_service import VPNService

router = Router()

class ProfileRequestCallback(CallbackData, prefix="vpn_req"):
    user_id: int
    action: str  # "request", "approve", "reject"

def get_main_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="➕ Запросить VPN", callback_data=ProfileRequestCallback(user_id=0, action="request").pack())]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_admin_vpn_keyboard(user_id: int) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text="✅ Выдать конфиг", callback_data=ProfileRequestCallback(user_id=user_id, action="approve").pack()),
            InlineKeyboardButton(text="❌ Отказать", callback_data=ProfileRequestCallback(user_id=user_id, action="reject").pack())
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

@router.message(Command("menu"))
async def cmd_menu(message: Message) -> None:
    """
    Главное меню для одобренных пользователей.
    """
    await message.answer(
        "Главное меню управления VPN 🛡️\n\n"
        "Вы можете запросить новый конфигурационный файл для подключения.",
        reply_markup=get_main_keyboard()
    )

@router.callback_query(ProfileRequestCallback.filter(F.action == "request"))
async def handle_vpn_request(callback_query: CallbackQuery, bot: Bot) -> None:
    """
    Пользователь нажимает кнопку "Запросить VPN".
    """
    user = callback_query.from_user
    
    await callback_query.answer("Запрос отправлен администратору.")
    await callback_query.message.edit_text(
        "⏳ Ваш запрос на получение VPN-профиля отправлен администратору. \n"
        "Ожидайте уведомления о готовности."
    )
    
    # Уведомление админа
    try:
        await bot.send_message(
            settings.admin_id,
            f"🔑 <b>Запрос на VPN-конфиг</b>\n\n"
            f"От: {user.full_name} (@{user.username or 'id' + str(user.id)})\n"
            f"ID: {user.id}",
            reply_markup=get_admin_vpn_keyboard(user.id)
        )
    except Exception as e:
        logger.error(f"Не удалось уведомить админа о запросе VPN: {e}")

@router.callback_query(ProfileRequestCallback.filter(F.action == "approve"))
async def handle_vpn_approve(callback_query: CallbackQuery, callback_data: ProfileRequestCallback, bot: Bot) -> None:
    """
    Админ одобряет выдачу конфига.
    """
    user_id = callback_data.user_id
    
    await callback_query.answer("Генерирую конфиг...")
    await callback_query.message.edit_text(
        f"{callback_query.message.text}\n\n⏳ <b>Генерация профиля...</b>"
    )
    
    try:
        # Создаем профиль
        profile_name = f"VPN_{user_id}"
        result = await VPNService.create_profile(user_id, profile_name)
        
        # Генерируем QR-код
        qr_bytes = VPNService.generate_qr_code(result['config'])
        
        # Подготовка файлов
        qr_file = BufferedInputFile(qr_bytes, filename=f"{profile_name}.png")
        conf_file = BufferedInputFile(result['config'].encode(), filename=f"{profile_name}.conf")
        
        # Отправляем пользователю
        await bot.send_photo(
            user_id,
            photo=qr_file,
            caption=(
                "✅ <b>Ваш VPN-профиль готов!</b>\n\n"
                "1. Установите приложение <b>AmneziaWG</b>\n"
                "2. Отсканируйте этот QR-код или импортируйте .conf файл\n"
                "3. Подключитесь и пользуйтесь! 🚀"
            )
        )
        await bot.send_document(user_id, document=conf_file)
        
        # Обновляем сообщение у админа
        await callback_query.message.edit_text(
            f"{callback_query.message.text.replace('⏳ <b>Генерация профиля...</b>', '')}\n\n✅ <b>Конфиг выдан и отправлен пользователю.</b>"
        )
        
    except Exception as e:
        logger.exception(f"Ошибка при выдаче конфига: {e}")
        await callback_query.message.answer("❌ Произошла ошибка при создании профиля. Обратитесь к администратору.")

@router.callback_query(ProfileRequestCallback.filter(F.action == "reject"))
async def handle_vpn_reject(callback_query: CallbackQuery, callback_data: ProfileRequestCallback, bot: Bot) -> None:
    """
    Админ отклоняет выдачу конфига.
    """
    user_id = callback_data.user_id
    
    await callback_query.message.edit_text(
        f"{callback_query.message.text}\n\n❌ <b>Запрос отклонен.</b>"
    )
    
    try:
        await bot.send_message(user_id, "❌ Ваш запрос на получение VPN-профиля был отклонен администратором.")
    except Exception as e:
        logger.error(f"Не удалось уведомить пользователя {user_id} об отказе: {e}")
