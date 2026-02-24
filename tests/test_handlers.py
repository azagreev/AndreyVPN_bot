from typing import Any
from unittest.mock import AsyncMock

import aiosqlite
import pytest

from bot.core.config import settings
from bot.handlers.admin import ApproveCallback, get_admin_keyboard, handle_approve, handle_reject
from bot.handlers.monitoring import cmd_server_status, cmd_stats
from bot.handlers.onboarding import CaptchaStates, cmd_start, process_captcha
from bot.handlers.profiles import (
    ProfileRequestCallback,
    cmd_menu,
    handle_vpn_approve,
    handle_vpn_reject,
    handle_vpn_request,
)
from bot.services.vpn_service import VPNService
from aiogram.fsm.context import FSMContext


# ============================================================================
# Onboarding handlers
# ============================================================================


@pytest.mark.asyncio
async def test_cmd_start_new_user_captcha(
    db_connection: aiosqlite.Connection,
    mock_user: Any,
    make_message: Any,
    fsm_context: FSMContext,
) -> None:
    """New user → captcha question + FSM state set."""
    msg = make_message(mock_user, "/start")
    await cmd_start(msg, db_connection, fsm_context)

    msg.answer.assert_awaited_once()
    text = msg.answer.await_args.args[0]
    assert "+" in text

    state = await fsm_context.get_state()
    assert state == CaptchaStates.waiting_for_answer.state


@pytest.mark.asyncio
async def test_cmd_start_approved_user(
    db_connection: aiosqlite.Connection,
    mock_user: Any,
    make_message: Any,
    fsm_context: FSMContext,
) -> None:
    """Approved user → welcome + main keyboard."""
    await db_connection.execute(
        "INSERT INTO users (telegram_id, username, full_name, is_approved) VALUES (?, ?, ?, 1)",
        (mock_user.id, "testuser", "Test"),
    )
    await db_connection.commit()

    msg = make_message(mock_user, "/start")
    await cmd_start(msg, db_connection, fsm_context)

    msg.answer.assert_awaited_once()
    text = msg.answer.await_args.args[0]
    assert "возвращением" in text.lower() or "активен" in text.lower()
    assert msg.answer.await_args.kwargs.get("reply_markup") is not None


@pytest.mark.asyncio
async def test_cmd_start_pending_user(
    db_connection: aiosqlite.Connection,
    mock_user: Any,
    make_message: Any,
    fsm_context: FSMContext,
) -> None:
    """Pending user → waiting message."""
    await db_connection.execute(
        "INSERT INTO users (telegram_id, username, full_name, is_approved) VALUES (?, ?, ?, 0)",
        (mock_user.id, "testuser", "Test"),
    )
    await db_connection.commit()

    msg = make_message(mock_user, "/start")
    await cmd_start(msg, db_connection, fsm_context)

    msg.answer.assert_awaited_once()
    text = msg.answer.await_args.args[0]
    assert "рассмотрении" in text.lower() or "ожидайте" in text.lower()


@pytest.mark.asyncio
async def test_process_captcha_correct(
    db_connection: aiosqlite.Connection,
    mock_user: Any,
    make_message: Any,
    mock_bot: AsyncMock,
    fsm_context: FSMContext,
) -> None:
    """Correct captcha answer → user registered + admin notified."""
    await fsm_context.update_data(captcha_answer=42)
    await fsm_context.set_state(CaptchaStates.waiting_for_answer)

    msg = make_message(mock_user, "42")
    await process_captcha(msg, db_connection, fsm_context, mock_bot)

    # User should be registered
    async with db_connection.execute(
        "SELECT is_approved FROM users WHERE telegram_id = ?", (mock_user.id,)
    ) as cursor:
        row = await cursor.fetchone()
    assert row is not None
    assert row["is_approved"] == 0

    # State should be cleared
    state = await fsm_context.get_state()
    assert state is None

    # Admin should have been notified
    mock_bot.send_message.assert_awaited_once()
    call_args = mock_bot.send_message.await_args
    assert call_args.args[0] == settings.admin_id


@pytest.mark.asyncio
async def test_process_captcha_wrong(
    db_connection: aiosqlite.Connection,
    mock_user: Any,
    make_message: Any,
    mock_bot: AsyncMock,
    fsm_context: FSMContext,
) -> None:
    """Wrong captcha answer → new question, state kept."""
    await fsm_context.update_data(captcha_answer=42)
    await fsm_context.set_state(CaptchaStates.waiting_for_answer)

    msg = make_message(mock_user, "99")
    await process_captcha(msg, db_connection, fsm_context, mock_bot)

    msg.answer.assert_awaited_once()
    text = msg.answer.await_args.args[0]
    assert "неверно" in text.lower()
    assert "+" in text

    # State should still be set
    state = await fsm_context.get_state()
    assert state == CaptchaStates.waiting_for_answer.state


# ============================================================================
# Admin handlers
# ============================================================================


@pytest.mark.asyncio
async def test_handle_approve(
    db_connection: aiosqlite.Connection,
    admin_user: Any,
    make_callback_query: Any,
    mock_bot: AsyncMock,
) -> None:
    """Approve updates DB and notifies user."""
    user_id = 99999
    await db_connection.execute(
        "INSERT INTO users (telegram_id, username, full_name, is_approved) VALUES (?, ?, ?, 0)",
        (user_id, "pending_user", "Pending"),
    )
    await db_connection.execute(
        "INSERT INTO approvals (user_id, status) VALUES (?, 'pending')",
        (user_id,),
    )
    await db_connection.commit()

    cq = make_callback_query(admin_user)
    callback_data = ApproveCallback(user_id=user_id, action="accept")

    await handle_approve(cq, callback_data, db_connection, mock_bot)

    # Check DB
    async with db_connection.execute(
        "SELECT is_approved FROM users WHERE telegram_id = ?", (user_id,)
    ) as cursor:
        row = await cursor.fetchone()
    assert row["is_approved"] == 1

    async with db_connection.execute(
        "SELECT status FROM approvals WHERE user_id = ?", (user_id,)
    ) as cursor:
        row = await cursor.fetchone()
    assert row["status"] == "approved"

    mock_bot.send_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_reject(
    db_connection: aiosqlite.Connection,
    admin_user: Any,
    make_callback_query: Any,
    mock_bot: AsyncMock,
) -> None:
    """Reject updates approval status and notifies user."""
    user_id = 88888
    await db_connection.execute(
        "INSERT INTO users (telegram_id, username, full_name, is_approved) VALUES (?, ?, ?, 0)",
        (user_id, "pending_user", "Pending"),
    )
    await db_connection.execute(
        "INSERT INTO approvals (user_id, status) VALUES (?, 'pending')",
        (user_id,),
    )
    await db_connection.commit()

    cq = make_callback_query(admin_user)
    callback_data = ApproveCallback(user_id=user_id, action="reject")

    await handle_reject(cq, callback_data, db_connection, mock_bot)

    async with db_connection.execute(
        "SELECT status FROM approvals WHERE user_id = ?", (user_id,)
    ) as cursor:
        row = await cursor.fetchone()
    assert row["status"] == "rejected"

    mock_bot.send_message.assert_awaited_once()


def test_admin_keyboard_buttons() -> None:
    """get_admin_keyboard produces correct callback data."""
    kb = get_admin_keyboard(777)
    buttons = kb.inline_keyboard[0]
    assert len(buttons) == 2
    assert buttons[0].callback_data is not None and "accept" in buttons[0].callback_data
    assert buttons[1].callback_data is not None and "reject" in buttons[1].callback_data


# ============================================================================
# Profiles handlers
# ============================================================================


@pytest.mark.asyncio
async def test_cmd_menu(mock_user: Any, make_message: Any) -> None:
    """cmd_menu sends main keyboard."""
    msg = make_message(mock_user, "/menu")
    await cmd_menu(msg)
    msg.answer.assert_awaited_once()
    assert msg.answer.await_args.kwargs.get("reply_markup") is not None


@pytest.mark.asyncio
async def test_vpn_request_notifies_admin(
    mock_user: Any,
    make_callback_query: Any,
    mock_bot: AsyncMock,
) -> None:
    """VPN request sends notification to admin."""
    cq = make_callback_query(mock_user)
    await handle_vpn_request(cq, mock_bot)

    mock_bot.send_message.assert_awaited_once()
    call_args = mock_bot.send_message.await_args
    assert call_args.args[0] == settings.admin_id


@pytest.mark.asyncio
async def test_vpn_approve_sends_config(
    admin_user: Any,
    make_callback_query: Any,
    mock_bot: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Approve creates profile and sends QR + conf to user."""
    fake_result = {
        "name": "VPN_12345",
        "ipv4": "10.0.0.2",
        "config": "[Interface]\nPrivateKey = test\n",
        "synced": True,
    }
    monkeypatch.setattr(VPNService, "create_profile", AsyncMock(return_value=fake_result))
    monkeypatch.setattr(VPNService, "generate_qr_code", lambda _config: b"\x89PNG_fake")

    cq = make_callback_query(admin_user)
    callback_data = ProfileRequestCallback(user_id=12345, action="approve")

    await handle_vpn_approve(cq, callback_data, mock_bot)

    mock_bot.send_photo.assert_awaited_once()
    mock_bot.send_document.assert_awaited_once()


@pytest.mark.asyncio
async def test_vpn_approve_error_sanitized(
    admin_user: Any,
    make_callback_query: Any,
    mock_bot: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SECURITY: Error message to Telegram does NOT leak internal details."""
    monkeypatch.setattr(
        VPNService,
        "create_profile",
        AsyncMock(side_effect=RuntimeError("secret DB path /etc/secret.db")),
    )

    cq = make_callback_query(admin_user)
    callback_data = ProfileRequestCallback(user_id=12345, action="approve")

    await handle_vpn_approve(cq, callback_data, mock_bot)

    # The message.answer should have been called with a GENERIC error
    cq.message.answer.assert_awaited_once()
    error_text = cq.message.answer.await_args.args[0]
    assert "secret" not in error_text.lower()
    assert "/etc/" not in error_text


@pytest.mark.asyncio
async def test_vpn_reject_notifies_user(
    admin_user: Any,
    make_callback_query: Any,
    mock_bot: AsyncMock,
) -> None:
    """Reject sends notification to user."""
    cq = make_callback_query(admin_user)
    callback_data = ProfileRequestCallback(user_id=12345, action="reject")

    await handle_vpn_reject(cq, callback_data, mock_bot)

    mock_bot.send_message.assert_awaited_once()
    call_args = mock_bot.send_message.await_args
    assert call_args.args[0] == 12345


# ============================================================================
# Monitoring handlers
# ============================================================================


@pytest.mark.asyncio
async def test_stats_no_profiles(
    mock_user: Any,
    make_message: Any,
    db_connection: aiosqlite.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No profiles → 'нет профилей' message."""
    monkeypatch.setattr(VPNService, "get_monthly_usage", AsyncMock(return_value=[]))
    msg = make_message(mock_user, "/stats")
    await cmd_stats(msg, db_connection)

    msg.answer.assert_awaited_once()
    text = msg.answer.await_args.args[0]
    assert "нет" in text.lower()


@pytest.mark.asyncio
async def test_stats_with_profiles(
    mock_user: Any,
    make_message: Any,
    db_connection: aiosqlite.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With profiles → formatted usage output."""
    usage = [
        {"id": 1, "name": "VPN_1", "ip": "10.0.0.2", "monthly_total": 1073741824},
        {"id": 2, "name": "VPN_2", "ip": "10.0.0.3", "monthly_total": 512000},
    ]
    monkeypatch.setattr(VPNService, "get_monthly_usage", AsyncMock(return_value=usage))
    msg = make_message(mock_user, "/stats")
    await cmd_stats(msg, db_connection)

    msg.answer.assert_awaited_once()
    text = msg.answer.await_args.args[0]
    assert "VPN_1" in text
    assert "VPN_2" in text
    assert "GB" in text or "MB" in text


@pytest.mark.asyncio
async def test_server_status_non_admin(
    mock_user: Any,
    make_message: Any,
) -> None:
    """Non-admin user → silently ignored."""
    msg = make_message(mock_user, "/server")
    await cmd_server_status(msg)
    msg.answer.assert_not_awaited()
