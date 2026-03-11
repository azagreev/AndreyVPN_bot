"""
Интеграционные тесты для процесса регистрации пользователей.

Используют реальную SQLite БД. Telegram API полностью замокан.
"""
import pytest
from unittest.mock import patch, AsyncMock

from tests.conftest import make_message, make_bot, make_state


# ---------------------------------------------------------------------------
# Вспомогательная функция вставки пользователя
# ---------------------------------------------------------------------------

async def insert_user(db, telegram_id, username="user", full_name="Full Name", is_approved=0):
    await db.execute(
        "INSERT OR IGNORE INTO users (telegram_id, username, full_name, is_approved) VALUES (?, ?, ?, ?)",
        (telegram_id, username, full_name, is_approved),
    )
    await db.commit()


async def insert_approval(db, user_id, status="pending"):
    await db.execute(
        "INSERT INTO approvals (user_id, status) VALUES (?, ?)",
        (user_id, status),
    )
    await db.commit()


# ---------------------------------------------------------------------------
# Тесты
# ---------------------------------------------------------------------------

async def test_new_user_gets_captcha(prepared_db, db_connection, admin_id):
    """Новый пользователь при вызове cmd_start получает задачу капчи, state переведён в waiting_for_answer."""
    from bot.handlers.common.start import cmd_start, CaptchaStates

    user_id = 1001
    message = make_message(user_id=user_id, text="/start", username="newuser", full_name="New User")
    state = make_state()

    await cmd_start(message, db_connection, state)

    message.answer.assert_called_once()
    text = message.answer.call_args[0][0]
    assert "+" in text and "?" in text, "Ответ должен содержать задачу капчи"

    state.set_state.assert_called_once()
    call_args = state.set_state.call_args[0][0]
    assert "waiting_for_answer" in str(call_args), "Стейт должен быть установлен в waiting_for_answer"


async def test_wrong_captcha_regenerates(prepared_db, db_connection, admin_id):
    """При неверном ответе на капчу генерируется новый пример, стейт не сбрасывается."""
    from bot.handlers.common.start import process_captcha

    state = make_state()
    state.get_data = AsyncMock(return_value={"captcha_answer": 15})

    message = make_message(user_id=1002, text="99")  # явно неверный ответ
    bot = make_bot()

    await process_captcha(message, db_connection, state, bot)

    message.answer.assert_called_once()
    text = message.answer.call_args[0][0]
    assert "+" in text and "?" in text, "При неверном ответе должен появиться новый пример"
    state.clear.assert_not_called(), "Стейт не должен сбрасываться при неверном ответе"


async def test_correct_captcha_registers_user(prepared_db, db_connection, admin_id):
    """Верный ответ на капчу регистрирует пользователя и уведомляет админа."""
    from bot.handlers.common.start import process_captcha

    user_id = 1003
    correct_answer = 7

    state = make_state()
    state.get_data = AsyncMock(return_value={"captcha_answer": correct_answer})

    message = make_message(user_id=user_id, text=str(correct_answer), username="tester", full_name="Tester")
    bot = make_bot()

    await process_captcha(message, db_connection, state, bot)

    # Пользователь должен появиться в users с is_approved=0
    cursor = await db_connection.execute(
        "SELECT is_approved FROM users WHERE telegram_id = ?", (user_id,)
    )
    row = await cursor.fetchone()
    assert row is not None, "Пользователь должен быть создан в БД"
    assert row["is_approved"] == 0, "Пользователь не должен быть одобрен сразу"

    # Запись в approvals со статусом pending
    cursor = await db_connection.execute(
        "SELECT status FROM approvals WHERE user_id = ?", (user_id,)
    )
    approval = await cursor.fetchone()
    assert approval is not None, "Должна быть запись в approvals"
    assert approval["status"] == "pending", "Статус заявки должен быть pending"

    # Уведомление администратора
    bot.send_message.assert_called_once()
    call_args = bot.send_message.call_args
    assert call_args[0][0] == admin_id, "Уведомление должно отправляться на admin_id"

    # Стейт сброшен
    state.clear.assert_called_once()


async def test_existing_approved_user_gets_keyboard(prepared_db, db_connection, admin_id):
    """Одобренный пользователь при /start получает пользовательскую клавиатуру."""
    from bot.handlers.common.start import cmd_start

    user_id = 1004
    await insert_user(db_connection, user_id, is_approved=1)

    message = make_message(user_id=user_id, text="/start")
    state = make_state()

    await cmd_start(message, db_connection, state)

    message.answer.assert_called_once()
    text = message.answer.call_args[0][0]
    assert "возвращени" in text.lower() or "🚀" in text, "Одобренный пользователь должен получить приветствие"

    kwargs = message.answer.call_args[1]
    assert "reply_markup" in kwargs, "Должна быть передана клавиатура"


async def test_existing_pending_user_gets_wait_message(prepared_db, db_connection, admin_id):
    """Пользователь с незавершённой заявкой получает сообщение об ожидании."""
    from bot.handlers.common.start import cmd_start

    user_id = 1005
    await insert_user(db_connection, user_id, is_approved=0)

    message = make_message(user_id=user_id, text="/start")
    state = make_state()

    await cmd_start(message, db_connection, state)

    message.answer.assert_called_once()
    text = message.answer.call_args[0][0]
    assert "ожидани" in text.lower() or "рассматрива" in text.lower(), \
        "Пользователь в ожидании должен получить соответствующее сообщение"


async def test_admin_gets_admin_keyboard_on_start(prepared_db, db_connection, admin_id):
    """Администратор при /start получает admin keyboard и добавляется в users с is_approved=1."""
    from bot.handlers.common.start import cmd_start

    message = make_message(user_id=admin_id, text="/start", username="admin_user", full_name="Admin")
    state = make_state()

    await cmd_start(message, db_connection, state)

    message.answer.assert_called_once()
    kwargs = message.answer.call_args[1]
    assert "reply_markup" in kwargs, "Должна быть передана клавиатура для администратора"

    cursor = await db_connection.execute(
        "SELECT is_approved, is_admin FROM users WHERE telegram_id = ?", (admin_id,)
    )
    row = await cursor.fetchone()
    assert row is not None, "Администратор должен быть добавлен в БД"
    assert row["is_approved"] == 1, "Администратор должен быть одобрен"
    assert row["is_admin"] == 1, "Должен быть установлен флаг is_admin"


async def test_cancel_clears_captcha_state(prepared_db, db_connection, admin_id):
    """cmd_cancel сбрасывает FSM состояние и возвращает инструкцию с /start."""
    from bot.handlers.common.start import cmd_cancel

    state = make_state()
    message = make_message(user_id=1099, text="/cancel")

    await cmd_cancel(message, state)

    state.clear.assert_called_once(), "FSM состояние должно быть сброшено"
    message.answer.assert_called_once()
    text = message.answer.call_args[0][0]
    assert "/start" in text, "Сообщение об отмене должно содержать /start"


async def test_notification_to_admin_escapes_html(prepared_db, db_connection, admin_id):
    """Уведомление администратору экранирует HTML в full_name и username пользователя."""
    from bot.handlers.common.start import process_captcha

    user_id = 1098
    correct_answer = 5

    state = make_state()
    state.get_data = AsyncMock(return_value={"captcha_answer": correct_answer})

    # full_name с HTML-символами
    message = make_message(
        user_id=user_id,
        text=str(correct_answer),
        username="hacker<b>",
        full_name="<script>alert(1)</script>",
    )
    bot = make_bot()

    await process_captcha(message, db_connection, state, bot)

    bot.send_message.assert_called_once()
    notification_text = bot.send_message.call_args[0][1]
    # HTML-теги должны быть экранированы
    assert "<script>" not in notification_text, "HTML теги в full_name должны быть экранированы"
    assert "&lt;script&gt;" in notification_text or "script" in notification_text, \
        "Экранированный тег должен присутствовать"
