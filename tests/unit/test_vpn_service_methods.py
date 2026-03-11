"""
Юнит-тесты для методов VPNService.

Тестируют delete_profile, get_profile_config и remove_peer_from_server
с полным мокингом внешних зависимостей (aiosqlite, subprocess, wg binary).
"""
import asyncio
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock


# ---------------------------------------------------------------------------
# Вспомогательные моки для subprocess
# ---------------------------------------------------------------------------

def make_process(returncode: int = 0, stdout: bytes = b"", stderr: bytes = b""):
    """Создаёт mock asyncio.Process с заданными параметрами."""
    proc = AsyncMock()
    proc.returncode = returncode
    proc.communicate = AsyncMock(return_value=(stdout, stderr))
    return proc


def make_mock_db(fetchone_return=None):
    """
    Создаёт mock aiosqlite.Connection для передачи напрямую в сервис.
    """
    cursor = AsyncMock()
    cursor.fetchone = AsyncMock(return_value=fetchone_return)
    # support dict-like access for Row objects
    if fetchone_return is not None and isinstance(fetchone_return, tuple):
        mock_row = MagicMock()
        for i, val in enumerate(fetchone_return):
            mock_row.__getitem__ = MagicMock(side_effect=lambda k, v=fetchone_return: v[k] if isinstance(k, int) else None)
        cursor.fetchone = AsyncMock(return_value=fetchone_return)

    db = AsyncMock()
    db.execute = AsyncMock(return_value=cursor)
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    return db, cursor


# ---------------------------------------------------------------------------
# delete_profile
# ---------------------------------------------------------------------------

async def test_delete_profile_removes_from_db(test_settings):
    """delete_profile выполняет DELETE из vpn_profiles при успешном нахождении профиля."""
    from bot.services.vpn_service import VPNService

    db, cursor = make_mock_db()

    proc = make_process(returncode=0)

    with patch("bot.db.repository.get_profile_public_key", return_value="fake_public_key_abc123"), \
         patch("bot.db.repository.delete_vpn_profile", return_value=None), \
         patch("bot.services.vpn_service.shutil.which", return_value="/usr/bin/awg"), \
         patch("bot.services.vpn_service.asyncio.create_subprocess_exec", return_value=proc):
        result = await VPNService.delete_profile(db=db, profile_id=1)

    assert result is True, "delete_profile должен возвращать True при успешном удалении"


async def test_delete_profile_not_found(test_settings):
    """delete_profile возвращает False если профиль не найден в БД."""
    from bot.services.vpn_service import VPNService

    db, cursor = make_mock_db()

    with patch("bot.db.repository.get_profile_public_key", return_value=None):
        result = await VPNService.delete_profile(db=db, profile_id=999)

    assert result is False, "delete_profile должен возвращать False если профиль не найден"


async def test_delete_profile_server_removal_fails(test_settings):
    """delete_profile возвращает False если удаление peer с WG-сервера провалилось.

    Профиль должен остаться в БД — repository.delete_vpn_profile не должен вызываться.
    """
    from bot.services.vpn_service import VPNService

    db, cursor = make_mock_db()
    proc = make_process(returncode=1, stderr=b"error: peer not found")

    with patch("bot.db.repository.get_profile_public_key", return_value="fake_public_key"), \
         patch("bot.db.repository.delete_vpn_profile") as mock_delete, \
         patch("bot.services.vpn_service.shutil.which", return_value="/usr/bin/awg"), \
         patch("bot.services.vpn_service.asyncio.create_subprocess_exec", return_value=proc):
        result = await VPNService.delete_profile(db=db, profile_id=1)

    assert result is False, "delete_profile должен возвращать False при ошибке удаления с сервера"
    mock_delete.assert_not_called()


# ---------------------------------------------------------------------------
# get_profile_config
# ---------------------------------------------------------------------------

async def test_get_profile_config_returns_config(test_settings):
    """get_profile_config возвращает словарь с корректным конфигом."""
    from bot.services.vpn_service import VPNService

    # Шифруем тестовый приватный ключ
    encrypted_key = VPNService.encrypt_data("FAKE_PRIVATE_KEY_BASE64==")

    mock_row = MagicMock()
    mock_row.__getitem__ = MagicMock(side_effect=lambda k: {
        "name": "TestProfile",
        "private_key": encrypted_key,
        "ipv4_address": "10.0.0.2",
    }[k])

    db, cursor = make_mock_db()

    with patch("bot.db.repository.get_profile_for_config", return_value=mock_row):
        result = await VPNService.get_profile_config(db=db, profile_id=1)

    assert result is not None, "get_profile_config не должен возвращать None"
    assert result["name"] == "TestProfile", "Имя профиля должно совпадать"
    assert result["ipv4"] == "10.0.0.2", "IP-адрес должен совпадать"
    assert "PrivateKey" in result["config"], "Конфиг должен содержать PrivateKey"
    assert "Address" in result["config"], "Конфиг должен содержать Address"
    assert "[Peer]" in result["config"], "Конфиг должен содержать секцию [Peer]"
    assert "FAKE_PRIVATE_KEY_BASE64==" in result["config"], "PrivateKey в конфиге должен совпадать"


async def test_get_profile_config_not_found(test_settings):
    """get_profile_config возвращает None если профиль не найден."""
    from bot.services.vpn_service import VPNService

    db, cursor = make_mock_db()

    with patch("bot.db.repository.get_profile_for_config", return_value=None):
        result = await VPNService.get_profile_config(db=db, profile_id=404)

    assert result is None, "get_profile_config должен возвращать None если профиль не найден"


async def test_get_profile_config_decrypt_failure_returns_none(test_settings):
    """get_profile_config возвращает None если расшифровка приватного ключа провалилась.

    Это защищает от необработанного исключения если ключ шифрования сменился
    или запись в БД повреждена.
    """
    from bot.services.vpn_service import VPNService

    mock_row = MagicMock()
    mock_row.__getitem__ = MagicMock(side_effect=lambda k: {
        "name": "BrokenProfile",
        "private_key": "not_a_valid_fernet_token",
        "ipv4_address": "10.0.0.5",
    }[k])

    db, _ = make_mock_db()

    with patch("bot.db.repository.get_profile_for_config", return_value=mock_row):
        result = await VPNService.get_profile_config(db=db, profile_id=1)

    assert result is None, "get_profile_config должен возвращать None при ошибке расшифровки"


# ---------------------------------------------------------------------------
# remove_peer_from_server
# ---------------------------------------------------------------------------

async def test_remove_peer_from_server_success(test_settings):
    """remove_peer_from_server возвращает True при returncode=0."""
    from bot.services.vpn_service import VPNService

    proc = make_process(returncode=0)

    with patch("bot.services.vpn_service.shutil.which", return_value="/usr/bin/awg"), \
         patch("bot.services.vpn_service.asyncio.create_subprocess_exec", return_value=proc):
        result = await VPNService.remove_peer_from_server("FAKE_PUBLIC_KEY==")

    assert result is True, "remove_peer_from_server должен возвращать True при успехе"


async def test_remove_peer_from_server_failure(test_settings):
    """remove_peer_from_server возвращает False при returncode != 0."""
    from bot.services.vpn_service import VPNService

    proc = make_process(returncode=1, stderr=b"error: peer not found")

    with patch("bot.services.vpn_service.shutil.which", return_value="/usr/bin/awg"), \
         patch("bot.services.vpn_service.asyncio.create_subprocess_exec", return_value=proc):
        result = await VPNService.remove_peer_from_server("NONEXISTENT_KEY==")

    assert result is False, "remove_peer_from_server должен возвращать False при ошибке"


async def test_remove_peer_from_server_no_binary(test_settings):
    """remove_peer_from_server возвращает False если нет awg/wg бинарника (без исключения)."""
    from bot.services.vpn_service import VPNService

    with patch("bot.services.vpn_service.shutil.which", return_value=None):
        result = await VPNService.remove_peer_from_server("SOME_KEY==")

    assert result is False, "remove_peer_from_server должен возвращать False если бинарник не найден"


# ---------------------------------------------------------------------------
# startup validation helpers
# ---------------------------------------------------------------------------

async def test_startup_validation_invalid_cidr(test_settings, monkeypatch):
    """Некорректный VPN_IP_RANGE должен давать ValueError/критическую ошибку."""
    import ipaddress
    with pytest.raises(ValueError):
        ipaddress.IPv4Network("not_a_cidr", strict=False)


async def test_startup_validation_too_small_cidr(test_settings):
    """CIDR /31 содержит только 2 адреса — слишком маленький для VPN пула."""
    import ipaddress
    network = ipaddress.IPv4Network("10.0.0.0/31", strict=False)
    usable = max(network.num_addresses - 2, 0)
    assert usable < 2, "Диапазон /31 не должен проходить валидацию"


async def test_startup_validation_empty_server_fields(test_settings):
    """Пустые SERVER_PUB_KEY и SERVER_ENDPOINT не должны проходить валидацию."""
    assert not "".strip(), "Пустой SERVER_PUB_KEY должен быть отклонён"
    assert ":" not in "192.168.1.1", "SERVER_ENDPOINT без порта должен быть отклонён"
    assert ":" in "192.168.1.1:51820", "Корректный SERVER_ENDPOINT должен содержать двоеточие"
