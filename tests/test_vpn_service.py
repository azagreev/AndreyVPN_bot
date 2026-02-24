import pytest
import ipaddress
from bot.services.vpn_service import VPNService
from bot.core.config import settings

@pytest.mark.asyncio
async def test_encryption_decryption(encryption_key):
    """
    v5: Тест Fernet-шифрования приватных ключей.
    """
    settings.encryption_key = encryption_key
    VPNService._fernet = None
    
    original_text = "private_key_v5_secret"
    encrypted = VPNService.encrypt_data(original_text)
    assert encrypted != original_text
    
    decrypted = VPNService.decrypt_data(encrypted)
    assert decrypted == original_text

@pytest.mark.asyncio
async def test_cidr_pool_management(temp_db):
    """
    v5: Тест управления CIDR пулом (поиск первого свободного IP).
    """
    settings.vpn_ip_range = "10.0.0.0/29"
    settings.db_path = "test_bot_v5.db"
    
    # Сначала база пуста.
    next_ip = await VPNService.get_next_ipv4(temp_db)
    assert next_ip == "10.0.0.2"
    
    # Занимаем .2 и .4
    await temp_db.execute("INSERT INTO vpn_profiles (user_id, name, ipv4_address) VALUES (?, ?, ?)", (1, "p1", "10.0.0.2"))
    await temp_db.execute("INSERT INTO vpn_profiles (user_id, name, ipv4_address) VALUES (?, ?, ?)", (2, "p2", "10.0.0.4"))
    await temp_db.commit()
    
    # Следующий свободный — .3 (дырка)
    next_ip = await VPNService.get_next_ipv4(temp_db)
    assert next_ip == "10.0.0.3"

@pytest.mark.asyncio
async def test_atomic_create_profile(temp_db, mock_subprocess, encryption_key):
    """
    v5: Тест атомарного создания профиля (транзакция + шифрование).
    """
    settings.encryption_key = encryption_key
    settings.db_path = "test_bot_v5.db"
    VPNService._fernet = None
    
    mock_subprocess.return_value.communicate.side_effect = [
        (b"priv_key\n", b""), # genkey
        (b"pub_key\n", b""),  # pubkey
        (b"", b"")            # wg set
    ]
    
    user_id = 555
    profile_name = "v5_user"
    
    result = await VPNService.create_profile(user_id, profile_name)
    
    assert ipaddress.IPv4Address(result["ipv4"]) in ipaddress.IPv4Network(settings.vpn_ip_range)
    assert "priv_key" in result["config"]
    
    async with temp_db.execute("SELECT private_key FROM vpn_profiles WHERE user_id = ?", (user_id,)) as cursor:
        row = await cursor.fetchone()
        assert row["private_key"] != "priv_key"
        assert VPNService.decrypt_data(row["private_key"]) == "priv_key"

@pytest.mark.asyncio
async def test_migration_script(temp_db, encryption_key):
    """
    v5: Тест скрипта миграции существующих данных на Fernet.
    """
    settings.encryption_key = encryption_key
    settings.db_path = "test_bot_v5.db"
    VPNService._fernet = None
    
    open_key = "unencrypted_key_123"
    await temp_db.execute(
        "INSERT INTO vpn_profiles (user_id, name, private_key, public_key, ipv4_address) VALUES (?, ?, ?, ?, ?)",
        (1, "old_profile", open_key, "pub", "10.0.0.2")
    )
    await temp_db.commit()
    
    from scripts.migrate_to_fernet import migrate_to_fernet
    await migrate_to_fernet()
    
    async with temp_db.execute("SELECT private_key FROM vpn_profiles WHERE user_id = 1") as cursor:
        row = await cursor.fetchone()
        encrypted_key = row["private_key"]
        assert encrypted_key != open_key
        assert VPNService.decrypt_data(encrypted_key) == open_key
