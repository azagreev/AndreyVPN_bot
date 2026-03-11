import html

from aiogram import Router, F, Bot
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    BufferedInputFile,
)
from aiogram.filters.callback_data import CallbackData
from loguru import logger
import aiosqlite

from bot.handlers.user.menu import BTN_PROFILES
from bot.services.vpn_service import VPNService
from bot.core.config import settings
from bot.core.logging import audit

router = Router()


class ProfileAction(CallbackData, prefix="prof"):
    action: str  # conf, qr, delete, confirm_delete, cancel_delete, request
    profile_id: int


def profiles_keyboard(profiles: list) -> InlineKeyboardMarkup:
    buttons = []
    for p in profiles:
        pid = p["id"]
        buttons.append(
            [InlineKeyboardButton(text=f"🔐 {p['name']}  ({p['ipv4_address']})", callback_data="noop")]
        )
        buttons.append([
            InlineKeyboardButton(text="📥 .conf", callback_data=ProfileAction(action="conf", profile_id=pid).pack()),
            InlineKeyboardButton(text="📱 QR", callback_data=ProfileAction(action="qr", profile_id=pid).pack()),
            InlineKeyboardButton(text="🗑️ Удалить", callback_data=ProfileAction(action="delete", profile_id=pid).pack()),
        ])
    buttons.append([
        InlineKeyboardButton(
            text="➕ Запросить новый профиль",
            callback_data=ProfileAction(action="request", profile_id=0).pack(),
        )
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def confirm_delete_keyboard(profile_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="✅ Да, удалить",
            callback_data=ProfileAction(action="confirm_delete", profile_id=profile_id).pack(),
        ),
        InlineKeyboardButton(
            text="❌ Отмена",
            callback_data=ProfileAction(action="cancel_delete", profile_id=profile_id).pack(),
        ),
    ]])


async def _fetch_profiles(db: aiosqlite.Connection, user_id: int) -> list:
    cursor = await db.execute(
        "SELECT id, name, ipv4_address FROM vpn_profiles WHERE user_id = ? ORDER BY created_at",
        (user_id,),
    )
    return [dict(r) for r in await cursor.fetchall()]


@router.message(F.text == BTN_PROFILES)
async def handle_profiles(message: Message, db: aiosqlite.Connection):
    profiles = await _fetch_profiles(db, message.from_user.id)

    if not profiles:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text="➕ Запросить VPN профиль",
                callback_data=ProfileAction(action="request", profile_id=0).pack(),
            )
        ]])
        await message.answer("У вас пока нет VPN профилей.", reply_markup=keyboard)
        return

    await message.answer(
        f"🔑 <b>Ваши VPN профили</b> ({len(profiles)} шт.):",
        reply_markup=profiles_keyboard(profiles),
    )


@router.callback_query(ProfileAction.filter(F.action == "conf"))
async def handle_download_conf(callback: CallbackQuery, callback_data: ProfileAction, bot: Bot, db: aiosqlite.Connection):
    profile_id = callback_data.profile_id
    user_id = callback.from_user.id

    # Проверяем владельца — предотвращаем скачивание чужого конфига
    cursor = await db.execute(
        "SELECT user_id FROM vpn_profiles WHERE id = ?", (profile_id,)
    )
    row = await cursor.fetchone()
    if not row or row["user_id"] != user_id:
        await callback.answer("Профиль не найден.", show_alert=True)
        return

    await callback.answer("Генерирую конфиг...")
    result = await VPNService.get_profile_config(profile_id)
    if not result:
        return

    conf_file = BufferedInputFile(result["config"].encode(), filename=f"{result['name']}.conf")
    await bot.send_document(
        user_id,
        document=conf_file,
        caption=f"📄 <b>{html.escape(result['name'])}</b>\nIP: <code>{result['ipv4']}</code>",
    )


@router.callback_query(ProfileAction.filter(F.action == "qr"))
async def handle_show_qr(callback: CallbackQuery, callback_data: ProfileAction, bot: Bot, db: aiosqlite.Connection):
    profile_id = callback_data.profile_id
    user_id = callback.from_user.id

    # Проверяем владельца — предотвращаем просмотр чужого QR
    cursor = await db.execute(
        "SELECT user_id FROM vpn_profiles WHERE id = ?", (profile_id,)
    )
    row = await cursor.fetchone()
    if not row or row["user_id"] != user_id:
        await callback.answer("Профиль не найден.", show_alert=True)
        return

    await callback.answer("Генерирую QR-код...")
    result = await VPNService.get_profile_config(profile_id)
    if not result:
        return

    qr_bytes = VPNService.generate_qr_code(result["config"])
    qr_file = BufferedInputFile(qr_bytes, filename=f"{result['name']}.png")
    await bot.send_photo(
        user_id,
        photo=qr_file,
        caption=f"📱 <b>{html.escape(result['name'])}</b>\nIP: <code>{result['ipv4']}</code>",
    )


@router.callback_query(ProfileAction.filter(F.action == "delete"))
async def handle_delete_prompt(callback: CallbackQuery, callback_data: ProfileAction):
    await callback.message.edit_reply_markup(
        reply_markup=confirm_delete_keyboard(callback_data.profile_id)
    )
    await callback.answer("Подтвердите удаление")


@router.callback_query(ProfileAction.filter(F.action == "confirm_delete"))
async def handle_delete_confirm(callback: CallbackQuery, callback_data: ProfileAction, db: aiosqlite.Connection):
    profile_id = callback_data.profile_id
    user_id = callback.from_user.id

    cursor = await db.execute("SELECT user_id FROM vpn_profiles WHERE id = ?", (profile_id,))
    row = await cursor.fetchone()
    if not row or row["user_id"] != user_id:
        await callback.answer("Профиль не найден.", show_alert=True)
        return

    # Сохраняем имя профиля для лога до удаления
    cursor = await db.execute("SELECT name FROM vpn_profiles WHERE id = ?", (profile_id,))
    profile_row = await cursor.fetchone()
    profile_name = profile_row["name"] if profile_row else str(profile_id)

    success = await VPNService.delete_profile(profile_id)
    if not success:
        logger.error("[VPN] Ошибка удаления профиля | user_id={} profile_id={}", user_id, profile_id)
        await callback.answer("❌ Ошибка при удалении профиля.", show_alert=True)
        return

    logger.info("[VPN] Профиль удалён пользователем | user_id={} profile={}", user_id, profile_name)
    audit("VPN_DELETED", user_id=user_id, profile=profile_name)
    await callback.answer("✅ Профиль удалён.")
    profiles = await _fetch_profiles(db, user_id)

    if not profiles:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text="➕ Запросить VPN профиль",
                callback_data=ProfileAction(action="request", profile_id=0).pack(),
            )
        ]])
        await callback.message.edit_text("У вас пока нет VPN профилей.", reply_markup=keyboard)
    else:
        await callback.message.edit_text(
            f"🔑 <b>Ваши VPN профили</b> ({len(profiles)} шт.):",
            reply_markup=profiles_keyboard(profiles),
        )


@router.callback_query(ProfileAction.filter(F.action == "cancel_delete"))
async def handle_delete_cancel(callback: CallbackQuery, callback_data: ProfileAction, db: aiosqlite.Connection):
    profiles = await _fetch_profiles(db, callback.from_user.id)
    await callback.message.edit_reply_markup(reply_markup=profiles_keyboard(profiles))
    await callback.answer()


@router.callback_query(ProfileAction.filter(F.action == "request"))
async def handle_vpn_request(callback: CallbackQuery, bot: Bot):
    user = callback.from_user

    username = f"@{user.username}" if user.username else "без username"
    logger.info("[VPN] Пользователь запросил профиль | user_id={} username={}", user.id, username)

    await callback.answer("Запрос отправлен!")
    await callback.message.edit_text(
        "⏳ Запрос на новый VPN профиль отправлен администратору.\n"
        "Вы получите уведомление, когда профиль будет готов."
    )

    from bot.handlers.admin.users import get_issue_vpn_keyboard

    try:
        await bot.send_message(
            settings.admin_id,
            f"🔑 <b>Запрос на VPN профиль</b>\n\n"
            f"👤 {html.escape(user.full_name)}\n"
            f"🔗 @{html.escape(user.username or '—')}\n"
            f"🆔 <code>{user.id}</code>",
            reply_markup=get_issue_vpn_keyboard(user.id),
        )
    except Exception as e:
        logger.warning("[VPN] Не удалось переслать запрос администратору | admin_id={} error={}", settings.admin_id, e)
