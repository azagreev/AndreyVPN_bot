from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters.callback_data import CallbackData
from loguru import logger
import aiosqlite

from bot.filters.admin import AdminFilter
from bot.keyboards.admin import BTN_APPROVALS
from bot.keyboards.user import get_user_keyboard
from bot.core.logging import audit
from bot.db import repository

router = Router()

PAGE_SIZE = 5


class ApprovalAction(CallbackData, prefix="appr"):
    action: str  # approve, reject, page
    user_id: int
    page: int = 0


def get_approval_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Клавиатура для уведомления о новой заявке."""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="✅ Одобрить",
            callback_data=ApprovalAction(action="approve", user_id=user_id).pack(),
        ),
        InlineKeyboardButton(
            text="❌ Отклонить",
            callback_data=ApprovalAction(action="reject", user_id=user_id).pack(),
        ),
    ]])


def pending_list_keyboard(users: list, page: int, total: int) -> InlineKeyboardMarkup:
    buttons = []
    for u in users:
        uid = u["user_id"]
        name = u["full_name"] or "Без имени"
        username = u["username"]
        label = f"👤 {name}" + (f" (@{username})" if username else "")
        buttons.append([InlineKeyboardButton(text=label, callback_data="noop")])
        buttons.append([
            InlineKeyboardButton(
                text="✅ Одобрить",
                callback_data=ApprovalAction(action="approve", user_id=uid, page=page).pack(),
            ),
            InlineKeyboardButton(
                text="❌ Отклонить",
                callback_data=ApprovalAction(action="reject", user_id=uid, page=page).pack(),
            ),
        ])

    pages = max((total + PAGE_SIZE - 1) // PAGE_SIZE, 1)
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(
            text="◀️",
            callback_data=ApprovalAction(action="page", user_id=0, page=page - 1).pack(),
        ))
    nav.append(InlineKeyboardButton(text=f"{page + 1}/{pages}", callback_data="noop"))
    if (page + 1) * PAGE_SIZE < total:
        nav.append(InlineKeyboardButton(
            text="▶️",
            callback_data=ApprovalAction(action="page", user_id=0, page=page + 1).pack(),
        ))
    if nav:
        buttons.append(nav)

    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.message(F.text == BTN_APPROVALS, AdminFilter())
async def handle_approvals(message: Message, db: aiosqlite.Connection):
    rows, total = await repository.get_pending_approvals(db, 0, PAGE_SIZE)
    logger.debug("[ACCESS] Админ открыл список заявок | admin_id={} pending={}", message.from_user.id, total)
    if not rows:
        await message.answer("✅ Нет ожидающих заявок.")
        return
    await message.answer(
        f"⏳ <b>Заявки на доступ</b> ({total} ожидает):",
        reply_markup=pending_list_keyboard(rows, 0, total),
    )


@router.callback_query(ApprovalAction.filter(F.action == "page"), AdminFilter())
async def handle_approvals_page(callback: CallbackQuery, callback_data: ApprovalAction, db: aiosqlite.Connection):
    rows, total = await repository.get_pending_approvals(db, callback_data.page, PAGE_SIZE)
    await callback.message.edit_text(
        f"⏳ <b>Заявки на доступ</b> ({total} ожидает):",
        reply_markup=pending_list_keyboard(rows, callback_data.page, total),
    )
    await callback.answer()


@router.callback_query(ApprovalAction.filter(F.action == "approve"), AdminFilter())
async def handle_approve(callback: CallbackQuery, callback_data: ApprovalAction, db: aiosqlite.Connection, bot: Bot):
    user_id = callback_data.user_id
    admin_id = callback.from_user.id

    await repository.set_user_approved(db, user_id, True)
    await repository.set_approval_status(db, user_id, "approved", admin_id)

    logger.info("[ACCESS] Пользователь одобрен | user_id={} by_admin={}", user_id, admin_id)
    audit("APPROVED", user_id=user_id, by_admin=admin_id)

    # Очищаем pending VPN requests для этого пользователя
    from bot.handlers.user.profiles import _pending_vpn_requests
    _pending_vpn_requests.discard(user_id)

    await callback.answer("✅ Пользователь одобрен!")
    await callback.message.edit_text(callback.message.text + "\n\n✅ <b>Одобрено.</b>")

    try:
        await bot.send_message(
            user_id,
            "✅ <b>Ваш доступ одобрен!</b>\n\n"
            "Теперь вы можете запросить VPN профиль через «🔑 Мои профили».",
            reply_markup=get_user_keyboard(),
        )
    except Exception as e:
        logger.warning("[ACCESS] Не удалось уведомить пользователя об одобрении | user_id={} error={}", user_id, e)


@router.callback_query(ApprovalAction.filter(F.action == "reject"), AdminFilter())
async def handle_reject(callback: CallbackQuery, callback_data: ApprovalAction, db: aiosqlite.Connection, bot: Bot):
    user_id = callback_data.user_id
    admin_id = callback.from_user.id

    await repository.set_approval_status(db, user_id, "rejected", admin_id)

    logger.info("[ACCESS] Заявка пользователя отклонена | user_id={} by_admin={}", user_id, admin_id)
    audit("REJECTED", user_id=user_id, by_admin=admin_id)

    # Очищаем pending VPN requests для этого пользователя
    from bot.handlers.user.profiles import _pending_vpn_requests
    _pending_vpn_requests.discard(user_id)

    await callback.answer("❌ Заявка отклонена.")
    await callback.message.edit_text(callback.message.text + "\n\n❌ <b>Отклонено.</b>")

    try:
        await bot.send_message(user_id, "❌ Ваша заявка на доступ была отклонена.")
    except Exception as e:
        logger.warning("[ACCESS] Не удалось уведомить пользователя об отказе | user_id={} error={}", user_id, e)
