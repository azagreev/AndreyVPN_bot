import pytest
import ipaddress
import aiosqlite
from bot.services.vpn_service import VPNService
from bot.core.config import settings

@pytest.mark.asyncio
async def test_encryption_decryption(encryption_key):
    """
    Тест шифрования и дешифрования приватных ключей.
    """
    settings.encryption_key = encryption_key
    # Сбрасываем кэшированный Fernet
    VPNService._fernet = None
    
    original_text = "test_private_key_123"
    encrypted = VPNService.encrypt_data(original_text)
    assert encrypted != original_text
    
    decrypted = VPNService.decrypt_data(encrypted)
    assert decrypted == original_text

@pytest.mark.asyncio
async def test_ip_pool_refactor(temp_db):
    """
    Тест рефакторинга IP пула (использование ipaddress).
    """
    settings.vpn_ip_range = "10.0.0.0/24"
    settings.db_path = "test_bot_data.db"
    
    # Сначала проверяем на пустой базе
    next_ip = await VPNService.get_next_ipv4()
    assert next_ip == "10.0.0.2"
    
    # Добавляем запись в базу
    await temp_db.execute(
        "INSERT INTO vpn_profiles (user_id, name, ipv4_address) VALUES (?, ?, ?)",
        (1, "test", "10.0.0.2")
    )
    await temp_db.commit()
    
    # Проверяем следующий IP
    next_ip = await VPNService.get_next_ipv4()
    assert next_ip == "10.0.0.3"

@pytest.mark.asyncio
async def test_generate_keys_binary_check(mock_subprocess):
    """
    Тест генерации ключей и проверки бинарника.
    """
    import shutil
    from unittest.mock import patch
    
    with patch("shutil.which") as mock_which:
        mock_which.side_effect = lambda x: "/usr/bin/awg" if x == "awg" else None
        
        mock_subprocess.return_value.communicate.side_effect = [
            (b"private_key_output\n", b""), 
            (b"public_key_output\n", b"")
        ]
        
        priv, pub = await VPNService.generate_keys()
        assert priv == "private_key_output"
        assert pub == "public_key_output"

@pytest.mark.asyncio
async def test_create_profile_flow(temp_db, mock_subprocess, encryption_key):
    """
    Тест полного цикла создания профиля с шифрованием.
    """
    settings.encryption_key = encryption_key
    settings.db_path = "test_bot_data.db"
    VPNService._fernet = None
    
    mock_subprocess.return_value.communicate.side_effect = [
        (b"priv_key\n", b""), # genkey
        (b"pub_key\n", b""),  # pubkey
        (b"", b"")            # wg set
    ]
    
    user_id = 12345
    profile_name = "test_user"
    
    result = await VPNService.create_profile(user_id, profile_name)
    assert result["name"] == profile_name
    assert "priv_key" in result["config"]
    
    async with temp_db.execute("SELECT private_key FROM vpn_profiles WHERE user_id = ?", (user_id,)) as cursor:
        row = await cursor.fetchone()
        encrypted_in_db = row["private_key"]
        assert encrypted_in_db != "priv_key"
        assert VPNService.decrypt_data(encrypted_in_db) == "priv_key"
