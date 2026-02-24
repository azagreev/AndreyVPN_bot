from __future__ import annotations

import sqlite3
from collections.abc import Generator
from pathlib import Path
from typing import Any, Callable, Iterable

Row = sqlite3.Row
Error = sqlite3.Error
IntegrityError = sqlite3.IntegrityError


class Cursor:
    def __init__(self, cursor: sqlite3.Cursor) -> None:
        self._cursor = cursor

    async def __aenter__(self) -> "Cursor":
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        await self.close()

    async def fetchone(self) -> Any:
        return self._cursor.fetchone()

    async def fetchall(self) -> list[Any]:
        return self._cursor.fetchall()

    async def close(self) -> None:
        self._cursor.close()

    def __aiter__(self) -> "Cursor":
        return self

    async def __anext__(self) -> Any:
        row = self._cursor.fetchone()
        if row is None:
            raise StopAsyncIteration
        return row


class _CursorContext:
    def __init__(self, factory: Callable[[], sqlite3.Cursor]) -> None:
        self._factory = factory
        self._cursor: Cursor | None = None

    async def _get_cursor(self) -> Cursor:
        if self._cursor is None:
            self._cursor = Cursor(self._factory())
        return self._cursor

    def __await__(self) -> Generator[Any, None, Cursor]:
        return self._get_cursor().__await__()

    async def __aenter__(self) -> Cursor:
        return await self._get_cursor()

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if self._cursor is not None:
            await self._cursor.close()


class Connection:
    def __init__(self, database: str | Path, **kwargs: Any) -> None:
        self._conn = sqlite3.connect(str(database), **kwargs)

    def __await__(self) -> Generator[Any, None, "Connection"]:
        async def _ready() -> "Connection":
            return self

        return _ready().__await__()

    async def __aenter__(self) -> "Connection":
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        await self.close()

    @property
    def row_factory(self) -> Any:
        return self._conn.row_factory

    @row_factory.setter
    def row_factory(self, value: Any) -> None:
        self._conn.row_factory = value

    @property
    def total_changes(self) -> int:
        return int(self._conn.total_changes)

    def execute(
        self,
        sql: str,
        parameters: Iterable[Any] | None = None,
    ) -> _CursorContext:
        params = tuple(parameters or ())
        return _CursorContext(lambda: self._conn.execute(sql, params))

    def executemany(self, sql: str, parameters: Iterable[Iterable[Any]]) -> _CursorContext:
        return _CursorContext(lambda: self._conn.executemany(sql, parameters))

    def executescript(self, sql_script: str) -> _CursorContext:
        return _CursorContext(lambda: self._conn.executescript(sql_script))

    async def commit(self) -> None:
        self._conn.commit()

    async def rollback(self) -> None:
        self._conn.rollback()

    async def close(self) -> None:
        self._conn.close()


def connect(database: str | Path, **kwargs: Any) -> Connection:
    return Connection(database, **kwargs)
