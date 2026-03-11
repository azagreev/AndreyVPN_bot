"""
Функциональные тесты: полные пользовательские сценарии.

Каждый тест проходит несколько шагов взаимодействия с реальной БД,
имитируя реальное использование бота от начала до конца.
"""
import pytest
from unittest.mock import patch, AsyncMock

from tests.conftest import make_message, make_callback, make_bot, make_state


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

async def insert_approved_user(db, user_id, username="user", full_name="Test User"):
    await db.execute(
        "INSERT OR IGNORE INTO users (telegram_id, username, full_name, is_approved) VALUES (?, ?, ?, 1)",
        (user_id, username, full_name),
    )
    await db.commit()


async def get_user(db, user_id):
    cursor = await db.execute("SELECT * FROM users WHERE telegram_id = ?", (user_id,))
    return await cursor.fetchone()


async def insert_profile(db, user_id, name="TestVPN", ip="10.0.0.2", public_key="pk_test"):
    await db.execute(
        "INSERT INTO vpn_profiles (user_id, name, private_key, public_key, ipv4_address) VALUES (?, ?, ?, ?, ?)",
        (user_id, name, "enc_key", public_key, ip),
    )
    await db.commit()
    cursor = await db.execute("SELECT last_insert_rowid()")
    row = await cursor.fetchone()
    return row[0]


# ---------------------------------------------------------------------------
# Сценарий 1: Полная регистрация
# ---------------------------------------------------------------------------

async def test_full_registration_flow(prepared_db, db_connection, admin_id):
    """
    Полный сценарий регистрации:
    1. Новый user вызывает cmd_start — получает капчу
    2. Неверный ответ — снова капча
    3. Верный ответ — user в БД pending
    4. Admin одобряет (handle_approve) — user получает keyboard, is_approved=1
    """
    from bot.handlers.common.start import cmd_start, process_captcha, CaptchaStates
    from bot.handlers.admin.approvals import handle_approve, ApprovalAction

    user_id = 5001
    bot = make_bot()

    # Шаг 1: Новый пользователь — получает капчу
    message = make_message(user_id=user_id, text="/start", username="flowuser", full_name="Flow User")
    state = make_state()

    await cmd_start(message, db_connection, state)

    assert message.answer.called, "Новый пользователь должен получить ответ"
    captcha_text = message.answer.call_args[0][0]
    assert "+" in captcha_text and "?" in captcha_text, "Должна быть задача капчи"
    state.set_state.assert_called_once()

    # Шаг 2: Неверный ответ — перегенерация капчи
    state2 = make_state()
    state2.get_data = AsyncMock(return_value={"captcha_answer": 42})

    message2 = make_message(user_id=user_id, text="99")  # неверный ответ
    await process_captcha(message2, db_connection, state2, bot)

    message2.answer.assert_called_once()
    text2 = message2.answer.call_args[0][0]
    assert "+" in text2 and "?" in text2, "После неверного ответа должен быть новый пример"
    state2.clear.assert_not_called()

    # Шаг 3: Верный ответ — регистрация
    correct = 42
    state3 = make_state()
    state3.get_data = AsyncMock(return_value={"captcha_answer": correct})

    message3 = make_message(user_id=user_id, text=str(correct), username="flowuser", full_name="Flow User")
    await process_captcha(message3, db_connection, state3, bot)

    user_row = await get_user(db_connection, user_id)
    assert user_row is not None, "Пользователь должен быть создан в БД"
    assert user_row["is_approved"] == 0, "Пользователь должен ожидать одобрения"

    cursor = await db_connection.execute(
        "SELECT status FROM approvals WHERE user_id = ?", (user_id,)
    )
    approval = await cursor.fetchone()
    assert approval["status"] == "pending", "Заявка должна быть в статусе pending"

    # Шаг 4: Администратор одобряет
    callback = make_callback(user_id=admin_id)
    callback_data = ApprovalAction(action="approve", user_id=user_id)
    admin_bot = make_bot()

    await handle_approve(callback, callback_data, db_connection, admin_bot)

    user_row = await get_user(db_connection, user_id)
    assert user_row["is_approved"] == 1, "После одобрения пользователь должен быть одобрен"

    admin_bot.send_message.assert_called_once()
    notified = admin_bot.send_message.call_args[0][0]
    assert notified == user_id, "Уведомление должно быть отправлено пользователю"


# ---------------------------------------------------------------------------
# Сценарий 2: Полный жизненный цикл профиля
# ---------------------------------------------------------------------------

async def test_full_profile_lifecycle(prepared_db, db_connection, admin_id):
    """
    Полный сценарий работы с профилем:
    1. Одобренный user — пустой список + кнопка Запросить
    2. handle_vpn_request — уведомление admin
    3. Профиль добавлен в БД
    4. handle_profiles — профиль отображён
    5. handle_delete_prompt — клавиатура подтверждения
    6. handle_delete_confirm — профиль удалён
    """
    from bot.handlers.user.profiles import (
        handle_profiles, handle_vpn_request,
        handle_delete_prompt, handle_delete_confirm,
        ProfileAction,
    )

    user_id = 5002
    await insert_approved_user(db_connection, user_id, username="lifecycle", full_name="Lifecycle User")
    bot = make_bot()

    # Шаг 1: Пустой список
    message1 = make_message(user_id=user_id)
    await handle_profiles(message1, db_connection)
    message1.answer.assert_called_once()
    keyboard1 = message1.answer.call_args[1]["reply_markup"]
    all_btns = [btn for row in keyboard1.inline_keyboard for btn in row]
    assert any("Запросить" in b.text for b in all_btns), "Должна быть кнопка 'Запросить'"

    # Шаг 2: Запрос VPN — уведомление admin
    callback_req = make_callback(user_id=user_id)
    await handle_vpn_request(callback_req, bot, db_connection)
    bot.send_message.assert_called_once()
    assert bot.send_message.call_args[0][0] == admin_id, "Уведомление должно быть отправлено admin"

    # Шаг 3: Добавляем профиль напрямую в БД
    profile_id = await insert_profile(db_connection, user_id, name="LifecycleVPN", ip="10.0.0.30",
                                      public_key="pk_lifecycle")

    # Шаг 4: Список с профилем
    message4 = make_message(user_id=user_id)
    await handle_profiles(message4, db_connection)
    message4.answer.assert_called_once()
    keyboard4 = message4.answer.call_args[1]["reply_markup"]
    all_btns4 = [btn.text for row in keyboard4.inline_keyboard for btn in row]
    assert any("LifecycleVPN" in t for t in all_btns4), "Профиль должен отображаться в списке"

    # Шаг 5: Запрос удаления
    callback_del = make_callback(user_id=user_id)
    callback_data_del = ProfileAction(action="delete", profile_id=profile_id)
    await handle_delete_prompt(callback_del, callback_data_del)
    callback_del.message.edit_reply_markup.assert_called_once()

    # Шаг 6: Подтверждение удаления
    callback_confirm = make_callback(user_id=user_id)
    callback_data_confirm = ProfileAction(action="confirm_delete", profile_id=profile_id)

    # delete_profile принимает (db, pid) после рефакторинга — имитируем удаление
    async def fake_delete(db, pid):
        await db_connection.execute("DELETE FROM vpn_profiles WHERE id = ?", (pid,))
        await db_connection.commit()
        return True

    with patch("bot.handlers.user.profiles.VPNService.delete_profile", side_effect=fake_delete):
        await handle_delete_confirm(callback_confirm, callback_data_confirm, db_connection)

    cursor = await db_connection.execute(
        "SELECT id FROM vpn_profiles WHERE id = ?", (profile_id,)
    )
    deleted = await cursor.fetchone()
    assert deleted is None, "После подтверждения удаления профиль должен исчезнуть из БД"


# ---------------------------------------------------------------------------
# Сценарий 3: Статус и трафик
# ---------------------------------------------------------------------------

async def test_full_status_flow(prepared_db, db_connection, admin_id):
    """
    Сценарий просмотра статуса:
    1. Одобренный user с профилями
    2. handle_status — корректная информация об аккаунте
    3. handle_traffic — статистика (пустая если нет WG)
    """
    from bot.handlers.user.status import handle_status, handle_traffic

    user_id = 5003
    await insert_approved_user(db_connection, user_id, username="statususer", full_name="Status User")
    await insert_profile(db_connection, user_id, name="StatusVPN", ip="10.0.0.40", public_key="pk_status")

    # Шаг 2: handle_status
    message_status = make_message(user_id=user_id)
    await handle_status(message_status, db_connection)

    message_status.answer.assert_called_once()
    status_text = message_status.answer.call_args[0][0]
    assert "Status User" in status_text, "Полное имя пользователя должно быть в статусе"
    assert str(user_id) in status_text, "user_id должен быть в статусе"
    assert "1" in status_text, "Количество профилей (1) должно быть указано"

    # Шаг 3: handle_traffic (без wg бинарника — должен корректно обрабатывать)
    message_traffic = make_message(user_id=user_id)

    with patch("bot.services.vpn_service.shutil.which", return_value=None):
        await handle_traffic(message_traffic, db_connection)

    message_traffic.answer.assert_called_once()
    # При отсутствии WG либо нет данных о профилях, либо трафик = 0
    traffic_text = message_traffic.answer.call_args[0][0]
    assert traffic_text, "Должен быть получен ответ о трафике"
