import asyncio
from pathlib import Path

import aiosqlite
import pytest
from pydantic import SecretStr
from unittest.mock import AsyncMock

import bot.services.vpn_service as vpn_service_module
from bot.core.config import settings
from bot.services.vpn_service import VPNService


@pytest.mark.asyncio
async def test_fernet_encryption_roundtrip(test_settings: Path) -> None:
    encrypted = VPNService.encrypt_data("test_key_123")
    assert encrypted != "test_key_123"
    assert VPNService.looks_like_fernet_token(encrypted)
    assert VPNService.decrypt_data(encrypted) == "test_key_123"


def test_encryption_fails_when_key_missing(
    monkeypatch: pytest.MonkeyPatch,
    test_settings: Path,
) -> None:
    monkeypatch.setattr(settings, "encryption_key", None, raising=False)
    VPNService.reset_cache()
    with pytest.raises(RuntimeError, match="ENCRYPTION_KEY"):
        VPNService.encrypt_data("private_key")


@pytest.mark.asyncio
async def test_generate_keys_prefers_awg_binary(test_settings: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        vpn_service_module.shutil,
        "which",
        lambda binary: "/usr/bin/awg" if binary == "awg" else "/usr/bin/wg",
    )

    genkey_process = AsyncMock()
    genkey_process.communicate.return_value = (b"private_key\n", b"")
    genkey_process.returncode = 0

    pubkey_process = AsyncMock()
    pubkey_process.communicate.return_value = (b"public_key\n", b"")
    pubkey_process.returncode = 0

    create_process = AsyncMock(side_effect=[genkey_process, pubkey_process])
    monkeypatch.setattr(vpn_service_module.asyncio, "create_subprocess_exec", create_process)

    private_key, public_key = await VPNService.generate_keys()

    assert private_key == "private_key"
    assert public_key == "public_key"
    assert create_process.await_count == 2
    assert create_process.await_args_list[0].args[0] == "/usr/bin/awg"
    assert create_process.await_args_list[1].args[0] == "/usr/bin/awg"


@pytest.mark.asyncio
async def test_generate_keys_fallbacks_to_wg_binary(
    test_settings: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        vpn_service_module.shutil,
        "which",
        lambda binary: None if binary == "awg" else "/usr/bin/wg",
    )

    genkey_process = AsyncMock()
    genkey_process.communicate.return_value = (b"private_key\n", b"")
    genkey_process.returncode = 0

    pubkey_process = AsyncMock()
    pubkey_process.communicate.return_value = (b"public_key\n", b"")
    pubkey_process.returncode = 0

    create_process = AsyncMock(side_effect=[genkey_process, pubkey_process])
    monkeypatch.setattr(vpn_service_module.asyncio, "create_subprocess_exec", create_process)

    await VPNService.generate_keys()

    assert create_process.await_args_list[0].args[0] == "/usr/bin/wg"
    assert create_process.await_args_list[1].args[0] == "/usr/bin/wg"


@pytest.mark.asyncio
async def test_generate_keys_fails_when_binaries_missing(
    test_settings: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(vpn_service_module.shutil, "which", lambda _binary: None)
    with pytest.raises(RuntimeError, match="not installed"):
        await VPNService.generate_keys()


@pytest.mark.asyncio
async def test_cidr_ip_allocation_with_gap(db_connection: aiosqlite.Connection) -> None:
    await db_connection.execute("INSERT INTO users (telegram_id) VALUES (1)")
    await db_connection.execute(
        """
        INSERT INTO vpn_profiles (user_id, name, private_key, public_key, ipv4_address)
        VALUES (?, ?, ?, ?, ?)
        """,
        (1, "p1", VPNService.encrypt_data("k1"), "pub1", "10.0.0.2"),
    )
    await db_connection.execute(
        """
        INSERT INTO vpn_profiles (user_id, name, private_key, public_key, ipv4_address)
        VALUES (?, ?, ?, ?, ?)
        """,
        (1, "p2", VPNService.encrypt_data("k2"), "pub2", "10.0.0.4"),
    )
    await db_connection.commit()

    next_ip = await VPNService.get_next_ipv4(db_connection)
    assert next_ip == "10.0.0.3"


@pytest.mark.asyncio
async def test_cidr_too_small_raises(
    db_connection: aiosqlite.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "vpn_ip_range", "10.0.0.0/31", raising=False)
    with pytest.raises(ValueError, match="too small"):
        await VPNService.get_next_ipv4(db_connection)


@pytest.mark.asyncio
async def test_create_profile_is_atomic_and_encrypts_keys(
    prepared_db: Path,
    monkeypatch: pytest.MonkeyPatch,
    fernet_key: str,
) -> None:
    monkeypatch.setattr(settings, "encryption_key", SecretStr(fernet_key), raising=False)
    VPNService.reset_cache()

    async with aiosqlite.connect(prepared_db) as db:
        await db.executemany(
            "INSERT INTO users (telegram_id) VALUES (?)",
            [(101,), (102,), (103,)],
        )
        await db.commit()

    key_counter = 0

    async def fake_generate_keys(_cls: type[VPNService]) -> tuple[str, str]:
        nonlocal key_counter
        key_counter += 1
        return (f"private_{key_counter}", f"public_{key_counter}")

    async def fake_sync(_cls: type[VPNService], _public_key: str, _ipv4: str) -> bool:
        return True

    monkeypatch.setattr(VPNService, "generate_keys", classmethod(fake_generate_keys))
    monkeypatch.setattr(VPNService, "sync_peer_with_server", classmethod(fake_sync))

    results = await asyncio.gather(
        VPNService.create_profile(101, "profile_101"),
        VPNService.create_profile(102, "profile_102"),
        VPNService.create_profile(103, "profile_103"),
    )
    allocated_ips = {item["ipv4"] for item in results}
    assert allocated_ips == {"10.0.0.2", "10.0.0.3", "10.0.0.4"}

    async with aiosqlite.connect(prepared_db) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT user_id, private_key, ipv4_address
            FROM vpn_profiles
            ORDER BY user_id
            """,
        ) as cursor:
            rows = list(await cursor.fetchall())

    assert len(rows) == 3
    for row in rows:
        stored_key = row["private_key"]
        assert VPNService.looks_like_fernet_token(stored_key)
        assert VPNService.decrypt_data(stored_key).startswith("private_")


@pytest.mark.asyncio
async def test_update_profile(prepared_db: Path) -> None:
    async with aiosqlite.connect(prepared_db) as db:
        await db.execute("INSERT INTO users (telegram_id) VALUES (201)")
        await db.execute(
            """
            INSERT INTO vpn_profiles (user_id, name, private_key, public_key, ipv4_address)
            VALUES (?, ?, ?, ?, ?)
            """,
            (201, "old", VPNService.encrypt_data("old_key"), "pub_old", "10.0.0.2"),
        )
        await db.commit()

    assert await VPNService.update_profile(1, "new") is True

    async with aiosqlite.connect(prepared_db) as db:
        async with db.execute("SELECT name FROM vpn_profiles WHERE id = 1") as cursor:
            row = await cursor.fetchone()
    assert row is not None
    assert row[0] == "new"
