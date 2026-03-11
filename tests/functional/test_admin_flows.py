"""
Функциональные тесты: полные административные сценарии.

Несколько шагов взаимодействия с реальной БД, имитирующие работу администратора.
"""
import pytest
from unittest.mock import patch, AsyncMock

from tests.conftest import make_message, make_callback, make_bot, make_state


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

async def create_user(db, user_id, username=None, full_name=None, is_approved=1):
    full_name = full_name or f"User {user_id}"
    await db.execute(
        "INSERT OR IGNORE INTO users (telegram_id, username, full_name, is_approved) VALUES (?, ?, ?, ?)",
        (user_id, username, full_name, is_approved),
    )
    await db.commit()


async def create_pending_approval(db, user_id):
    await db.execute(
        "INSERT INTO approvals (user_id, status) VALUES (?, 'pending')", (user_id,)
    )
    await db.commit()


async def get_user(db, user_id):
    cursor = await db.execute("SELECT * FROM users WHERE telegram_id = ?", (user_id,))
    return await cursor.fetchone()


# ---------------------------------------------------------------------------
# Сценарий 1: Панель одобрений
# ---------------------------------------------------------------------------

async def test_admin_approval_panel_flow(prepared_db, db_connection, admin_id):
    """
    Полный сценарий панели одобрений:
    1. Создаём 2 pending user
    2. handle_approvals — список с пагинацией
    3. handle_approve — один user одобрен и уведомлён
    4. handle_reject — второй отклонён и уведомлён
    """
    from bot.handlers.admin.approvals import (
        handle_approvals, handle_approve, handle_reject, ApprovalAction
    )

    user_id_1 = 6001
    user_id_2 = 6002

    # Шаг 1: Создаём pending пользователей
    await create_user(db_connection, user_id_1, full_name="Pending User 1", is_approved=0)
    await create_pending_approval(db_connection, user_id_1)
    await create_user(db_connection, user_id_2, full_name="Pending User 2", is_approved=0)
    await create_pending_approval(db_connection, user_id_2)

    # Шаг 2: Список заявок
    message = make_message(user_id=admin_id)
    await handle_approvals(message, db_connection)

    message.answer.assert_called_once()
    text = message.answer.call_args[0][0]
    assert "2" in text, "Должно быть указано количество ожидающих (2)"
    assert "ожидает" in text, "Должно быть слово 'ожидает'"

    # Шаг 3: Одобряем первого
    callback_approve = make_callback(user_id=admin_id)
    callback_data_approve = ApprovalAction(action="approve", user_id=user_id_1)
    bot = make_bot()

    await handle_approve(callback_approve, callback_data_approve, db_connection, bot)

    user1 = await get_user(db_connection, user_id_1)
    assert user1["is_approved"] == 1, "Первый пользователь должен быть одобрен"
    bot.send_message.assert_called_once()
    assert bot.send_message.call_args[0][0] == user_id_1, "Уведомление одобрения должно идти к user_id_1"

    # Шаг 4: Отклоняем второго
    bot2 = make_bot()
    callback_reject = make_callback(user_id=admin_id)
    callback_data_reject = ApprovalAction(action="reject", user_id=user_id_2)

    await handle_reject(callback_reject, callback_data_reject, db_connection, bot2)

    cursor = await db_connection.execute(
        "SELECT status FROM approvals WHERE user_id = ?", (user_id_2,)
    )
    approval2 = await cursor.fetchone()
    assert approval2["status"] == "rejected", "Заявка второго пользователя должна быть отклонена"
    bot2.send_message.assert_called_once()
    assert bot2.send_message.call_args[0][0] == user_id_2, "Уведомление отклонения должно идти к user_id_2"


# ---------------------------------------------------------------------------
# Сценарий 2: Управление пользователями
# ---------------------------------------------------------------------------

async def test_admin_user_management_flow(prepared_db, db_connection, admin_id):
    """
    Полный сценарий управления пользователями:
    1. Создаём 2 пользователей (одобренный + неодобренный)
    2. handle_users — список
    3. handle_user_view (одобренного) — кнопки "Выдать VPN" и "Заблокировать"
    4. handle_user_block — is_approved=0, user уведомлён
    5. handle_user_view снова — кнопка "Разблокировать"
    6. handle_user_unblock — is_approved=1, user уведомлён
    """
    from bot.handlers.admin.users import (
        handle_users, handle_user_view, handle_user_block, handle_user_unblock, UserAction
    )

    user_id_approved = 6010
    user_id_blocked = 6011

    # Шаг 1: Создаём пользователей
    await create_user(db_connection, user_id_approved, full_name="Approved User", is_approved=1)
    await create_user(db_connection, user_id_blocked, full_name="Blocked User", is_approved=0)

    # Шаг 2: Список пользователей
    message = make_message(user_id=admin_id)
    await handle_users(message, db_connection)

    message.answer.assert_called_once()
    text = message.answer.call_args[0][0]
    assert "2" in text, "Должно быть указано общее количество (2)"

    # Шаг 3: Просмотр одобренного пользователя
    callback_view = make_callback(user_id=admin_id)
    callback_data_view = UserAction(action="view", user_id=user_id_approved)

    await handle_user_view(callback_view, callback_data_view, db_connection)

    callback_view.message.edit_text.assert_called_once()
    keyboard_view = callback_view.message.edit_text.call_args[1]["reply_markup"]
    all_btns_view = [btn.text for row in keyboard_view.inline_keyboard for btn in row]
    assert any("VPN" in t for t in all_btns_view), "Должна быть кнопка 'Выдать VPN'"
    assert any("Заблокировать" in t for t in all_btns_view), "Должна быть кнопка 'Заблокировать'"

    # Шаг 4: Блокируем пользователя
    bot_block = make_bot()
    callback_block = make_callback(user_id=admin_id)
    callback_data_block = UserAction(action="block", user_id=user_id_approved)

    await handle_user_block(callback_block, callback_data_block, db_connection, bot_block)

    user_approved = await get_user(db_connection, user_id_approved)
    assert user_approved["is_approved"] == 0, "После блокировки is_approved должно быть 0"
    bot_block.send_message.assert_called_once()

    # Шаг 5: Просмотр заблокированного пользователя — кнопка "Разблокировать"
    callback_view2 = make_callback(user_id=admin_id)
    callback_data_view2 = UserAction(action="view", user_id=user_id_approved)

    await handle_user_view(callback_view2, callback_data_view2, db_connection)

    keyboard_view2 = callback_view2.message.edit_text.call_args[1]["reply_markup"]
    all_btns_view2 = [btn.text for row in keyboard_view2.inline_keyboard for btn in row]
    assert any("Разблокировать" in t for t in all_btns_view2), "Должна быть кнопка 'Разблокировать'"
    assert not any("Заблокировать" in t for t in all_btns_view2), "Не должно быть кнопки 'Заблокировать'"

    # Шаг 6: Разблокируем
    bot_unblock = make_bot()
    callback_unblock = make_callback(user_id=admin_id)
    callback_data_unblock = UserAction(action="unblock", user_id=user_id_approved)

    await handle_user_unblock(callback_unblock, callback_data_unblock, db_connection, bot_unblock)

    user_unblocked = await get_user(db_connection, user_id_approved)
    assert user_unblocked["is_approved"] == 1, "После разблокировки is_approved должно быть 1"
    bot_unblock.send_message.assert_called_once()


# ---------------------------------------------------------------------------
# Сценарий 3: Доступ администратора к пользовательскому меню
# ---------------------------------------------------------------------------

async def test_admin_can_access_user_menu(prepared_db, db_connection, admin_id):
    """
    Сценарий доступа к меню:
    1. Администратор вызывает cmd_start — получает admin keyboard
    2. Администратор вызывает cmd_menu — получает user keyboard
    """
    from bot.handlers.common.start import cmd_start
    from bot.handlers.user.menu import cmd_menu

    # Шаг 1: cmd_start для admin
    message_start = make_message(user_id=admin_id, text="/start", username="admin_boss", full_name="Admin Boss")
    state = make_state()

    await cmd_start(message_start, db_connection, state)

    message_start.answer.assert_called_once()
    kwargs_start = message_start.answer.call_args[1]
    assert "reply_markup" in kwargs_start, "Admin должен получить клавиатуру при /start"

    # Проверяем что это admin keyboard (содержит кнопки администратора)
    admin_kb = kwargs_start["reply_markup"]
    admin_btns = [btn.text for row in admin_kb.keyboard for btn in row]
    from bot.handlers.admin.menu import BTN_USERS, BTN_APPROVALS
    assert BTN_USERS in admin_btns or BTN_APPROVALS in admin_btns, \
        "Admin keyboard должна содержать административные кнопки"

    # Шаг 2: cmd_menu → user keyboard
    message_menu = make_message(user_id=admin_id, text="/menu")

    await cmd_menu(message_menu)

    message_menu.answer.assert_called_once()
    kwargs_menu = message_menu.answer.call_args[1]
    assert "reply_markup" in kwargs_menu, "cmd_menu должен вернуть клавиатуру"

    user_kb = kwargs_menu["reply_markup"]
    user_btns = [btn.text for row in user_kb.keyboard for btn in row]
    from bot.handlers.user.menu import BTN_PROFILES, BTN_STATUS
    assert BTN_PROFILES in user_btns or BTN_STATUS in user_btns, \
        "User keyboard должна содержать пользовательские кнопки"
