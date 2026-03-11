"""Тесты для docker exec адаптера в VPNService."""
import pytest
from unittest.mock import patch

from bot.services.vpn_service import VPNService
from bot.core.config import settings


def test_build_command_direct(monkeypatch: pytest.MonkeyPatch):
    """Без WG_CONTAINER_NAME — прямой вызов."""
    monkeypatch.setattr(settings, "wg_container_name", "", raising=False)
    cmd = VPNService._build_command("awg", "genkey")
    assert cmd == ["awg", "genkey"]


def test_build_command_docker_exec(monkeypatch: pytest.MonkeyPatch):
    """С WG_CONTAINER_NAME — docker exec обёртка."""
    monkeypatch.setattr(settings, "wg_container_name", "amneziawg", raising=False)
    cmd = VPNService._build_command("awg", "genkey")
    assert cmd == ["docker", "exec", "amneziawg", "awg", "genkey"]


def test_build_command_docker_exec_set(monkeypatch: pytest.MonkeyPatch):
    """docker exec для awg set."""
    monkeypatch.setattr(settings, "wg_container_name", "myvpn", raising=False)
    cmd = VPNService._build_command("awg", "set", "awg0", "peer", "pubkey123", "allowed-ips", "10.0.0.2/32")
    assert cmd[0] == "docker"
    assert cmd[1] == "exec"
    assert cmd[2] == "myvpn"
    assert "awg" in cmd
    assert "set" in cmd


def test_build_command_strips_whitespace(monkeypatch: pytest.MonkeyPatch):
    """Пробелы в имени контейнера обрезаются."""
    monkeypatch.setattr(settings, "wg_container_name", "  amneziawg  ", raising=False)
    cmd = VPNService._build_command("awg", "show")
    assert cmd[2] == "amneziawg"


def test_build_command_empty_string_is_direct(monkeypatch: pytest.MonkeyPatch):
    """Пустая строка = прямой вызов."""
    monkeypatch.setattr(settings, "wg_container_name", "   ", raising=False)
    cmd = VPNService._build_command("awg", "show")
    assert cmd == ["awg", "show"]
