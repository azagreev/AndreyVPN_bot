from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import aiosqlite
import pytest

from bot.middlewares.access_middleware import AccessControlMiddleware
from bot.middlewares.db_middleware import DbMiddleware


# ---------------------------------------------------------------------------
# DbMiddleware
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_db_middleware_injects_connection() -> None:
    """DbMiddleware должен внедрять переданное соединение в data['db']."""
    mock_db = MagicMock(spec=aiosqlite.Connection)
    middleware = DbMiddleware(mock_db)
    handler = AsyncMock(return_value="ok")
    event = MagicMock()

    result = await middleware(handler, event, {})

    assert result == "ok"
    handler.assert_awaited_once()
    _, call_data = handler.await_args.args
    assert "db" in call_data
    assert call_data["db"] is mock_db


@pytest.mark.asyncio
async def test_db_middleware_passes_existing_data() -> None:
    """DbMiddleware не перезаписывает другие ключи в data."""
    mock_db = MagicMock(spec=aiosqlite.Connection)
    middleware = DbMiddleware(mock_db)
    handler = AsyncMock(return_value="ok")
    event = MagicMock()
    initial_data = {"state": "some_state", "user": "some_user"}

    await middleware(handler, event, initial_data)

    _, call_data = handler.await_args.args
    assert call_data["state"] == "some_state"
    assert call_data["user"] == "some_user"
    assert call_data["db"] is mock_db


# ---------------------------------------------------------------------------
# AccessControlMiddleware
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_access_passes_admin(
    db_connection: aiosqlite.Connection,
    admin_id: int,
    mock_message: Any,
) -> None:
    """Администратор всегда пропускается вне зависимости от is_approved."""
    middleware = AccessControlMiddleware()
    handler = AsyncMock(return_value="ok")
    msg = mock_message(admin_id, "/anything")
    data: dict[str, Any] = {"db": db_connection}

    result = await middleware(handler, msg, data)
    assert result == "ok"
    handler.assert_awaited_once()


@pytest.mark.asyncio
async def test_access_passes_start_command(
    db_connection: aiosqlite.Connection,
    mock_message: Any,
) -> None:
    """/start разрешён для любого пользователя."""
    middleware = AccessControlMiddleware()
    handler = AsyncMock(return_value="ok")
    msg = mock_message(42000, "/start")
    data: dict[str, Any] = {"db": db_connection}

    result = await middleware(handler, msg, data)
    assert result == "ok"
    handler.assert_awaited_once()


@pytest.mark.asyncio
async def test_access_passes_captcha_state(
    db_connection: aiosqlite.Connection,
    mock_message: Any,
) -> None:
    """Пользователь в состоянии капчи пропускается."""
    middleware = AccessControlMiddleware()
    handler = AsyncMock(return_value="ok")
    msg = mock_message(42001, "42")

    state = AsyncMock()
    state.get_state = AsyncMock(return_value="CaptchaStates:waiting_for_answer")
    data: dict[str, Any] = {"db": db_connection, "state": state}

    result = await middleware(handler, msg, data)
    assert result == "ok"
    handler.assert_awaited_once()


@pytest.mark.asyncio
async def test_access_blocks_unapproved_user_message(
    db_connection: aiosqlite.Connection,
    mock_message: Any,
) -> None:
    """Неодобренный пользователь с обычным сообщением получает отказ."""
    middleware = AccessControlMiddleware()
    handler = AsyncMock()
    msg = mock_message(42002, "hello")
    data: dict[str, Any] = {"db": db_connection, "state": None}

    result = await middleware(handler, msg, data)
    assert result is None
    handler.assert_not_awaited()
    msg.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_access_blocks_unapproved_callback_query(
    db_connection: aiosqlite.Connection,
    mock_callback: Any,
) -> None:
    """Неодобренный пользователь с callback получает show_alert."""
    middleware = AccessControlMiddleware()
    handler = AsyncMock()
    cq = mock_callback(42003, "some_data")
    data: dict[str, Any] = {"db": db_connection, "state": None}

    result = await middleware(handler, cq, data)
    assert result is None
    handler.assert_not_awaited()
    cq.answer.assert_awaited_once()
    call_kwargs = cq.answer.await_args.kwargs
    assert call_kwargs.get("show_alert") is True


@pytest.mark.asyncio
async def test_access_passes_approved_user(
    db_connection: aiosqlite.Connection,
    mock_message: Any,
) -> None:
    """Одобренный пользователь пропускается."""
    from bot.db import repository
    user_id = 42004
    await repository.create_user(db_connection, user_id, "testuser", "Test User")
    await repository.set_user_approved(db_connection, user_id, True)
    await db_connection.commit()

    middleware = AccessControlMiddleware()
    handler = AsyncMock(return_value="ok")
    msg = mock_message(user_id, "hello")
    data: dict[str, Any] = {"db": db_connection, "state": None}

    result = await middleware(handler, msg, data)
    assert result == "ok"
    handler.assert_awaited_once()
