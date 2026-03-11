"""
Интеграционные тесты для панели одобрения заявок.

Проверяют корректность обновления БД при одобрении/отклонении,
уведомления пользователей и отображения списков с пагинацией.
"""
import pytest
from unittest.mock import AsyncMock

from tests.conftest import make_message, make_callback, make_bot


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

async def create_pending_user(db, user_id, username=None, full_name=None):
    full_name = full_name or f"User {user_id}"
    await db.execute(
        "INSERT OR IGNORE INTO users (telegram_id, username, full_name, is_approved) VALUES (?, ?, ?, 0)",
        (user_id, username, full_name),
    )
    await db.execute(
        "INSERT INTO approvals (user_id, status) VALUES (?, 'pending')",
        (user_id,),
    )
    await db.commit()


# ---------------------------------------------------------------------------
# Тесты одобрения и отклонения
# ---------------------------------------------------------------------------

async def test_approve_user_updates_db(prepared_db, db_connection, admin_id):
    """handle_approve обновляет users.is_approved=1 и approvals.status='approved'."""
    from bot.handlers.admin.approvals import handle_approve, ApprovalAction

    user_id = 2001
    await create_pending_user(db_connection, user_id)

    callback = make_callback(user_id=admin_id)
    callback_data = ApprovalAction(action="approve", user_id=user_id)
    bot = make_bot()

    await handle_approve(callback, callback_data, db_connection, bot)

    cursor = await db_connection.execute(
        "SELECT is_approved FROM users WHERE telegram_id = ?", (user_id,)
    )
    row = await cursor.fetchone()
    assert row["is_approved"] == 1, "Пользователь должен быть одобрен в БД"

    cursor = await db_connection.execute(
        "SELECT status FROM approvals WHERE user_id = ?", (user_id,)
    )
    approval = await cursor.fetchone()
    assert approval["status"] == "approved", "Статус заявки должен стать 'approved'"


async def test_reject_user_updates_db(prepared_db, db_connection, admin_id):
    """handle_reject обновляет approvals.status='rejected'."""
    from bot.handlers.admin.approvals import handle_reject, ApprovalAction

    user_id = 2002
    await create_pending_user(db_connection, user_id)

    callback = make_callback(user_id=admin_id)
    callback_data = ApprovalAction(action="reject", user_id=user_id)
    bot = make_bot()

    await handle_reject(callback, callback_data, db_connection, bot)

    cursor = await db_connection.execute(
        "SELECT status FROM approvals WHERE user_id = ?", (user_id,)
    )
    approval = await cursor.fetchone()
    assert approval["status"] == "rejected", "Статус заявки должен стать 'rejected'"


async def test_approve_notifies_user(prepared_db, db_connection, admin_id):
    """handle_approve отправляет уведомление одобренному пользователю."""
    from bot.handlers.admin.approvals import handle_approve, ApprovalAction

    user_id = 2003
    await create_pending_user(db_connection, user_id)

    callback = make_callback(user_id=admin_id)
    callback_data = ApprovalAction(action="approve", user_id=user_id)
    bot = make_bot()

    await handle_approve(callback, callback_data, db_connection, bot)

    bot.send_message.assert_called_once()
    notified_user = bot.send_message.call_args[0][0]
    assert notified_user == user_id, "Уведомление должно отправляться пользователю с его user_id"


async def test_reject_notifies_user(prepared_db, db_connection, admin_id):
    """handle_reject отправляет уведомление отклонённому пользователю."""
    from bot.handlers.admin.approvals import handle_reject, ApprovalAction

    user_id = 2004
    await create_pending_user(db_connection, user_id)

    callback = make_callback(user_id=admin_id)
    callback_data = ApprovalAction(action="reject", user_id=user_id)
    bot = make_bot()

    await handle_reject(callback, callback_data, db_connection, bot)

    bot.send_message.assert_called_once()
    notified_user = bot.send_message.call_args[0][0]
    assert notified_user == user_id, "Уведомление при отклонении должно отправляться пользователю"


# ---------------------------------------------------------------------------
# Тесты отображения списка заявок
# ---------------------------------------------------------------------------

async def test_pending_list_shows_correct_count(prepared_db, db_connection, admin_id):
    """При 3 pending пользователях текст содержит '(3 ожидает)'."""
    from bot.handlers.admin.approvals import handle_approvals

    for uid in [2010, 2011, 2012]:
        await create_pending_user(db_connection, uid, full_name=f"User {uid}")

    message = make_message(user_id=admin_id)

    await handle_approvals(message, db_connection)

    message.answer.assert_called_once()
    text = message.answer.call_args[0][0]
    assert "3" in text, "Текст должен содержать количество ожидающих (3)"
    assert "ожидает" in text, "Текст должен содержать слово 'ожидает'"


async def test_pending_list_empty(prepared_db, db_connection, admin_id):
    """При отсутствии заявок выводится сообщение 'Нет ожидающих заявок'."""
    from bot.handlers.admin.approvals import handle_approvals

    message = make_message(user_id=admin_id)

    await handle_approvals(message, db_connection)

    message.answer.assert_called_once()
    text = message.answer.call_args[0][0]
    assert "Нет" in text or "нет" in text.lower(), "Должно быть сообщение об отсутствии заявок"


async def test_pending_list_pagination(prepared_db, db_connection, admin_id):
    """При 7 пользователях и page_size=5 на странице 1 есть кнопка ▶️."""
    from bot.handlers.admin.approvals import handle_approvals, PAGE_SIZE

    # Создаём 7 pending пользователей
    for uid in range(2020, 2027):
        await create_pending_user(db_connection, uid, full_name=f"User {uid}")

    message = make_message(user_id=admin_id)

    await handle_approvals(message, db_connection)

    message.answer.assert_called_once()
    kwargs = message.answer.call_args[1]
    assert "reply_markup" in kwargs, "Должна быть клавиатура с пагинацией"

    keyboard = kwargs["reply_markup"]
    all_buttons = [btn for row in keyboard.inline_keyboard for btn in row]
    forward_btns = [b for b in all_buttons if "▶" in b.text]
    assert len(forward_btns) >= 1, "При 7 пользователях на первой странице должна быть кнопка ▶️"
