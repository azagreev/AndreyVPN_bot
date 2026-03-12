"""Tests for incident root cause fixes (Steps 1-6)."""
from pathlib import Path
from unittest.mock import AsyncMock

import aiosqlite
import pytest

import bot.services.vpn_service as vpn_service_module
from bot.core.config import settings
from bot.services.vpn_service import VPNService


# ============================================================================
# Step 1: Docker-mode binary resolution
# ============================================================================


def test_resolve_binary_docker_mode(
    test_settings: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """In Docker mode, returns bare 'awg' without shutil.which."""
    monkeypatch.setattr(settings, "wg_container_name", "amneziawg", raising=False)
    # shutil.which would return None — but should never be called
    monkeypatch.setattr(vpn_service_module.shutil, "which", lambda _: None)
    assert VPNService._resolve_wg_binary() == "awg"


def test_resolve_wg_quick_binary_docker_mode(
    test_settings: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "wg_container_name", "amneziawg", raising=False)
    monkeypatch.setattr(vpn_service_module.shutil, "which", lambda _: None)
    assert VPNService._resolve_wg_quick_binary() == "awg-quick"


def test_resolve_binary_direct_mode_awg(
    test_settings: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Direct mode prefers awg binary."""
    monkeypatch.setattr(settings, "wg_container_name", "", raising=False)
    monkeypatch.setattr(
        vpn_service_module.shutil,
        "which",
        lambda b: "/usr/bin/awg" if b == "awg" else None,
    )
    assert VPNService._resolve_wg_binary() == "/usr/bin/awg"


def test_resolve_binary_direct_mode_no_binaries(
    test_settings: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "wg_container_name", "", raising=False)
    monkeypatch.setattr(vpn_service_module.shutil, "which", lambda _: None)
    with pytest.raises(RuntimeError, match="not installed"):
        VPNService._resolve_wg_binary()


def test_resolve_wg_quick_direct_mode_no_binaries(
    test_settings: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "wg_container_name", "", raising=False)
    monkeypatch.setattr(vpn_service_module.shutil, "which", lambda _: None)
    with pytest.raises(RuntimeError, match="not installed"):
        VPNService._resolve_wg_quick_binary()


# ============================================================================
# Step 2: Docker exec -i flag
# ============================================================================


def test_build_command_docker_interactive(
    test_settings: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "wg_container_name", "awg_container", raising=False)
    cmd = VPNService._build_command("awg", "pubkey", interactive=True)
    assert cmd == ["docker", "exec", "-i", "awg_container", "awg", "pubkey"]


def test_build_command_docker_non_interactive(
    test_settings: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "wg_container_name", "awg_container", raising=False)
    cmd = VPNService._build_command("awg", "genkey")
    assert cmd == ["docker", "exec", "awg_container", "awg", "genkey"]
    assert "-i" not in cmd


def test_build_command_direct_mode_ignores_interactive(
    test_settings: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "wg_container_name", "", raising=False)
    cmd = VPNService._build_command("awg", "pubkey", interactive=True)
    assert cmd == ["awg", "pubkey"]
    assert "docker" not in cmd


# ============================================================================
# Step 4: Config generation with S3/S4/I1
# ============================================================================


def test_config_includes_s3_when_nonzero(
    test_settings: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "s3", 100, raising=False)
    monkeypatch.setattr(settings, "s4", 200, raising=False)
    monkeypatch.setattr(settings, "i1", 300, raising=False)
    config = VPNService.generate_config_content("test_key", "10.0.0.2")
    assert "S3 = 100" in config
    assert "S4 = 200" in config
    assert "I1 = 300" in config


def test_config_excludes_s3_s4_i1_when_zero(
    test_settings: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "s3", 0, raising=False)
    monkeypatch.setattr(settings, "s4", 0, raising=False)
    monkeypatch.setattr(settings, "i1", 0, raising=False)
    config = VPNService.generate_config_content("test_key", "10.0.0.2")
    assert "S3" not in config
    assert "S4" not in config
    assert "I1" not in config


# ============================================================================
# Step 5: save_interface_config
# ============================================================================


@pytest.mark.asyncio
async def test_save_interface_config_success(
    test_settings: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "wg_container_name", "awg_container", raising=False)

    mock_process = AsyncMock()
    mock_process.communicate.return_value = (b"", b"")
    mock_process.returncode = 0
    monkeypatch.setattr(
        vpn_service_module.asyncio, "create_subprocess_exec", AsyncMock(return_value=mock_process)
    )

    result = await VPNService.save_interface_config()
    assert result is True


@pytest.mark.asyncio
async def test_save_interface_config_failure(
    test_settings: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "wg_container_name", "awg_container", raising=False)

    mock_process = AsyncMock()
    mock_process.communicate.return_value = (b"", b"save failed")
    mock_process.returncode = 1
    monkeypatch.setattr(
        vpn_service_module.asyncio, "create_subprocess_exec", AsyncMock(return_value=mock_process)
    )

    result = await VPNService.save_interface_config()
    assert result is False


@pytest.mark.asyncio
async def test_save_interface_config_no_binary(
    test_settings: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "wg_container_name", "", raising=False)
    monkeypatch.setattr(vpn_service_module.shutil, "which", lambda _: None)

    result = await VPNService.save_interface_config()
    assert result is False


# ============================================================================
# Step 5: recover_all_peers
# ============================================================================


@pytest.mark.asyncio
async def test_recover_all_peers_empty_db(
    db_connection: aiosqlite.Connection,
) -> None:
    ok, fail = await VPNService.recover_all_peers(db_connection)
    assert ok == 0
    assert fail == 0


@pytest.mark.asyncio
async def test_recover_all_peers_syncs_profiles(
    db_connection: aiosqlite.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Insert test data
    await db_connection.execute("INSERT INTO users (telegram_id) VALUES (1)")
    await db_connection.execute(
        "INSERT INTO vpn_profiles (user_id, name, private_key, public_key, ipv4_address) "
        "VALUES (?, ?, ?, ?, ?)",
        (1, "p1", VPNService.encrypt_data("k1"), "pub1", "10.0.0.2"),
    )
    await db_connection.execute(
        "INSERT INTO vpn_profiles (user_id, name, private_key, public_key, ipv4_address) "
        "VALUES (?, ?, ?, ?, ?)",
        (1, "p2", VPNService.encrypt_data("k2"), "pub2", "10.0.0.3"),
    )
    await db_connection.commit()

    monkeypatch.setattr(settings, "wg_container_name", "awg_container", raising=False)

    mock_process = AsyncMock()
    mock_process.communicate.return_value = (b"", b"")
    mock_process.returncode = 0
    mock_create = AsyncMock(return_value=mock_process)
    monkeypatch.setattr(vpn_service_module.asyncio, "create_subprocess_exec", mock_create)

    ok, fail = await VPNService.recover_all_peers(db_connection)
    assert ok == 2
    assert fail == 0
    # 2 awg set calls + 1 awg-quick save = 3 subprocess calls
    assert mock_create.await_count == 3


@pytest.mark.asyncio
async def test_recover_all_peers_no_binary(
    db_connection: aiosqlite.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await db_connection.execute("INSERT INTO users (telegram_id) VALUES (1)")
    await db_connection.execute(
        "INSERT INTO vpn_profiles (user_id, name, private_key, public_key, ipv4_address) "
        "VALUES (?, ?, ?, ?, ?)",
        (1, "p1", VPNService.encrypt_data("k1"), "pub1", "10.0.0.2"),
    )
    await db_connection.commit()

    monkeypatch.setattr(settings, "wg_container_name", "", raising=False)
    monkeypatch.setattr(vpn_service_module.shutil, "which", lambda _: None)

    ok, fail = await VPNService.recover_all_peers(db_connection)
    assert ok == 0
    assert fail == 1


# ============================================================================
# Step 6: SERVER_PUB_KEY format validation
# ============================================================================


def test_valid_base64_key_format() -> None:
    """Valid WireGuard key: 44 chars, base64 ending with =."""
    import re
    key = "YWJjZGVmZ2hpamtsbW5vcHFyc3R1dnd4eXoxMjM0NTY="
    assert re.match(r'^[A-Za-z0-9+/]{43}=$', key)


def test_invalid_key_format_rejected() -> None:
    import re
    bad_keys = [
        "not_a_valid_key",
        "too_short=",
        "",
        "public_key_of_your_server",
    ]
    for key in bad_keys:
        assert not re.match(r'^[A-Za-z0-9+/]{43}=$', key), f"Should reject: {key}"
