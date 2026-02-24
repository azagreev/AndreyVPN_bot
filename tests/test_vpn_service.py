import pytest
from bot.services.vpn_service import VPNService
from bot.core.config import settings

@pytest.mark.asyncio
async def test_encryption_decryption(encryption_key):
    """
    v3: Тест Fernet-шифрования приватных ключей.
    """
    settings.encryption_key = encryption_key
    VPNService._fernet = None # Сброс кэша
    
    original_text = "private_key_top_secret_123"
    encrypted = VPNService.encrypt_data(original_text)
    assert encrypted != original_text
    
    decrypted = VPNService.decrypt_data(encrypted)
    assert decrypted == original_text

@pytest.mark.asyncio
async def test_cidr_pool_management(temp_db):
    """
    v3: Тест управления CIDR пулом (поиск первого свободного IP).
    """
    settings.vpn_ip_range = "10.0.0.0/29" # 10.0.0.1 - 10.0.0.6 доступно
    settings.db_path = "test_bot_data.db"
    
    # Сначала база пуста. Пропускаем .1 (gateway), первый должен быть .2
    next_ip = await VPNService.get_next_ipv4(temp_db)
    assert next_ip == "10.0.0.2"
    
    # Занимаем .2 и .4
    await temp_db.execute("INSERT INTO vpn_profiles (user_id, name, ipv4_address) VALUES (?, ?, ?)", (1, "p1", "10.0.0.2"))
    await temp_db.execute("INSERT INTO vpn_profiles (user_id, name, ipv4_address) VALUES (?, ?, ?)", (2, "p2", "10.0.0.4"))
    await temp_db.commit()
    
    # Следующий свободный должен быть .3 (дырка между .2 и .4)
    next_ip = await VPNService.get_next_ipv4(temp_db)
    assert next_ip == "10.0.0.3"
    
    # Занимаем .3, .5, .6
    await temp_db.execute("INSERT INTO vpn_profiles (user_id, name, ipv4_address) VALUES (?, ?, ?)", (3, "p3", "10.0.0.3"))
    await temp_db.execute("INSERT INTO vpn_profiles (user_id, name, ipv4_address) VALUES (?, ?, ?)", (4, "p4", "10.0.0.5"))
    await temp_db.execute("INSERT INTO vpn_profiles (user_id, name, ipv4_address) VALUES (?, ?, ?)", (5, "p5", "10.0.0.6"))
    await temp_db.commit()
    
    # Пул должен быть исчерпан
    with pytest.raises(ValueError, match="No available IP addresses"):
        await VPNService.get_next_ipv4(temp_db)

@pytest.mark.asyncio
async def test_atomic_create_profile(temp_db, mock_subprocess, encryption_key):
    """
    v3: Тест атомарного создания профиля (транзакция + шифрование).
    """
    settings.encryption_key = encryption_key
    settings.db_path = "test_bot_data.db"
    VPNService._fernet = None
    
    # Мокаем awg
    mock_subprocess.return_value.communicate.side_effect = [
        (b"priv_key\n", b""), # genkey
        (b"pub_key\n", b""),  # pubkey
        (b"", b"")            # wg set
    ]
    
    user_id = 999
    profile_name = "atomic_user"
    
    result = await VPNService.create_profile(user_id, profile_name)
    
    # Проверяем, что IP соответствует текущей сети
    network = ipaddress.IPv4Network(settings.vpn_ip_range)
    assert ipaddress.IPv4Address(result["ipv4"]) in network
    assert "priv_key" in result["config"]
    
    # Проверка шифрования в БД
    async with temp_db.execute("SELECT private_key FROM vpn_profiles WHERE user_id = ?", (user_id,)) as cursor:
        row = await cursor.fetchone()
        assert row["private_key"] != "priv_key"
        assert VPNService.decrypt_data(row["private_key"]) == "priv_key"

@pytest.mark.asyncio
async def test_awg_binary_priority(mock_subprocess):
    """
    v3: Проверка приоритета бинарника awg над wg.
    """
    from unittest.mock import patch
    
    with patch("shutil.which") as mock_which:
        # awg доступен
        mock_which.side_effect = lambda x: "/usr/bin/awg" if x == "awg" else "/usr/bin/wg"
        
        mock_subprocess.return_value.communicate.side_effect = [
            (b"priv\n", b""), 
            (b"pub\n", b"")
        ]
        
        await VPNService.generate_keys()
        
        # Проверяем, что вызывался именно awg
        mock_subprocess.assert_any_call("awg", "genkey", stdout=-1, stderr=-1)
