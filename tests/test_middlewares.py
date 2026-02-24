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
async def test_db_middleware_injects_connection(test_settings: Path) -> None:
    """DbMiddleware must inject an aiosqlite.Connection as data['db']."""
    middleware = DbMiddleware()
    handler = AsyncMock(return_value="ok")
    event = MagicMock()

    result = await middleware(handler, event, {})

    assert result == "ok"
    handler.assert_awaited_once()
    assert handler.await_args is not None
    _, call_data = handler.await_args.args
    assert "db" in call_data
    assert isinstance(call_data["db"], aiosqlite.Connection)


@pytest.mark.asyncio
async def test_db_middleware_closes_connection(test_settings: Path) -> None:
    """Connection is closed after handler returns."""
    middleware = DbMiddleware()
    captured_db: list[aiosqlite.Connection] = []

    async def grab_db(_event: Any, data: dict[str, Any]) -> None:
        captured_db.append(data["db"])

    handler = AsyncMock(side_effect=grab_db)
    await middleware(handler, MagicMock(), {})

    # After the context manager exits the connection should be closed.
    db = captured_db[0]
    import sqlite3
    with pytest.raises(sqlite3.ProgrammingError):
        await db.execute("SELECT 1")


# ---------------------------------------------------------------------------
# AccessControlMiddleware
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_access_passes_admin(
    db_connection: aiosqlite.Connection,
    admin_user: Any,
    make_message: Any,
) -> None:
    """Admin user always passes through regardless of approval status."""
    middleware = AccessControlMiddleware()
    handler = AsyncMock(return_value="ok")
    msg = make_message(admin_user, "/anything")
    data: dict[str, Any] = {"db": db_connection}

    result = await middleware(handler, msg, data)
    assert result == "ok"
    handler.assert_awaited_once()


@pytest.mark.asyncio
async def test_access_passes_start_command(
    db_connection: aiosqlite.Connection,
    mock_user: Any,
    make_message: Any,
) -> None:
    """/start command is always allowed for any user."""
    middleware = AccessControlMiddleware()
    handler = AsyncMock(return_value="ok")
    msg = make_message(mock_user, "/start")
    data: dict[str, Any] = {"db": db_connection}

    result = await middleware(handler, msg, data)
    assert result == "ok"
    handler.assert_awaited_once()


@pytest.mark.asyncio
async def test_access_passes_captcha_state(
    db_connection: aiosqlite.Connection,
    mock_user: Any,
    make_message: Any,
) -> None:
    """User in captcha state must be allowed through."""
    middleware = AccessControlMiddleware()
    handler = AsyncMock(return_value="ok")
    msg = make_message(mock_user, "42")

    state = AsyncMock()
    state.get_state = AsyncMock(return_value="CaptchaStates:waiting_for_answer")
    data: dict[str, Any] = {"db": db_connection, "state": state}

    result = await middleware(handler, msg, data)
    assert result == "ok"
    handler.assert_awaited_once()


@pytest.mark.asyncio
async def test_access_blocks_unapproved_user_message(
    db_connection: aiosqlite.Connection,
    mock_user: Any,
    make_message: Any,
) -> None:
    """Unapproved user sending a regular message is blocked."""
    middleware = AccessControlMiddleware()
    handler = AsyncMock()
    msg = make_message(mock_user, "hello")
    data: dict[str, Any] = {"db": db_connection, "state": None}

    result = await middleware(handler, msg, data)
    assert result is None
    handler.assert_not_awaited()
    msg.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_access_blocks_unapproved_callback_query(
    db_connection: aiosqlite.Connection,
    mock_user: Any,
    make_callback_query: Any,
) -> None:
    """Unapproved user firing a callback is blocked with show_alert."""
    middleware = AccessControlMiddleware()
    handler = AsyncMock()
    cq = make_callback_query(mock_user)
    data: dict[str, Any] = {"db": db_connection, "state": None}

    result = await middleware(handler, cq, data)
    assert result is None
    handler.assert_not_awaited()
    cq.answer.assert_awaited_once()
    call_kwargs = cq.answer.await_args.kwargs
    assert call_kwargs.get("show_alert") is True


@pytest.mark.asyncio
async def test_access_denies_when_db_none(
    mock_user: Any,
    make_message: Any,
    test_settings: Path,
) -> None:
    """SECURITY: When db is None (DbMiddleware didn't run), block the request."""
    middleware = AccessControlMiddleware()
    handler = AsyncMock()
    msg = make_message(mock_user, "hello")
    data: dict[str, Any] = {"state": None}  # No "db" key at all

    result = await middleware(handler, msg, data)
    assert result is None
    handler.assert_not_awaited()
    msg.answer.assert_awaited_once()
    assert "error" in msg.answer.await_args.args[0].lower()
