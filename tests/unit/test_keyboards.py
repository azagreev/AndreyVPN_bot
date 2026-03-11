"""
Юнит-тесты для функций построения клавиатур.

Проверяют структуру возвращаемых InlineKeyboardMarkup / ReplyKeyboardMarkup
без обращения к базе данных или Telegram API.
"""
import pytest
from aiogram.types import ReplyKeyboardMarkup, InlineKeyboardMarkup

from bot.keyboards.user import get_user_keyboard, BTN_PROFILES, BTN_TRAFFIC, BTN_STATUS, BTN_HELP
from bot.keyboards.admin import get_admin_keyboard, BTN_USERS, BTN_APPROVALS, BTN_STATS, BTN_SERVER


def test_user_keyboard_structure():
    kb = get_user_keyboard()
    flat = [btn.text for row in kb.keyboard for btn in row]
    assert BTN_PROFILES in flat
    assert BTN_TRAFFIC in flat
    assert BTN_STATUS in flat
    assert BTN_HELP in flat


def test_admin_keyboard_structure():
    kb = get_admin_keyboard()
    flat = [btn.text for row in kb.keyboard for btn in row]
    assert BTN_USERS in flat
    assert BTN_APPROVALS in flat
    assert BTN_STATS in flat
    assert BTN_SERVER in flat


def test_user_keyboard_resize():
    kb = get_user_keyboard()
    assert kb.resize_keyboard is True


def test_admin_keyboard_resize():
    kb = get_admin_keyboard()
    assert kb.resize_keyboard is True


# ---------------------------------------------------------------------------
# User keyboard
# ---------------------------------------------------------------------------

def test_get_user_keyboard_structure():
    """Пользовательская клавиатура содержит 2 ряда по 2 кнопки в каждом."""
    from bot.handlers.user.menu import get_user_keyboard, BTN_PROFILES, BTN_TRAFFIC, BTN_STATUS, BTN_HELP

    kb = get_user_keyboard()
    assert isinstance(kb, ReplyKeyboardMarkup), "Должна возвращаться ReplyKeyboardMarkup"
    assert len(kb.keyboard) == 2, "Должно быть 2 ряда кнопок"
    assert len(kb.keyboard[0]) == 2, "Первый ряд должен содержать 2 кнопки"
    assert len(kb.keyboard[1]) == 2, "Второй ряд должен содержать 2 кнопки"

    all_texts = [btn.text for row in kb.keyboard for btn in row]
    assert BTN_PROFILES in all_texts, "Должна быть кнопка профилей"
    assert BTN_TRAFFIC in all_texts, "Должна быть кнопка трафика"
    assert BTN_STATUS in all_texts, "Должна быть кнопка статуса"
    assert BTN_HELP in all_texts, "Должна быть кнопка помощи"


# ---------------------------------------------------------------------------
# Admin keyboard
# ---------------------------------------------------------------------------

def test_get_admin_keyboard_structure():
    """Административная клавиатура содержит 2 ряда по 2 кнопки в каждом."""
    from bot.handlers.admin.menu import get_admin_keyboard, BTN_USERS, BTN_APPROVALS, BTN_STATS, BTN_SERVER

    kb = get_admin_keyboard()
    assert isinstance(kb, ReplyKeyboardMarkup), "Должна возвращаться ReplyKeyboardMarkup"
    assert len(kb.keyboard) == 2, "Должно быть 2 ряда кнопок"
    assert len(kb.keyboard[0]) == 2, "Первый ряд должен содержать 2 кнопки"
    assert len(kb.keyboard[1]) == 2, "Второй ряд должен содержать 2 кнопки"

    all_texts = [btn.text for row in kb.keyboard for btn in row]
    assert BTN_USERS in all_texts, "Должна быть кнопка пользователей"
    assert BTN_APPROVALS in all_texts, "Должна быть кнопка заявок"
    assert BTN_STATS in all_texts, "Должна быть кнопка статистики"
    assert BTN_SERVER in all_texts, "Должна быть кнопка сервера"


# ---------------------------------------------------------------------------
# Profiles keyboards
# ---------------------------------------------------------------------------

def test_profiles_keyboard_empty_list():
    """При пустом списке профилей клавиатура содержит только кнопку 'Запросить'."""
    from bot.handlers.user.profiles import profiles_keyboard

    kb = profiles_keyboard([])
    assert isinstance(kb, InlineKeyboardMarkup), "Должна возвращаться InlineKeyboardMarkup"

    # Единственный ряд — кнопка запроса
    assert len(kb.inline_keyboard) == 1, "Должен быть 1 ряд (только кнопка Запросить)"
    request_btn = kb.inline_keyboard[0][0]
    assert "Запросить" in request_btn.text, "Кнопка должна содержать текст 'Запросить'"


def test_profiles_keyboard_with_profiles():
    """Для каждого профиля отображаются 2 ряда: заголовок и кнопки действий."""
    from bot.handlers.user.profiles import profiles_keyboard

    profiles = [
        {"id": 1, "name": "Profile_1", "ipv4_address": "10.0.0.2"},
        {"id": 2, "name": "Profile_2", "ipv4_address": "10.0.0.3"},
    ]
    kb = profiles_keyboard(profiles)

    # 2 профиля × 2 ряда + 1 ряд "Запросить" = 5 рядов
    assert len(kb.inline_keyboard) == 5, "Ожидается 5 рядов: 2×(заголовок + кнопки) + Запросить"

    # Первый ряд — заголовок профиля
    assert "Profile_1" in kb.inline_keyboard[0][0].text
    # Второй ряд — кнопки .conf, QR, Удалить
    action_texts = [btn.text for btn in kb.inline_keyboard[1]]
    assert any("conf" in t.lower() or ".conf" in t for t in action_texts), "Должна быть кнопка .conf"
    assert any("QR" in t or "qr" in t.lower() for t in action_texts), "Должна быть кнопка QR"
    assert any("Удалить" in t for t in action_texts), "Должна быть кнопка Удалить"


def test_confirm_delete_keyboard():
    """Клавиатура подтверждения удаления содержит кнопки confirm_delete и cancel_delete."""
    from bot.handlers.user.profiles import confirm_delete_keyboard, ProfileAction

    kb = confirm_delete_keyboard(profile_id=42)
    assert isinstance(kb, InlineKeyboardMarkup)
    assert len(kb.inline_keyboard) == 1, "Должен быть 1 ряд"
    assert len(kb.inline_keyboard[0]) == 2, "Должно быть 2 кнопки"

    btn_texts = [btn.text for btn in kb.inline_keyboard[0]]
    assert any("Да" in t or "удалить" in t.lower() for t in btn_texts), "Кнопка подтверждения должна содержать 'Да'"
    assert any("Отмена" in t or "Отменить" in t for t in btn_texts), "Кнопка отмены должна содержать 'Отмена'"

    # Проверяем что callback_data содержат правильные action
    btn_data = [btn.callback_data for btn in kb.inline_keyboard[0]]
    assert any("confirm_delete" in (d or "") for d in btn_data), "Должна быть кнопка confirm_delete"
    assert any("cancel_delete" in (d or "") for d in btn_data), "Должна быть кнопка cancel_delete"


# ---------------------------------------------------------------------------
# Approval keyboards
# ---------------------------------------------------------------------------

def test_get_approval_keyboard():
    """Клавиатура одобрения содержит 2 кнопки: approve и reject."""
    from bot.handlers.admin.approvals import get_approval_keyboard

    kb = get_approval_keyboard(user_id=123)
    assert isinstance(kb, InlineKeyboardMarkup)
    assert len(kb.inline_keyboard) == 1, "Должен быть 1 ряд"
    assert len(kb.inline_keyboard[0]) == 2, "Должно быть 2 кнопки"

    btn_data = [btn.callback_data for btn in kb.inline_keyboard[0]]
    assert any("approve" in (d or "") for d in btn_data), "Должна быть кнопка approve"
    assert any("reject" in (d or "") for d in btn_data), "Должна быть кнопка reject"


def test_pending_list_keyboard_no_pagination():
    """При 1 пользователе нет кнопок навигации — только страница 1/1."""
    from bot.handlers.admin.approvals import pending_list_keyboard

    users = [{"user_id": 1, "full_name": "Test User", "username": "testuser"}]
    kb = pending_list_keyboard(users, page=0, total=1)

    # Кнопки: заголовок пользователя + approve/reject + навигация
    all_buttons = [btn for row in kb.inline_keyboard for btn in row]
    nav_texts = [b.text for b in all_buttons if "/" in b.text]

    assert len(nav_texts) == 1, "Должна быть только кнопка страницы (1/1)"
    assert nav_texts[0] == "1/1", "Текст страницы должен быть '1/1'"

    # Нет кнопок ◀️ ▶️
    arrow_texts = [b.text for b in all_buttons if "◀" in b.text or "▶" in b.text]
    assert len(arrow_texts) == 0, "Не должно быть кнопок навигации при 1 пользователе"


def test_pending_list_keyboard_with_pagination():
    """При большом количестве пользователей появляются кнопки ◀️ и ▶️."""
    from bot.handlers.admin.approvals import pending_list_keyboard, PAGE_SIZE

    # Создаём PAGE_SIZE+2 пользователей, показываем страницу 1 (не первую и не последнюю)
    total = PAGE_SIZE * 2 + 1
    page = 1
    users_on_page = [
        {"user_id": i, "full_name": f"User {i}", "username": None}
        for i in range(PAGE_SIZE)
    ]
    kb = pending_list_keyboard(users_on_page, page=page, total=total)

    all_buttons = [btn for row in kb.inline_keyboard for btn in row]
    arrow_texts = [b.text for b in all_buttons if "◀" in b.text or "▶" in b.text]
    assert len(arrow_texts) == 2, "При средней странице должны быть обе кнопки навигации"


# ---------------------------------------------------------------------------
# Users list / detail keyboards
# ---------------------------------------------------------------------------

def test_users_list_keyboard_approved_marker():
    """Одобренные пользователи отображаются с ✅, неодобренные — с ❌."""
    from bot.handlers.admin.users import users_list_keyboard

    users = [
        {"telegram_id": 1, "full_name": "Approved User", "is_approved": 1},
        {"telegram_id": 2, "full_name": "Blocked User", "is_approved": 0},
    ]
    kb = users_list_keyboard(users, page=0, total=2)

    all_buttons = [btn for row in kb.inline_keyboard for btn in row]
    user_btns = [b for b in all_buttons if "User" in b.text]

    approved_btn = next((b for b in user_btns if "Approved User" in b.text), None)
    blocked_btn = next((b for b in user_btns if "Blocked User" in b.text), None)

    assert approved_btn is not None, "Кнопка одобренного пользователя должна существовать"
    assert blocked_btn is not None, "Кнопка заблокированного пользователя должна существовать"
    assert "✅" in approved_btn.text, "Одобренный должен иметь ✅"
    assert "❌" in blocked_btn.text, "Заблокированный должен иметь ❌"


def test_user_detail_keyboard_approved():
    """Для одобренного пользователя отображаются кнопки 'Выдать VPN' и 'Заблокировать'."""
    from bot.handlers.admin.users import user_detail_keyboard

    kb = user_detail_keyboard(user_id=123, is_approved=True, page=0)
    all_buttons = [btn for row in kb.inline_keyboard for btn in row]
    texts = [b.text for b in all_buttons]

    assert any("VPN" in t for t in texts), "Должна быть кнопка 'Выдать VPN'"
    assert any("Заблокировать" in t or "Блокировать" in t for t in texts), "Должна быть кнопка блокировки"
    assert not any("Разблокировать" in t for t in texts), "Не должно быть кнопки разблокировки"


def test_user_detail_keyboard_blocked():
    """Для заблокированного пользователя отображается только кнопка 'Разблокировать'."""
    from bot.handlers.admin.users import user_detail_keyboard

    kb = user_detail_keyboard(user_id=123, is_approved=False, page=0)
    all_buttons = [btn for row in kb.inline_keyboard for btn in row]
    texts = [b.text for b in all_buttons]

    assert any("Разблокировать" in t for t in texts), "Должна быть кнопка 'Разблокировать'"
    assert not any("Заблокировать" in t for t in texts), "Не должно быть кнопки блокировки"
    assert not any("VPN" in t for t in texts), "Не должно быть кнопки 'Выдать VPN'"
