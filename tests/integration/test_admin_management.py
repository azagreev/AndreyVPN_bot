"""
Интеграционные тесты для администраторских функций управления пользователями.

Проверяют отображение списков, блокировку/разблокировку, статистику и статус сервера.
"""
import pytest
from unittest.mock import patch, AsyncMock

from tests.conftest import make_message, make_callback, make_bot


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


async def create_profile(db, user_id, name="Profile", ip="10.0.0.2", public_key="pub"):
    await db.execute(
        "INSERT INTO vpn_profiles (user_id, name, private_key, public_key, ipv4_address) VALUES (?, ?, ?, ?, ?)",
        (user_id, name, "enc_key", public_key, ip),
    )
    await db.commit()


async def create_pending(db, user_id):
    await db.execute(
        "INSERT OR IGNORE INTO approvals (user_id, status) VALUES (?, 'pending')", (user_id,)
    )
    await db.commit()


# ---------------------------------------------------------------------------
# Тесты списка пользователей
# ---------------------------------------------------------------------------

async def test_users_list_shows_all_users(prepared_db, db_connection, admin_id):
    """handle_users при 3 пользователях в БД отображает их с указанием общего количества."""
    from bot.handlers.admin.users import handle_users

    for uid in [4001, 4002, 4003]:
        await create_user(db_connection, uid)

    message = make_message(user_id=admin_id)

    await handle_users(message, db_connection)

    message.answer.assert_called_once()
    text = message.answer.call_args[0][0]
    assert "3" in text, "Текст должен содержать общее количество пользователей (3)"
    assert "всего" in text, "Текст должен содержать слово 'всего'"


async def test_users_list_empty(prepared_db, db_connection, admin_id):
    """handle_users при отсутствии пользователей выводит соответствующее сообщение."""
    from bot.handlers.admin.users import handle_users

    message = make_message(user_id=admin_id)

    await handle_users(message, db_connection)

    message.answer.assert_called_once()
    text = message.answer.call_args[0][0]
    assert "Нет" in text or "нет" in text.lower(), "Должно быть сообщение об отсутствии пользователей"


# ---------------------------------------------------------------------------
# Тест просмотра деталей пользователя
# ---------------------------------------------------------------------------

async def test_user_view_shows_profiles(prepared_db, db_connection, admin_id):
    """handle_user_view для пользователя с 2 профилями отображает оба."""
    from bot.handlers.admin.users import handle_user_view, UserAction

    user_id = 4010
    await create_user(db_connection, user_id, full_name="Profile Owner")
    await create_profile(db_connection, user_id, name="Prof_1", ip="10.0.0.10", public_key="pk1")
    await create_profile(db_connection, user_id, name="Prof_2", ip="10.0.0.11", public_key="pk2")

    callback = make_callback(user_id=admin_id)
    callback_data = UserAction(action="view", user_id=user_id)

    await handle_user_view(callback, callback_data, db_connection)

    callback.message.edit_text.assert_called_once()
    text = callback.message.edit_text.call_args[0][0]
    assert "Prof_1" in text, "Текст должен содержать первый профиль"
    assert "Prof_2" in text, "Текст должен содержать второй профиль"


# ---------------------------------------------------------------------------
# Тесты блокировки и разблокировки
# ---------------------------------------------------------------------------

async def test_block_user_updates_db(prepared_db, db_connection, admin_id):
    """handle_user_block устанавливает is_approved=0 для пользователя."""
    from bot.handlers.admin.users import handle_user_block, UserAction

    user_id = 4020
    await create_user(db_connection, user_id, is_approved=1)

    callback = make_callback(user_id=admin_id)
    callback_data = UserAction(action="block", user_id=user_id)
    bot = make_bot()

    await handle_user_block(callback, callback_data, db_connection, bot)

    cursor = await db_connection.execute(
        "SELECT is_approved FROM users WHERE telegram_id = ?", (user_id,)
    )
    row = await cursor.fetchone()
    assert row["is_approved"] == 0, "Заблокированный пользователь должен иметь is_approved=0"


async def test_unblock_user_updates_db(prepared_db, db_connection, admin_id):
    """handle_user_unblock устанавливает is_approved=1 для заблокированного пользователя."""
    from bot.handlers.admin.users import handle_user_unblock, UserAction

    user_id = 4021
    await create_user(db_connection, user_id, is_approved=0)

    callback = make_callback(user_id=admin_id)
    callback_data = UserAction(action="unblock", user_id=user_id)
    bot = make_bot()

    await handle_user_unblock(callback, callback_data, db_connection, bot)

    cursor = await db_connection.execute(
        "SELECT is_approved FROM users WHERE telegram_id = ?", (user_id,)
    )
    row = await cursor.fetchone()
    assert row["is_approved"] == 1, "Разблокированный пользователь должен иметь is_approved=1"


# ---------------------------------------------------------------------------
# Тест статистики
# ---------------------------------------------------------------------------

async def test_stats_shows_correct_counts(prepared_db, db_connection, admin_id):
    """handle_stats отображает корректные числа пользователей и профилей."""
    from bot.handlers.admin.stats import handle_stats

    # Создаём 2 одобренных и 1 ожидающего
    await create_user(db_connection, 4030, is_approved=1)
    await create_user(db_connection, 4031, is_approved=1)
    await create_user(db_connection, 4032, is_approved=0)
    await create_pending(db_connection, 4032)

    # Один профиль для пользователя 4030
    await create_profile(db_connection, 4030, name="StatsProfile", ip="10.0.0.20", public_key="spk1")

    message = make_message(user_id=admin_id)

    await handle_stats(message, db_connection)

    message.answer.assert_called_once()
    text = message.answer.call_args[0][0]

    # Всего 3 пользователя
    assert "3" in text, "Должно быть указано общее число пользователей (3)"
    # 2 одобренных
    assert "2" in text, "Должно быть указано количество одобренных (2)"
    # 1 ожидает
    assert "1" in text, "Должно быть указано количество ожидающих (1)"


# ---------------------------------------------------------------------------
# Тесты статуса сервера
# ---------------------------------------------------------------------------

async def test_server_status_online(prepared_db, db_connection, admin_id):
    """handle_server при статусе 'online' отображает 🟢 в ответе."""
    from bot.handlers.admin.stats import handle_server

    online_status = {
        "status": "online",
        "interface": "awg0",
        "active_peers_count": 3,
    }

    message = make_message(user_id=admin_id)

    with patch("bot.handlers.admin.stats.VPNService.get_server_status", return_value=online_status):
        await handle_server(message)

    message.answer.assert_called_once()
    text = message.answer.call_args[0][0]
    assert "🟢" in text, "При статусе online должна быть иконка 🟢"
    assert "Работает" in text, "Должно быть слово 'Работает'"


async def test_server_status_offline(prepared_db, db_connection, admin_id):
    """handle_server при статусе 'offline' отображает 🔴 в ответе."""
    from bot.handlers.admin.stats import handle_server

    offline_status = {
        "status": "offline",
        "interface": "awg0",
        "active_peers_count": 0,
        "message": "interface is down",
    }

    message = make_message(user_id=admin_id)

    with patch("bot.handlers.admin.stats.VPNService.get_server_status", return_value=offline_status):
        await handle_server(message)

    message.answer.assert_called_once()
    text = message.answer.call_args[0][0]
    assert "🔴" in text, "При статусе offline должна быть иконка 🔴"
    assert "Остановлен" in text, "Должно быть слово 'Остановлен'"
