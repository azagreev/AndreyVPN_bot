from pathlib import Path
from unittest.mock import AsyncMock

import aiosqlite
import pytest

import bot.services.vpn_service as vpn_service_module
from bot.core.config import settings
from bot.services.vpn_service import VPNService


# ============================================================================
# format_bytes
# ============================================================================


def test_format_bytes_zero() -> None:
    assert VPNService.format_bytes(0) == "0 B"


def test_format_bytes_bytes_range() -> None:
    assert VPNService.format_bytes(512) == "512 B"


def test_format_bytes_kilobytes() -> None:
    assert VPNService.format_bytes(1536) == "1.50 KB"


def test_format_bytes_gigabytes() -> None:
    assert VPNService.format_bytes(1073741824) == "1.00 GB"


def test_format_bytes_negative_clamped() -> None:
    assert VPNService.format_bytes(-100) == "0 B"


# ============================================================================
# Encryption edge cases
# ============================================================================


@pytest.mark.asyncio
async def test_encrypt_empty_raises(test_settings: Path) -> None:
    with pytest.raises(ValueError, match="empty"):
        VPNService.encrypt_data("")


@pytest.mark.asyncio
async def test_decrypt_empty_raises(test_settings: Path) -> None:
    with pytest.raises(ValueError, match="empty"):
        VPNService.decrypt_data("")


@pytest.mark.asyncio
async def test_decrypt_invalid_token_raises(test_settings: Path) -> None:
    with pytest.raises(ValueError, match="Invalid|mismatch"):
        VPNService.decrypt_data("not_a_real_token_at_all")


# ============================================================================
# Config generation
# ============================================================================


def test_config_content_structure(test_settings: Path) -> None:
    config = VPNService.generate_config_content("test_privkey", "10.0.0.2")

    assert "[Interface]" in config
    assert "[Peer]" in config
    assert "PrivateKey = test_privkey" in config
    assert "Address = 10.0.0.2/32" in config
    assert settings.server_pub_key in config
    assert settings.server_endpoint in config
    # AmneziaWG parameters
    assert f"Jc = {settings.jc}" in config
    assert f"Jmin = {settings.jmin}" in config
    assert f"S1 = {settings.s1}" in config
    assert f"H1 = {settings.h1}" in config


# ============================================================================
# QR code
# ============================================================================


def test_qr_code_png_bytes() -> None:
    data = VPNService.generate_qr_code("test config content")
    assert data[:4] == b"\x89PNG"
    assert len(data) > 100


# ============================================================================
# IP pool exhaustion
# ============================================================================


@pytest.mark.asyncio
async def test_ip_pool_exhaustion(db_connection: aiosqlite.Connection) -> None:
    """With /29 (5 client slots: .2-.6), filling all raises ValueError."""
    await db_connection.execute("INSERT INTO users (telegram_id) VALUES (1)")
    for i, ip_suffix in enumerate(["10.0.0.2", "10.0.0.3", "10.0.0.4", "10.0.0.5", "10.0.0.6"]):
        await db_connection.execute(
            "INSERT INTO vpn_profiles (user_id, name, private_key, public_key, ipv4_address) "
            "VALUES (?, ?, ?, ?, ?)",
            (1, f"p{i}", VPNService.encrypt_data(f"k{i}"), f"pub{i}", ip_suffix),
        )
    await db_connection.commit()

    with pytest.raises(ValueError, match="No available"):
        await VPNService.get_next_ipv4(db_connection)


# ============================================================================
# update_profile edge cases
# ============================================================================


@pytest.mark.asyncio
async def test_update_profile_none_name(prepared_db: Path) -> None:
    assert await VPNService.update_profile(1, None) is False


@pytest.mark.asyncio
async def test_update_profile_empty_name(prepared_db: Path) -> None:
    assert await VPNService.update_profile(1, "") is False


# ============================================================================
# get_server_status
# ============================================================================


@pytest.mark.asyncio
async def test_server_status_no_binary(
    test_settings: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(vpn_service_module.shutil, "which", lambda _binary: None)
    result = await VPNService.get_server_status()
    assert result["status"] == "error"
    assert result["active_peers_count"] == 0


# ============================================================================
# get_all_peers_stats
# ============================================================================


@pytest.mark.asyncio
async def test_peers_stats_parses_dump(
    test_settings: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Correctly parses wg show dump output."""
    monkeypatch.setattr(vpn_service_module.shutil, "which", lambda _binary: "/usr/bin/wg")

    # wg show dump format: pubkey preshared endpoint allowed_ips latest_handshake rx tx keepalive
    # Code reads parts[6]=rx, parts[7]=tx so we need at least 8 tab-separated fields
    # with numeric values at indices 6 and 7.
    dump_output = (
        "private_key\tpublic_key\tlisten_port\tfwmark\n"
        "peer_pub_1\tpreshared\tendpoint\tallowed_ips\tlatest_handshake\thandshake_time\t1000\t2000\tpersistent\n"
        "peer_pub_2\tpreshared\tendpoint\tallowed_ips\tlatest_handshake\thandshake_time\t3000\t4000\tpersistent\n"
    )
    mock_process = AsyncMock()
    mock_process.communicate.return_value = (dump_output.encode(), b"")
    mock_process.returncode = 0
    monkeypatch.setattr(
        vpn_service_module.asyncio, "create_subprocess_exec", AsyncMock(return_value=mock_process)
    )

    stats = await VPNService.get_all_peers_stats()
    assert "peer_pub_1" in stats
    assert stats["peer_pub_1"]["rx"] == 1000
    assert stats["peer_pub_1"]["tx"] == 2000
    assert stats["peer_pub_1"]["total"] == 3000
    assert stats["peer_pub_2"]["total"] == 7000


@pytest.mark.asyncio
async def test_peers_stats_no_binary(
    test_settings: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(vpn_service_module.shutil, "which", lambda _binary: None)
    result = await VPNService.get_all_peers_stats()
    assert result == {}


# ============================================================================
# get_monthly_usage
# ============================================================================


@pytest.mark.asyncio
async def test_monthly_usage_offset(
    db_connection: aiosqlite.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """monthly_total = stats total - offset when total >= offset."""
    user_id = 501
    await db_connection.execute("INSERT INTO users (telegram_id) VALUES (?)", (user_id,))
    await db_connection.execute(
        "INSERT INTO vpn_profiles (user_id, name, private_key, public_key, ipv4_address, monthly_offset_bytes) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, "test_profile", VPNService.encrypt_data("k"), "test_pub_key", "10.0.0.2", 1000),
    )
    await db_connection.commit()

    monkeypatch.setattr(
        VPNService,
        "get_all_peers_stats",
        AsyncMock(return_value={"test_pub_key": {"rx": 500, "tx": 1000, "total": 1500}}),
    )

    result = await VPNService.get_monthly_usage(db_connection, user_id)
    assert len(result) == 1
    assert result[0]["monthly_total"] == 500  # 1500 - 1000


@pytest.mark.asyncio
async def test_monthly_usage_offset_exceeds(
    db_connection: aiosqlite.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When offset > total, falls back to raw total."""
    user_id = 502
    await db_connection.execute("INSERT INTO users (telegram_id) VALUES (?)", (user_id,))
    await db_connection.execute(
        "INSERT INTO vpn_profiles (user_id, name, private_key, public_key, ipv4_address, monthly_offset_bytes) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, "test_profile", VPNService.encrypt_data("k"), "test_pub_key_2", "10.0.0.3", 5000),
    )
    await db_connection.commit()

    monkeypatch.setattr(
        VPNService,
        "get_all_peers_stats",
        AsyncMock(return_value={"test_pub_key_2": {"rx": 500, "tx": 1000, "total": 1500}}),
    )

    result = await VPNService.get_monthly_usage(db_connection, user_id)
    assert len(result) == 1
    assert result[0]["monthly_total"] == 1500  # Fallback to raw total since offset > total
