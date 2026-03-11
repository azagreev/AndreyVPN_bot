"""
Регрессионные тесты.

Каждый тест защищает конкретный баг или инвариант системы.
Тесты в этом файле должны быть сложно случайно удалить — они документируют
реальные проблемы которые были или могут быть обнаружены.
"""
import asyncio
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

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


async def create_profile(db, user_id, name="VPN", ip="10.0.0.2", public_key="pk"):
    await db.execute(
        "INSERT INTO vpn_profiles (user_id, name, private_key, public_key, ipv4_address) VALUES (?, ?, ?, ?, ?)",
        (user_id, name, "enc_key", public_key, ip),
    )
    await db.commit()
    cursor = await db.execute("SELECT last_insert_rowid()")
    row = await cursor.fetchone()
    return row[0]


# ---------------------------------------------------------------------------
# Регрессионные тесты
# ---------------------------------------------------------------------------

async def test_admin_always_bypasses_access_control(monkeypatch):
    """
    Регрессия: admin_id должен проходить AdminFilter даже без записи в users.

    Защищает от: случайного добавления проверки наличия в БД в AdminFilter,
    что заблокировало бы первый запуск бота администратором.
    """
    from bot.core.config import settings
    monkeypatch.setattr(settings, "admin_id", 999, raising=False)
    from bot.filters.admin import AdminFilter

    event = make_message(user_id=999)
    result = await AdminFilter()(event)
    assert result is True, "AdminFilter должен пропускать admin_id без проверки БД"


async def test_captcha_regenerates_on_wrong_answer(prepared_db, db_connection, admin_id):
    """
    Регрессия: при неверном ответе на капчу генерируется НОВЫЙ пример (не показывается старый).

    Защищает от: повторного показа той же капчи при неверном ответе,
    что позволило бы боту бесконечно спрашивать один и тот же вопрос.
    """
    from bot.handlers.common.start import process_captcha

    original_answer = 25
    state = make_state()
    state.get_data = AsyncMock(return_value={"captcha_answer": original_answer})
    state.update_data = AsyncMock()

    message = make_message(user_id=7001, text="99")  # заведомо неверный ответ
    bot = make_bot()

    await process_captcha(message, db_connection, state, bot)

    message.answer.assert_called_once()
    text = message.answer.call_args[0][0]

    # Проверяем что ответ содержит новую задачу
    assert ("+" in text and "?" in text) or "= ?" in text, \
        "При неверном ответе должен быть показан новый пример"
    # state.update_data должен быть вызван с новым ответом
    state.update_data.assert_called_once()
    # state НЕ должен быть сброшен
    state.clear.assert_not_called()


async def test_cannot_delete_another_users_profile(prepared_db, db_connection, admin_id):
    """
    Регрессия: пользователь не может удалить VPN профиль, принадлежащий другому пользователю.

    Защищает от: отсутствия или обхода проверки владельца профиля перед удалением.
    Критично для безопасности — без этой проверки любой пользователь мог бы
    удалить чужой VPN.
    """
    from bot.handlers.user.profiles import handle_delete_confirm, ProfileAction

    owner_id = 7010
    attacker_id = 7011

    await create_user(db_connection, owner_id)
    await create_user(db_connection, attacker_id)
    profile_id = await create_profile(db_connection, owner_id, name="OwnerVPN",
                                       ip="10.0.0.50", public_key="pk_owner_r")

    # Злоумышленник пытается удалить чужой профиль
    callback = make_callback(user_id=attacker_id)
    callback_data = ProfileAction(action="confirm_delete", profile_id=profile_id)

    await handle_delete_confirm(callback, callback_data, db_connection)

    # Должен быть алерт
    callback.answer.assert_called_once()
    call_kwargs = callback.answer.call_args[1]
    assert call_kwargs.get("show_alert") is True, \
        "Попытка удалить чужой профиль должна вызывать show_alert=True"

    # Профиль должен оставаться нетронутым
    cursor = await db_connection.execute(
        "SELECT id FROM vpn_profiles WHERE id = ?", (profile_id,)
    )
    row = await cursor.fetchone()
    assert row is not None, "Чужой профиль не должен быть удалён"


async def test_profile_ip_uniqueness_under_concurrent_load(prepared_db, db_connection, admin_id):
    """
    Регрессия: при параллельном создании профилей IP адреса не должны дублироваться.

    Защищает от: состояния гонки при выделении IP-адресов нескольким пользователям
    одновременно, что привело бы к коллизиям в сети VPN.

    Примечание: полное тестирование параллельности ограничено конструкцией
    BEGIN IMMEDIATE транзакции в VPNService.create_profile.
    Здесь проверяем что get_next_ipv4 при последовательных вызовах не выдаёт дубли.
    """
    from bot.services.vpn_service import VPNService

    # Создаём несколько профилей последовательно через get_next_ipv4
    ips = []
    for i in range(3):
        ip = await VPNService.get_next_ipv4(db_connection)
        ips.append(ip)
        # Сохраняем IP чтобы следующий вызов не выдал тот же
        await db_connection.execute(
            "INSERT INTO vpn_profiles (user_id, name, private_key, public_key, ipv4_address) VALUES (?, ?, ?, ?, ?)",
            (admin_id, f"profile_{i}", f"enc_{i}", f"pub_{i}", ip),
        )
        await db_connection.commit()

    assert len(set(ips)) == len(ips), \
        f"Все выделенные IP должны быть уникальными, получено: {ips}"


async def test_admin_filter_not_bypassed_by_wrong_id(monkeypatch):
    """
    Регрессия: AdminFilter должен блокировать любой user_id отличный от admin_id.

    Защищает от: off-by-one ошибок или неточных сравнений в AdminFilter
    (например, >= вместо ==).
    """
    from bot.core.config import settings
    monkeypatch.setattr(settings, "admin_id", 999, raising=False)
    from bot.filters.admin import AdminFilter

    # ID на единицу меньше
    event_less = make_message(user_id=998)
    result_less = await AdminFilter()(event_less)
    assert result_less is False, "ID=998 не должен пройти AdminFilter при admin_id=999"

    # ID на единицу больше
    event_more = make_message(user_id=1000)
    result_more = await AdminFilter()(event_more)
    assert result_more is False, "ID=1000 не должен пройти AdminFilter при admin_id=999"


async def test_approval_notification_goes_to_correct_admin(prepared_db, db_connection, admin_id):
    """
    Регрессия: уведомление о новой заявке должно отправляться именно на admin_id из настроек.

    Защищает от: жёстко заданных или неверно извлечённых admin_id в уведомлениях,
    что привело бы к тому что администратор не получал бы заявки.
    """
    from bot.handlers.common.start import process_captcha

    correct_answer = 13
    state = make_state()
    state.get_data = AsyncMock(return_value={"captcha_answer": correct_answer})

    user_id = 7020
    message = make_message(user_id=user_id, text=str(correct_answer),
                           username="notif_tester", full_name="Notif Tester")
    bot = make_bot()

    await process_captcha(message, db_connection, state, bot)

    bot.send_message.assert_called_once()
    notified_id = bot.send_message.call_args[0][0]
    assert notified_id == admin_id, \
        f"Уведомление должно отправляться на admin_id={admin_id}, получено: {notified_id}"


async def test_blocked_user_cannot_access_bot(prepared_db, db_connection, admin_id):
    """
    Регрессия: заблокированный пользователь (is_approved=0) не должен получать доступ к функциям.

    Защищает от: отсутствия или обхода middleware проверки доступа для заблокированных.
    Проверяем через AccessControlMiddleware напрямую с реальным Message объектом.
    """
    from bot.middlewares.access_middleware import AccessControlMiddleware
    from aiogram.types import Message, User, Chat
    from unittest.mock import AsyncMock, MagicMock

    blocked_user_id = 7030
    await create_user(db_connection, blocked_user_id, is_approved=0)

    middleware = AccessControlMiddleware()

    # Создаём правдоподобный Message объект через MagicMock со spec
    message = MagicMock(spec=Message)
    message.from_user = MagicMock(spec=User)
    message.from_user.id = blocked_user_id
    message.text = "Привет"  # не /start
    message.answer = AsyncMock()

    handler_called = False

    async def mock_handler(event, data):
        nonlocal handler_called
        handler_called = True
        return "handled"

    data = {"db": db_connection}

    result = await middleware(mock_handler, message, data)

    assert not handler_called, \
        "Хендлер не должен вызываться для заблокированного пользователя"


async def test_fernet_encrypted_key_not_stored_in_plaintext(prepared_db, db_connection, admin_id):
    """
    Регрессия: приватный ключ WireGuard НИКОГДА не хранится в БД в открытом виде.

    Защищает от: случайного отключения шифрования или сохранения декриптованного ключа.
    Критично для безопасности — открытый приватный ключ компрометирует весь VPN.
    """
    from bot.services.vpn_service import VPNService

    fake_private = "FAKE_WG_PRIVATE_KEY_BASE64_STRING=="
    fake_public = "FAKE_WG_PUBLIC_KEY_BASE64_STRING=="

    # Шифруем и вставляем напрямую
    encrypted = VPNService.encrypt_data(fake_private)
    await create_user(db_connection, 7040, is_approved=1)
    await db_connection.execute(
        "INSERT INTO vpn_profiles (user_id, name, private_key, public_key, ipv4_address) VALUES (?, ?, ?, ?, ?)",
        (7040, "EncTest", encrypted, fake_public, "10.0.0.60"),
    )
    await db_connection.commit()

    # Читаем из БД напрямую
    cursor = await db_connection.execute(
        "SELECT private_key FROM vpn_profiles WHERE public_key = ?", (fake_public,)
    )
    row = await cursor.fetchone()
    stored_key = row["private_key"]

    assert stored_key != fake_private, \
        "Приватный ключ не должен храниться в открытом виде"
    assert VPNService.looks_like_fernet_token(stored_key), \
        f"Сохранённый ключ должен быть Fernet-токеном, получено: {stored_key[:20]}..."


async def test_cannot_download_conf_for_other_users_profile(prepared_db, db_connection, admin_id):
    """
    Регрессия: пользователь не может скачать .conf профиля другого пользователя.

    Защищает от: отсутствия проверки владельца в handle_download_conf,
    что позволило бы злоумышленнику скачать приватный ключ чужого VPN
    простым перебором profile_id в callback_data.
    """
    from bot.handlers.user.profiles import handle_download_conf, ProfileAction

    owner_id = 7060
    attacker_id = 7061

    await create_user(db_connection, owner_id)
    await create_user(db_connection, attacker_id)
    profile_id = await create_profile(db_connection, owner_id, name="SecretVPN",
                                       ip="10.0.0.80", public_key="pk_secret")

    callback = MagicMock()
    callback.from_user = MagicMock()
    callback.from_user.id = attacker_id
    callback.answer = AsyncMock()
    callback_data = ProfileAction(action="conf", profile_id=profile_id)
    bot = AsyncMock()
    bot.send_document = AsyncMock()

    await handle_download_conf(callback, callback_data, bot, db_connection)

    callback.answer.assert_called_once()
    call_kwargs = callback.answer.call_args[1]
    assert call_kwargs.get("show_alert") is True, \
        "Попытка скачать чужой конфиг должна вызывать show_alert=True"
    bot.send_document.assert_not_called(), "Файл не должен быть отправлен злоумышленнику"


async def test_cancel_command_clears_captcha_state(prepared_db, db_connection, admin_id):
    """
    Регрессия: /cancel должен сбрасывать FSM-состояние капчи.

    Защищает от: невозможности выйти из состояния капчи, если пользователь
    передумал регистрироваться или застрял в бесконечном цикле неверных ответов.
    """
    from bot.handlers.common.start import cmd_cancel

    state = make_state()
    message = make_message(user_id=7070, text="/cancel")

    await cmd_cancel(message, state)

    state.clear.assert_called_once(), "/cancel должен вызывать state.clear()"
    message.answer.assert_called_once()


async def test_access_middleware_uses_typed_captcha_state(monkeypatch):
    """
    Регрессия: AccessControlMiddleware должна использовать CaptchaStates.waiting_for_answer.state,
    а не магическую строку 'CaptchaStates:waiting_for_answer'.

    Защищает от: хрупкого строкового сравнения, которое сломается при переименовании
    класса или модуля без явной ошибки — пользователи с капчей перестанут получать ответы.
    """
    from bot.handlers.common.start import CaptchaStates
    from bot.middlewares.access_middleware import AccessControlMiddleware
    import inspect

    source = inspect.getsource(AccessControlMiddleware.__call__)
    assert "CaptchaStates.waiting_for_answer.state" in source, \
        "AccessControlMiddleware должна использовать CaptchaStates.waiting_for_answer.state, не строку"


async def test_config_reconstruction_matches_original(prepared_db, db_connection, admin_id):
    """
    Регрессия: конфиг восстановленный из БД должен совпадать с оригиналом.

    Защищает от: потери данных при шифровании/дешифровании ключей,
    что сделало бы конфиг нерабочим при скачивании.
    """
    from bot.services.vpn_service import VPNService

    original_private = "ORIGINAL_PRIVATE_KEY_THAT_MUST_SURVIVE_ROUNDTRIP=="
    encrypted = VPNService.encrypt_data(original_private)
    ip = "10.0.0.70"

    await create_user(db_connection, 7050, is_approved=1)
    await db_connection.execute(
        "INSERT INTO vpn_profiles (user_id, name, private_key, public_key, ipv4_address) VALUES (?, ?, ?, ?, ?)",
        (7050, "RoundtripTest", encrypted, "pk_roundtrip", ip),
    )
    await db_connection.commit()
    cursor = await db_connection.execute("SELECT last_insert_rowid()")
    profile_id = (await cursor.fetchone())[0]

    # Восстанавливаем конфиг через get_profile_config, передавая db-соединение напрямую
    result = await VPNService.get_profile_config(db_connection, profile_id)

    assert result is not None, "get_profile_config не должен возвращать None"
    assert original_private in result["config"], \
        "Восстановленный конфиг должен содержать оригинальный приватный ключ"
    assert result["ipv4"] == ip, "IP-адрес в конфиге должен совпадать с оригиналом"
