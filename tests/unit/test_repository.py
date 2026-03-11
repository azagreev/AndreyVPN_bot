"""Unit тесты для слоя репозитория."""
import pytest
import aiosqlite
from pathlib import Path

from bot.db import repository


@pytest.mark.asyncio
async def test_create_and_get_user(db_connection: aiosqlite.Connection) -> None:
    await repository.create_user(db_connection, 12345, "testuser", "Test User")
    user = await repository.get_user(db_connection, 12345)
    assert user is not None
    assert user["telegram_id"] == 12345
    assert user["username"] == "testuser"
    assert user["is_approved"] == 0


@pytest.mark.asyncio
async def test_create_admin_user(db_connection: aiosqlite.Connection) -> None:
    await repository.create_user(db_connection, 999, "admin", "Admin", is_admin=True, is_approved=True)
    user = await repository.get_user(db_connection, 999)
    assert user["is_admin"] == 1
    assert user["is_approved"] == 1


@pytest.mark.asyncio
async def test_set_user_approved(db_connection: aiosqlite.Connection) -> None:
    await repository.create_user(db_connection, 100, "user100", "User 100")
    await repository.set_user_approved(db_connection, 100, True)
    user = await repository.get_user(db_connection, 100)
    assert user["is_approved"] == 1

    await repository.set_user_approved(db_connection, 100, False)
    user = await repository.get_user(db_connection, 100)
    assert user["is_approved"] == 0


@pytest.mark.asyncio
async def test_get_users_page_empty(db_connection: aiosqlite.Connection) -> None:
    rows, total = await repository.get_users_page(db_connection, page=0, page_size=5)
    assert total == 0
    assert rows == []


@pytest.mark.asyncio
async def test_get_users_page_pagination(db_connection: aiosqlite.Connection) -> None:
    for i in range(7):
        await repository.create_user(db_connection, 1000 + i, f"user{i}", f"User {i}")

    rows, total = await repository.get_users_page(db_connection, page=0, page_size=5)
    assert total == 7
    assert len(rows) == 5

    rows2, _ = await repository.get_users_page(db_connection, page=1, page_size=5)
    assert len(rows2) == 2


@pytest.mark.asyncio
async def test_create_approval_and_get_pending(db_connection: aiosqlite.Connection) -> None:
    await repository.create_user(db_connection, 200, "user200", "User 200")
    await repository.create_approval(db_connection, 200)

    rows, total = await repository.get_pending_approvals(db_connection, page=0, page_size=5)
    assert total == 1
    assert rows[0]["user_id"] == 200


@pytest.mark.asyncio
async def test_set_approval_status(db_connection: aiosqlite.Connection) -> None:
    await repository.create_user(db_connection, 300, "user300", "User 300")
    await repository.create_approval(db_connection, 300)

    await repository.set_approval_status(db_connection, 300, "approved", admin_id=999)

    rows, total = await repository.get_pending_approvals(db_connection, page=0, page_size=5)
    assert total == 0


@pytest.mark.asyncio
async def test_count_user_profiles_empty(db_connection: aiosqlite.Connection) -> None:
    await repository.create_user(db_connection, 400, "user400", "User 400")
    count = await repository.count_user_profiles(db_connection, 400)
    assert count == 0


@pytest.mark.asyncio
async def test_insert_and_get_profile(db_connection: aiosqlite.Connection) -> None:
    await repository.create_user(db_connection, 500, "user500", "User 500")
    await repository.insert_vpn_profile(
        db_connection, 500, "VPN_500_1", "encrypted_key", "pubkey123", "10.0.0.2"
    )
    await db_connection.commit()

    profiles = await repository.get_profiles(db_connection, 500)
    assert len(profiles) == 1
    assert profiles[0]["name"] == "VPN_500_1"
    assert profiles[0]["ipv4_address"] == "10.0.0.2"


@pytest.mark.asyncio
async def test_get_profile_owner(db_connection: aiosqlite.Connection) -> None:
    await repository.create_user(db_connection, 600, "user600", "User 600")
    await repository.insert_vpn_profile(
        db_connection, 600, "VPN_600_1", "enc_key", "pubkey600", "10.0.0.3"
    )
    await db_connection.commit()

    profiles = await repository.get_profiles(db_connection, 600)
    profile_id = profiles[0]["id"]

    owner = await repository.get_profile_owner(db_connection, profile_id)
    assert owner == 600

    owner_none = await repository.get_profile_owner(db_connection, 99999)
    assert owner_none is None


@pytest.mark.asyncio
async def test_delete_profile(db_connection: aiosqlite.Connection) -> None:
    await repository.create_user(db_connection, 700, "user700", "User 700")
    await repository.insert_vpn_profile(
        db_connection, 700, "VPN_700_1", "enc_key", "pubkey700", "10.0.0.4"
    )
    await db_connection.commit()

    profiles = await repository.get_profiles(db_connection, 700)
    profile_id = profiles[0]["id"]

    await repository.delete_vpn_profile(db_connection, profile_id)

    profiles_after = await repository.get_profiles(db_connection, 700)
    assert len(profiles_after) == 0


@pytest.mark.asyncio
async def test_get_global_stats(db_connection: aiosqlite.Connection) -> None:
    row = await repository.get_global_stats(db_connection)
    assert row["total_users"] == 0
    assert row["total_profiles"] == 0
    assert row["pending"] == 0


@pytest.mark.asyncio
async def test_schema_version(db_connection: aiosqlite.Connection) -> None:
    version = await repository.get_schema_version(db_connection)
    assert isinstance(version, int)

    await repository.set_schema_version(db_connection, 5)
    version = await repository.get_schema_version(db_connection)
    assert version == 5
