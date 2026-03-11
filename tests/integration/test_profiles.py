"""
Интеграционные тесты для управления VPN-профилями пользователей.
"""
import pytest
from unittest.mock import patch, AsyncMock

from tests.conftest import make_message, make_callback, make_bot


async def create_approved_user(db, user_id, username="user", full_name="Test User"):
    await db.execute(
        "INSERT OR IGNORE INTO users (telegram_id, username, full_name, is_approved) VALUES (?, ?, ?, 1)",
        (user_id, username, full_name),
    )
    await db.commit()


async def create_profile(db, user_id, profile_id=None, name="TestProfile", ip="10.0.0.2",
                         private_key="encrypted_key", public_key="pub_key"):
    await db.execute(
        "INSERT INTO vpn_profiles (user_id, name, private_key, public_key, ipv4_address) VALUES (?, ?, ?, ?, ?)",
        (user_id, name, private_key, public_key, ip),
    )
    await db.commit()
    cursor = await db.execute("SELECT last_insert_rowid()")
    row = await cursor.fetchone()
    return row[0]


async def test_user_with_no_profiles_sees_request_button(prepared_db, db_connection, admin_id):
    """handle_profiles для пользователя без профилей показывает инлайн-кнопку 'Запросить'."""
    from bot.handlers.user.profiles import handle_profiles

    user_id = 3001
    await create_approved_user(db_connection, user_id)
    message = make_message(user_id=user_id)

    await handle_profiles(message, db_connection)

    message.answer.assert_called_once()
    kwargs = message.answer.call_args[1]
    assert "reply_markup" in kwargs
    keyboard = kwargs["reply_markup"]
    all_buttons = [btn for row in keyboard.inline_keyboard for btn in row]
    request_btn = next((b for b in all_buttons if "Запросить" in b.text), None)
    assert request_btn is not None, "Должна быть кнопка 'Запросить VPN профиль'"


async def test_user_with_profiles_sees_list(prepared_db, db_connection, admin_id):
    """handle_profiles для пользователя с 2 профилями отображает оба в клавиатуре."""
    from bot.handlers.user.profiles import handle_profiles

    user_id = 3002
    await create_approved_user(db_connection, user_id)
    await create_profile(db_connection, user_id, name="Profile_A", ip="10.0.0.2", public_key="pub_key_A")
    await create_profile(db_connection, user_id, name="Profile_B", ip="10.0.0.3", public_key="pub_key_B")

    message = make_message(user_id=user_id)
    await handle_profiles(message, db_connection)

    message.answer.assert_called_once()
    kwargs = message.answer.call_args[1]
    keyboard = kwargs["reply_markup"]
    all_buttons_text = [btn.text for row in keyboard.inline_keyboard for btn in row]
    combined_text = " ".join(all_buttons_text)
    assert "Profile_A" in combined_text
    assert "Profile_B" in combined_text


async def test_delete_confirm_removes_profile(prepared_db, db_connection, admin_id):
    """handle_delete_confirm удаляет профиль из БД."""
    from bot.handlers.user.profiles import handle_delete_confirm, ProfileAction

    user_id = 3003
    await create_approved_user(db_connection, user_id)
    profile_id = await create_profile(db_connection, user_id, name="ToDelete", ip="10.0.0.4",
                                      public_key="pub_key_del")

    callback = make_callback(user_id=user_id)
    callback_data = ProfileAction(action="confirm_delete", profile_id=profile_id)

    async def fake_delete(db, pid):
        await db_connection.execute("DELETE FROM vpn_profiles WHERE id = ?", (pid,))
        await db_connection.commit()
        return True

    with patch("bot.handlers.user.profiles.VPNService.delete_profile", side_effect=fake_delete):
        await handle_delete_confirm(callback, callback_data, db_connection)

    cursor = await db_connection.execute("SELECT id FROM vpn_profiles WHERE id = ?", (profile_id,))
    row = await cursor.fetchone()
    assert row is None, "Профиль должен быть удалён из БД"
    callback.answer.assert_called()


async def test_delete_cancel_restores_keyboard(prepared_db, db_connection, admin_id):
    """handle_delete_cancel восстанавливает оригинальную клавиатуру профилей."""
    from bot.handlers.user.profiles import handle_delete_cancel, ProfileAction

    user_id = 3004
    await create_approved_user(db_connection, user_id)
    profile_id = await create_profile(db_connection, user_id, name="StayAlive", ip="10.0.0.5",
                                      public_key="pub_key_stay")

    callback = make_callback(user_id=user_id)
    callback_data = ProfileAction(action="cancel_delete", profile_id=profile_id)

    await handle_delete_cancel(callback, callback_data, db_connection)

    callback.message.edit_reply_markup.assert_called_once()
    callback.answer.assert_called_once()


async def test_cannot_delete_other_users_profile(prepared_db, db_connection, admin_id):
    """Пользователь не может удалить профиль, принадлежащий другому пользователю."""
    from bot.handlers.user.profiles import handle_delete_confirm, ProfileAction

    owner_id = 3005
    attacker_id = 3006
    await create_approved_user(db_connection, owner_id)
    await create_approved_user(db_connection, attacker_id)
    profile_id = await create_profile(db_connection, owner_id, name="OwnerProfile", ip="10.0.0.6",
                                      public_key="pub_key_owner")

    callback = make_callback(user_id=attacker_id)
    callback_data = ProfileAction(action="confirm_delete", profile_id=profile_id)

    await handle_delete_confirm(callback, callback_data, db_connection)

    callback.answer.assert_called_once()
    call_kwargs = callback.answer.call_args[1]
    assert call_kwargs.get("show_alert") is True

    cursor = await db_connection.execute("SELECT id FROM vpn_profiles WHERE id = ?", (profile_id,))
    row = await cursor.fetchone()
    assert row is not None, "Профиль не должен быть удалён при атаке"


async def test_cannot_download_conf_for_other_users_profile(prepared_db, db_connection, admin_id):
    """handle_download_conf отклоняет запрос на чужой профиль с show_alert=True."""
    from bot.handlers.user.profiles import handle_download_conf, ProfileAction

    owner_id = 3007
    attacker_id = 3008
    await create_approved_user(db_connection, owner_id)
    await create_approved_user(db_connection, attacker_id)
    profile_id = await create_profile(db_connection, owner_id, name="OwnerConf", ip="10.0.0.7",
                                      public_key="pub_key_conf")

    callback = make_callback(user_id=attacker_id)
    callback_data = ProfileAction(action="conf", profile_id=profile_id)
    bot = make_bot()

    await handle_download_conf(callback, callback_data, bot, db_connection)

    callback.answer.assert_called_once()
    call_kwargs = callback.answer.call_args[1]
    assert call_kwargs.get("show_alert") is True, "Должен быть show_alert при попытке скачать чужой конфиг"
    bot.send_document.assert_not_called(), "Файл не должен быть отправлен"


async def test_cannot_show_qr_for_other_users_profile(prepared_db, db_connection, admin_id):
    """handle_show_qr отклоняет запрос на чужой QR с show_alert=True."""
    from bot.handlers.user.profiles import handle_show_qr, ProfileAction

    owner_id = 3009
    attacker_id = 3010
    await create_approved_user(db_connection, owner_id)
    await create_approved_user(db_connection, attacker_id)
    profile_id = await create_profile(db_connection, owner_id, name="OwnerQR", ip="10.0.0.8",
                                      public_key="pub_key_qr")

    callback = make_callback(user_id=attacker_id)
    callback_data = ProfileAction(action="qr", profile_id=profile_id)
    bot = make_bot()

    await handle_show_qr(callback, callback_data, bot, db_connection)

    callback.answer.assert_called_once()
    call_kwargs = callback.answer.call_args[1]
    assert call_kwargs.get("show_alert") is True, "Должен быть show_alert при попытке просмотра чужого QR"
    bot.send_photo.assert_not_called(), "Фото не должно быть отправлено"


async def test_vpn_request_notifies_admin(prepared_db, db_connection, admin_id):
    """handle_vpn_request отправляет уведомление администратору."""
    from bot.handlers.user.profiles import handle_vpn_request, _pending_vpn_requests

    user_id = 3011
    await create_approved_user(db_connection, user_id, username="requester", full_name="Requester")

    _pending_vpn_requests.clear()
    callback = make_callback(user_id=user_id)
    bot = make_bot()

    await handle_vpn_request(callback, bot, db_connection)

    bot.send_message.assert_called_once()
    call_args = bot.send_message.call_args
    assert call_args[0][0] == admin_id, "Уведомление должно отправляться на admin_id"


async def test_vpn_request_blocked_within_ttl(prepared_db, db_connection, admin_id):
    """Повторный запрос в течение 24ч блокируется."""
    from bot.handlers.user.profiles import handle_vpn_request, _pending_vpn_requests

    user_id = 3020
    await create_approved_user(db_connection, user_id, username="ttl_user", full_name="TTL User")

    _pending_vpn_requests.clear()
    import time
    _pending_vpn_requests[user_id] = time.time()  # уже есть свежий запрос

    callback = make_callback(user_id=user_id)
    bot = make_bot()

    await handle_vpn_request(callback, bot, db_connection)

    # Уведомление администратору НЕ должно уйти
    bot.send_message.assert_not_called()
    callback.answer.assert_called_once()
    assert "ожидайте" in callback.answer.call_args[0][0]


async def test_vpn_request_allowed_after_ttl_expired(prepared_db, db_connection, admin_id):
    """Запрос разрешён если предыдущий старше 24ч."""
    from bot.handlers.user.profiles import handle_vpn_request, _pending_vpn_requests, PENDING_REQUEST_TTL

    user_id = 3021
    await create_approved_user(db_connection, user_id, username="expired_user", full_name="Expired User")

    _pending_vpn_requests.clear()
    import time
    _pending_vpn_requests[user_id] = time.time() - PENDING_REQUEST_TTL - 1  # истёк

    callback = make_callback(user_id=user_id)
    bot = make_bot()

    await handle_vpn_request(callback, bot, db_connection)

    bot.send_message.assert_called_once()
    assert bot.send_message.call_args[0][0] == admin_id


async def test_vpn_request_blocked_at_profile_limit(prepared_db, db_connection, admin_id, test_settings, monkeypatch):
    """Запрос блокируется если пользователь достиг лимита профилей."""
    from bot.handlers.user.profiles import handle_vpn_request, _pending_vpn_requests
    from bot.core.config import settings

    user_id = 3022
    await create_approved_user(db_connection, user_id, username="limit_user", full_name="Limit User")

    monkeypatch.setattr(settings, "max_profiles_per_user", 2, raising=False)

    # Вставляем 2 профиля — лимит достигнут
    for i, (ip, pk) in enumerate([("10.0.0.90", "pk_lim1"), ("10.0.0.91", "pk_lim2")], start=1):
        await db_connection.execute(
            "INSERT INTO vpn_profiles (user_id, name, private_key, public_key, ipv4_address) VALUES (?, ?, ?, ?, ?)",
            (user_id, f"Prof_{i}", "enc_key", pk, ip),
        )
    await db_connection.commit()

    _pending_vpn_requests.clear()
    callback = make_callback(user_id=user_id)
    bot = make_bot()

    await handle_vpn_request(callback, bot, db_connection)

    bot.send_message.assert_not_called()
    callback.answer.assert_called_once()
    assert "лимит" in callback.answer.call_args[0][0]

    # TTL запись должна быть сброшена — пользователь может попробовать снова после удаления профиля
    assert user_id not in _pending_vpn_requests
