from pathlib import Path

import aiosqlite
import pytest
from pydantic import SecretStr

from bot.core.config import settings
from bot.services.vpn_service import VPNService
from scripts.migrate_to_fernet import migrate_to_fernet


@pytest.mark.asyncio
async def test_migration_encrypts_plaintext_and_keeps_valid_tokens(
    prepared_db: Path,
    monkeypatch: pytest.MonkeyPatch,
    fernet_key: str,
) -> None:
    monkeypatch.setattr(settings, "encryption_key", SecretStr(fernet_key), raising=False)
    VPNService.reset_cache()
    existing_token = VPNService.encrypt_data("already_encrypted")

    async with aiosqlite.connect(prepared_db) as db:
        await db.executemany(
            "INSERT INTO users (telegram_id) VALUES (?)",
            [(301,), (302,)],
        )
        await db.execute(
            """
            INSERT INTO vpn_profiles (user_id, name, private_key, public_key, ipv4_address)
            VALUES (?, ?, ?, ?, ?)
            """,
            (301, "plain_profile", "plain_private_key", "pub_plain", "10.0.0.2"),
        )
        await db.execute(
            """
            INSERT INTO vpn_profiles (user_id, name, private_key, public_key, ipv4_address)
            VALUES (?, ?, ?, ?, ?)
            """,
            (302, "encrypted_profile", existing_token, "pub_enc", "10.0.0.3"),
        )
        await db.commit()

    updated = await migrate_to_fernet()
    assert updated == 1

    async with aiosqlite.connect(prepared_db) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT name, private_key FROM vpn_profiles ORDER BY name",
        ) as cursor:
            rows = list(await cursor.fetchall())

    encrypted_profile = rows[0]
    plain_profile = rows[1]
    assert encrypted_profile["name"] == "encrypted_profile"
    assert encrypted_profile["private_key"] == existing_token
    assert plain_profile["name"] == "plain_profile"
    assert VPNService.looks_like_fernet_token(plain_profile["private_key"])
    assert VPNService.decrypt_data(plain_profile["private_key"]) == "plain_private_key"


@pytest.mark.asyncio
async def test_migration_fails_on_invalid_fernet_like_token(
    prepared_db: Path,
    monkeypatch: pytest.MonkeyPatch,
    fernet_key: str,
) -> None:
    monkeypatch.setattr(settings, "encryption_key", SecretStr(fernet_key), raising=False)
    VPNService.reset_cache()

    async with aiosqlite.connect(prepared_db) as db:
        await db.execute("INSERT INTO users (telegram_id) VALUES (401)")
        await db.execute(
            """
            INSERT INTO vpn_profiles (user_id, name, private_key, public_key, ipv4_address)
            VALUES (?, ?, ?, ?, ?)
            """,
            (401, "broken_profile", "gAAAAAthis_is_not_a_valid_token", "pub_broken", "10.0.0.2"),
        )
        await db.commit()

    with pytest.raises(RuntimeError, match="cannot be decrypted"):
        await migrate_to_fernet()

    async with aiosqlite.connect(prepared_db) as db:
        async with db.execute("SELECT private_key FROM vpn_profiles WHERE user_id = 401") as cursor:
            row = await cursor.fetchone()
    assert row is not None
    assert row[0] == "gAAAAAthis_is_not_a_valid_token"


@pytest.mark.asyncio
async def test_migration_fails_without_encryption_key(
    prepared_db: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "encryption_key", None, raising=False)
    VPNService.reset_cache()
    with pytest.raises(RuntimeError, match="ENCRYPTION_KEY"):
        await migrate_to_fernet()
