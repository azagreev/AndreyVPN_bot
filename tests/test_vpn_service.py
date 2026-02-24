import pytest
from bot.services.vpn_service import VPNService
from bot.core.config import settings

@pytest.mark.asyncio
async def test_v6_encryption(encryption_key):
    settings.encryption_key = encryption_key
    VPNService._fernet = None
    data = "test_key_123"
    encrypted = VPNService.encrypt_data(data)
    assert encrypted != data
    assert VPNService.decrypt_data(encrypted) == data

@pytest.mark.asyncio
async def test_v6_ip_pool_atomic(temp_db):
    settings.vpn_ip_range = "10.0.0.0/29" # .1 to .6
    settings.db_path = "test_bot_v6.db"
    
    # First IP
    ip = await VPNService.get_next_ipv4(temp_db)
    assert ip == "10.0.0.2"
    
    # Fill gaps
    await temp_db.execute("INSERT INTO vpn_profiles (user_id, ipv4_address) VALUES (1, '10.0.0.2')")
    await temp_db.execute("INSERT INTO vpn_profiles (user_id, ipv4_address) VALUES (1, '10.0.0.4')")
    await temp_db.commit()
    
    ip = await VPNService.get_next_ipv4(temp_db)
    assert ip == "10.0.0.3" # Found the gap

@pytest.mark.asyncio
async def test_v6_create_profile_flow(temp_db, mock_subprocess, encryption_key):
    settings.encryption_key = encryption_key
    settings.db_path = "test_bot_v6.db"
    VPNService._fernet = None
    
    mock_subprocess.return_value.communicate.side_effect = [
        (b"priv\n", b""), (b"pub\n", b""), (b"", b"")
    ]
    
    res = await VPNService.create_profile(123, "test_v6")
    assert res["name"] == "test_v6"
    assert "priv" in res["config"]
    
    # Check DB encryption
    async with temp_db.execute("SELECT private_key FROM vpn_profiles WHERE user_id = 123") as cursor:
        row = await cursor.fetchone()
        assert row[0] != "priv"
        assert VPNService.decrypt_data(row[0]) == "priv"

@pytest.mark.asyncio
async def test_v6_update_profile(temp_db):
    settings.db_path = "test_bot_v6.db"
    await temp_db.execute("INSERT INTO vpn_profiles (user_id, name) VALUES (1, 'old')")
    await temp_db.commit()
    
    assert await VPNService.update_profile(1, "new") is True
    async with temp_db.execute("SELECT name FROM vpn_profiles WHERE id = 1") as cursor:
        row = await cursor.fetchone()
        assert row[0] == "new"
