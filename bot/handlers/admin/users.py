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

from bot.filters.admin import AdminFilter
from bot.handlers.admin.menu import BTN_USERS
from bot.services.vpn_service import VPNService
from bot.core.config import settings
from bot.core.logging import audit

router = Router()

PAGE_SIZE = 5


class UserAction(CallbackData, prefix="usr"):
    action: str  # view, block, unblock, issue_vpn, page
    user_id: int
    page: int = 0


class IssueVPN(CallbackData, prefix="ivpn"):
    action: str  # approve, reject
    user_id: int


def get_issue_vpn_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Клавиатура для уведомления о запросе VPN."""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="✅ Выдать конфиг",
            callback_data=IssueVPN(action="approve", user_id=user_id).pack(),
        ),
        InlineKeyboardButton(
            text="❌ Отказать",
            callback_data=IssueVPN(action="reject", user_id=user_id).pack(),
        ),
    ]])


def users_list_keyboard(users: list, page: int, total: int) -> InlineKeyboardMarkup:
    buttons = []
    for u in users:
        uid = u["telegram_id"]
        name = u["full_name"] or "Без имени"
        status = "✅" if u["is_approved"] else "❌"
        buttons.append([
            InlineKeyboardButton(
                text=f"{status} {name}",
                callback_data=UserAction(action="view", user_id=uid, page=page).pack(),
            )
        ])

    pages = max((total + PAGE_SIZE - 1) // PAGE_SIZE, 1)
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(
            text="◀️",
            callback_data=UserAction(action="page", user_id=0, page=page - 1).pack(),
        ))
    nav.append(InlineKeyboardButton(text=f"{page + 1}/{pages}", callback_data="noop"))
    if (page + 1) * PAGE_SIZE < total:
        nav.append(InlineKeyboardButton(
            text="▶️",
            callback_data=UserAction(action="page", user_id=0, page=page + 1).pack(),
        ))
    if nav:
        buttons.append(nav)

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def user_detail_keyboard(user_id: int, is_approved: bool, page: int) -> InlineKeyboardMarkup:
    buttons = []
    if is_approved:
        buttons.append([
            InlineKeyboardButton(
                text="🔑 Выдать VPN",
                callback_data=UserAction(action="issue_vpn", user_id=user_id, page=page).pack(),
            )
        ])
        buttons.append([
            InlineKeyboardButton(
                text="🚫 Заблокировать",
                callback_data=UserAction(action="block", user_id=user_id, page=page).pack(),
            )
        ])
    else:
        buttons.append([
            InlineKeyboardButton(
                text="✅ Разблокировать",
                callback_data=UserAction(action="unblock", user_id=user_id, page=page).pack(),
            )
        ])
    buttons.append([
        InlineKeyboardButton(
            text="◀️ Назад к списку",
            callback_data=UserAction(action="page", user_id=0, page=page).pack(),
        )
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def _get_users_page(db: aiosqlite.Connection, page: int) -> tuple[list, int]:
    cursor = await db.execute("SELECT COUNT(*) as cnt FROM users")
    total = (await cursor.fetchone())["cnt"]

    cursor = await db.execute(
        "SELECT telegram_id, full_name, username, is_approved FROM users ORDER BY registered_at DESC LIMIT ? OFFSET ?",
        (PAGE_SIZE, page * PAGE_SIZE),
    )
    rows = [dict(r) for r in await cursor.fetchall()]
    return rows, total


async def _build_user_detail_text(db: aiosqlite.Connection, user_id: int) -> tuple[str, bool]:
    cursor = await db.execute(
        "SELECT full_name, username, is_approved, registered_at FROM users WHERE telegram_id = ?",
        (user_id,),
    )
    user = await cursor.fetchone()
    if not user:
        return "Пользователь не найден.", False

    cursor = await db.execute(
        "SELECT id, name, ipv4_address FROM vpn_profiles WHERE user_id = ?",
        (user_id,),
    )
    profiles = await cursor.fetchall()

    status = "✅ Одобрен" if user["is_approved"] else "❌ Заблокирован / Ожидает"
    reg_date = user["registered_at"][:10] if user["registered_at"] else "—"
    full_name = html.escape(user["full_name"]) if user["full_name"] else "—"
    username = html.escape(user["username"]) if user["username"] else "—"

    text = (
        f"👤 <b>{full_name}</b>\n"
        f"🔗 @{username}\n"
        f"🆔 <code>{user_id}</code>\n"
        f"📅 {reg_date}\n"
        f"Статус: {status}\n\n"
        f"🔑 Профили ({len(profiles)}):\n"
    )
    for p in profiles:
        text += f"  • {html.escape(p['name'])} ({p['ipv4_address']})\n"
    if not profiles:
        text += "  Нет профилей\n"

    return text, bool(user["is_approved"])


@router.message(F.text == BTN_USERS, AdminFilter())
async def handle_users(message: Message, db: aiosqlite.Connection):
    rows, total = await _get_users_page(db, 0)
    if not rows:
        await message.answer("👥 Нет зарегистрированных пользователей.")
        return
    await message.answer(
        f"👥 <b>Пользователи</b> ({total} всего):",
        reply_markup=users_list_keyboard(rows, 0, total),
    )


@router.callback_query(UserAction.filter(F.action == "page"), AdminFilter())
async def handle_users_page(callback: CallbackQuery, callback_data: UserAction, db: aiosqlite.Connection):
    rows, total = await _get_users_page(db, callback_data.page)
    await callback.message.edit_text(
        f"👥 <b>Пользователи</b> ({total} всего):",
        reply_markup=users_list_keyboard(rows, callback_data.page, total),
    )
    await callback.answer()


@router.callback_query(UserAction.filter(F.action == "view"), AdminFilter())
async def handle_user_view(callback: CallbackQuery, callback_data: UserAction, db: aiosqlite.Connection):
    text, is_approved = await _build_user_detail_text(db, callback_data.user_id)
    await callback.message.edit_text(
        text,
        reply_markup=user_detail_keyboard(callback_data.user_id, is_approved, callback_data.page),
    )
    await callback.answer()


@router.callback_query(UserAction.filter(F.action == "block"), AdminFilter())
async def handle_user_block(callback: CallbackQuery, callback_data: UserAction, db: aiosqlite.Connection, bot: Bot):
    user_id = callback_data.user_id
    admin_id = callback.from_user.id
    await db.execute("UPDATE users SET is_approved = 0 WHERE telegram_id = ?", (user_id,))
    await db.commit()

    logger.info("[ACCESS] Пользователь заблокирован | user_id={} by_admin={}", user_id, admin_id)
    audit("BLOCKED", user_id=user_id, by_admin=admin_id)

    await callback.answer("🚫 Пользователь заблокирован.")
    text, is_approved = await _build_user_detail_text(db, user_id)
    await callback.message.edit_text(
        text,
        reply_markup=user_detail_keyboard(user_id, is_approved, callback_data.page),
    )

    try:
        await bot.send_message(user_id, "🚫 Ваш доступ был заблокирован администратором.")
    except Exception as e:
        logger.warning("[ACCESS] Не удалось уведомить пользователя о блокировке | user_id={} error={}", user_id, e)


@router.callback_query(UserAction.filter(F.action == "unblock"), AdminFilter())
async def handle_user_unblock(callback: CallbackQuery, callback_data: UserAction, db: aiosqlite.Connection, bot: Bot):
    user_id = callback_data.user_id
    admin_id = callback.from_user.id
    await db.execute("UPDATE users SET is_approved = 1 WHERE telegram_id = ?", (user_id,))
    await db.commit()

    logger.info("[ACCESS] Пользователь разблокирован | user_id={} by_admin={}", user_id, admin_id)
    audit("UNBLOCKED", user_id=user_id, by_admin=admin_id)

    await callback.answer("✅ Пользователь разблокирован.")
    text, is_approved = await _build_user_detail_text(db, user_id)
    await callback.message.edit_text(
        text,
        reply_markup=user_detail_keyboard(user_id, is_approved, callback_data.page),
    )

    from bot.handlers.user.menu import get_user_keyboard

    try:
        await bot.send_message(
            user_id,
            "✅ Ваш доступ восстановлен!",
            reply_markup=get_user_keyboard(),
        )
    except Exception as e:
        logger.warning("[ACCESS] Не удалось уведомить пользователя о разблокировке | user_id={} error={}", user_id, e)


@router.callback_query(UserAction.filter(F.action == "issue_vpn"), AdminFilter())
async def handle_issue_vpn_from_panel(callback: CallbackQuery, callback_data: UserAction, db: aiosqlite.Connection, bot: Bot):
    user_id = callback_data.user_id
    await callback.answer("Генерирую профиль...")
    await callback.message.edit_text(callback.message.text + "\n\n⏳ Генерация профиля...")
    await _issue_vpn_to_user(callback, user_id, db, bot)


@router.callback_query(IssueVPN.filter(F.action == "approve"), AdminFilter())
async def handle_vpn_approve(callback: CallbackQuery, callback_data: IssueVPN, db: aiosqlite.Connection, bot: Bot):
    user_id = callback_data.user_id
    await callback.answer("Генерирую профиль...")
    await callback.message.edit_text(callback.message.text + "\n\n⏳ Генерация профиля...")
    await _issue_vpn_to_user(callback, user_id, db, bot)


@router.callback_query(IssueVPN.filter(F.action == "reject"), AdminFilter())
async def handle_vpn_reject(callback: CallbackQuery, callback_data: IssueVPN, bot: Bot):
    user_id = callback_data.user_id
    logger.info("[VPN] Запрос на профиль отклонён администратором | user_id={} admin_id={}", user_id, callback.from_user.id)
    await callback.answer("Запрос отклонён.")
    await callback.message.edit_text(callback.message.text + "\n\n❌ <b>Отклонено.</b>")

    try:
        await bot.send_message(user_id, "❌ Ваш запрос на VPN профиль был отклонён.")
    except Exception as e:
        logger.warning("[VPN] Не удалось уведомить пользователя об отказе | user_id={} error={}", user_id, e)


async def _issue_vpn_to_user(callback: CallbackQuery, user_id: int, db: aiosqlite.Connection, bot: Bot):
    admin_id = callback.from_user.id
    try:
        cursor = await db.execute(
            "SELECT COUNT(*) as cnt FROM vpn_profiles WHERE user_id = ?",
            (user_id,),
        )
        cnt = (await cursor.fetchone())["cnt"]
        profile_name = f"VPN_{user_id}_{cnt + 1}"

        logger.info("[VPN] Создание профиля | user_id={} profile={} by_admin={}", user_id, profile_name, admin_id)
        result = await VPNService.create_profile(user_id, profile_name)
        logger.info("[VPN] Профиль создан | user_id={} profile={} ip={} synced={}", user_id, profile_name, result["ipv4"], result["synced"])
        audit("VPN_ISSUED", user_id=user_id, profile=profile_name, ip=result["ipv4"], by_admin=admin_id)

        if not result["synced"]:
            logger.warning("[VPN] Peer не синхронизирован с WireGuard | user_id={} profile={} ip={}", user_id, profile_name, result["ipv4"])

        qr_bytes = VPNService.generate_qr_code(result["config"])
        qr_file = BufferedInputFile(qr_bytes, filename=f"{profile_name}.png")
        conf_file = BufferedInputFile(result["config"].encode(), filename=f"{profile_name}.conf")

        await bot.send_photo(
            user_id,
            photo=qr_file,
            caption=(
                f"✅ <b>VPN профиль готов!</b>\n\n"
                f"Название: <b>{html.escape(profile_name)}</b>\n"
                f"IP: <code>{result['ipv4']}</code>\n\n"
                "1. Установите <b>AmneziaWG</b>\n"
                "2. Отсканируйте QR-код или импортируйте .conf файл\n"
                "3. Подключитесь! 🚀"
            ),
        )
        await bot.send_document(user_id, document=conf_file)

        clean_text = callback.message.text.replace("⏳ Генерация профиля...", "").rstrip()
        await callback.message.edit_text(
            f"{clean_text}\n\n✅ <b>Конфиг выдан.</b> IP: <code>{result['ipv4']}</code>"
        )

    except Exception as e:
        logger.error("[VPN] Ошибка создания профиля | user_id={} by_admin={} error={}", user_id, admin_id, e, exc_info=True)
        await callback.message.answer(f"❌ Ошибка при создании профиля: {html.escape(str(e))}")
