"""Тесты для bot/version.py."""
import re
from pathlib import Path

import pytest

from bot.version import __version__, __schema_version__


def test_version_format():
    assert re.match(r"^\d+\.\d+\.\d+$", __version__), f"Неверный формат: {__version__}"


def test_schema_version_is_int():
    assert isinstance(__schema_version__, int)


def test_schema_version_positive():
    assert __schema_version__ >= 1


def test_schema_version_matches_migration_count():
    migrations_dir = Path(__file__).parent.parent.parent / "bot" / "db" / "migrations"
    count = len(list(migrations_dir.glob("m[0-9]*.py")))
    assert count == __schema_version__, (
        f"Файлов миграций: {count}, __schema_version__: {__schema_version__}"
    )
