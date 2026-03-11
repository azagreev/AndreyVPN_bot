import asyncio
import ipaddress
import shutil
from io import BytesIO
from typing import Any

import aiosqlite
import segno
from cryptography.fernet import Fernet, InvalidToken
from loguru import logger

from bot.core.config import settings
from bot.core.logging import log_wg_command, log_wg_result
from bot.db import repository


class VPNService:
    """
    Сервис для управления VPN-профилями с поддержкой AmneziaWG и Fernet-шифрования.

    Все методы, требующие доступа к БД, принимают db: aiosqlite.Connection —
    соединение управляется снаружи (через DbMiddleware или lifecycle hooks).
    """

    _fernet: Fernet | None = None
    _FERNET_PREFIX = "gAAAAA"

    @classmethod
    def reset_cache(cls) -> None:
        cls._fernet = None

    @classmethod
    def _get_fernet(cls) -> Fernet:
        if cls._fernet is not None:
            return cls._fernet

        raw_key = settings.encryption_key
        if raw_key is None:
            raise RuntimeError("ENCRYPTION_KEY is required for private key encryption.")

        key_value = raw_key if isinstance(raw_key, str) else raw_key.get_secret_value()
        if not key_value:
            raise RuntimeError("ENCRYPTION_KEY is empty.")

        try:
            cls._fernet = Fernet(key_value.encode("utf-8"))
        except (TypeError, ValueError) as exc:
            raise RuntimeError("ENCRYPTION_KEY must be a valid Fernet key.") from exc

        return cls._fernet

    @classmethod
    def encrypt_data(cls, data: str) -> str:
        if not data:
            raise ValueError("Private key is empty and cannot be encrypted.")
        token = cls._get_fernet().encrypt(data.encode("utf-8"))
        return token.decode("utf-8")

    @classmethod
    def decrypt_data(cls, encrypted_data: str) -> str:
        if not encrypted_data:
            raise ValueError("Encrypted private key is empty.")
        try:
            payload = cls._get_fernet().decrypt(encrypted_data.encode("utf-8"))
        except InvalidToken as exc:
            raise ValueError(
                "Invalid encrypted private key or ENCRYPTION_KEY mismatch.",
            ) from exc
        return payload.decode("utf-8")

    @classmethod
    def looks_like_fernet_token(cls, value: str) -> bool:
        return value.startswith(cls._FERNET_PREFIX)

    @staticmethod
    def _resolve_wg_binary() -> str:
        """Находит бинарник awg или wg в PATH."""
        awg_binary = shutil.which("awg")
        if awg_binary:
            return awg_binary
        wg_binary = shutil.which("wg")
        if wg_binary:
            return wg_binary
        raise RuntimeError("Utilities 'awg' or 'wg' are not installed or not in PATH.")

    @classmethod
    def _build_command(cls, *args: str) -> list[str]:
        """
        Строит команду для выполнения.
        Если WG_CONTAINER_NAME задан — оборачивает в docker exec.
        Иначе вызывает напрямую.
        """
        cmd = list(args)
        container = settings.wg_container_name.strip()
        if container:
            return ["docker", "exec", container] + cmd
        return cmd

    @classmethod
    async def generate_keys(cls) -> tuple[str, str]:
        binary = cls._resolve_wg_binary()

        genkey_cmd = cls._build_command(binary, "genkey")
        log_wg_command(genkey_cmd)
        process_genkey = await asyncio.create_subprocess_exec(
            *genkey_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        genkey_stdout, genkey_stderr = await process_genkey.communicate()
        if process_genkey.returncode != 0:
            error = genkey_stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"Failed to generate private key: {error}")

        private_key = genkey_stdout.decode("utf-8", errors="replace").strip()
        if not private_key:
            raise RuntimeError("Generated private key is empty.")

        pubkey_cmd = cls._build_command(binary, "pubkey")
        log_wg_command(pubkey_cmd)
        process_pubkey = await asyncio.create_subprocess_exec(
            *pubkey_cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        pubkey_stdout, pubkey_stderr = await process_pubkey.communicate(
            input=private_key.encode("utf-8"),
        )
        if process_pubkey.returncode != 0:
            error = pubkey_stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"Failed to generate public key: {error}")

        public_key = pubkey_stdout.decode("utf-8", errors="replace").strip()
        if not public_key:
            raise RuntimeError("Generated public key is empty.")

        return private_key, public_key

    @classmethod
    async def get_next_ipv4(cls, db: aiosqlite.Connection) -> str:
        network = ipaddress.IPv4Network(settings.vpn_ip_range, strict=False)
        host_count = max(network.num_addresses - 2, 0)
        if host_count < 2:
            raise ValueError(
                "VPN_IP_RANGE is too small. Use CIDR that contains at least two usable hosts.",
            )

        used_ips: set[ipaddress.IPv4Address] = set()
        async with db.execute(
            "SELECT ipv4_address FROM vpn_profiles WHERE ipv4_address IS NOT NULL",
        ) as cursor:
            async for (raw_ip,) in cursor:
                try:
                    parsed_ip = ipaddress.IPv4Address(raw_ip)
                except ipaddress.AddressValueError:
                    logger.warning(f"Skipping invalid IPv4 entry in DB: {raw_ip!r}")
                    continue
                if parsed_ip in network:
                    used_ips.add(parsed_ip)

        host_iterator = iter(network.hosts())
        next(host_iterator, None)  # резервируем первый адрес для шлюза

        for ip in host_iterator:
            if ip not in used_ips:
                return str(ip)

        raise ValueError("No available IP addresses in the configured range")

    @classmethod
    async def create_profile(
        cls, db: aiosqlite.Connection, user_id: int, name: str
    ) -> dict:
        """Атомарное создание профиля. Принимает db — не открывает своё соединение."""
        await db.execute("BEGIN IMMEDIATE")
        try:
            private_key, public_key = await cls.generate_keys()
            ipv4 = await cls.get_next_ipv4(db)
            encrypted_key = cls.encrypt_data(private_key)

            synced = await cls.sync_peer_with_server(public_key, ipv4)

            await repository.insert_vpn_profile(db, user_id, name, encrypted_key, public_key, ipv4)
            await db.commit()

            return {
                "name": name,
                "ipv4": ipv4,
                "config": cls.generate_config_content(private_key, ipv4),
                "synced": synced,
            }
        except aiosqlite.IntegrityError as exc:
            await db.rollback()
            raise RuntimeError(
                "Failed to create profile due to DB integrity violation. "
                "Check duplicate public_key/ipv4.",
            ) from exc
        except Exception:
            await db.rollback()
            raise

    @classmethod
    async def sync_peer_with_server(cls, public_key: str, ipv4: str) -> bool:
        try:
            binary = cls._resolve_wg_binary()
        except RuntimeError as exc:
            logger.error(str(exc))
            return False

        args = cls._build_command(
            binary, "set", settings.wg_interface, "peer", public_key,
            "allowed-ips", f"{ipv4}/32"
        )
        log_wg_command(args)
        try:
            process = await asyncio.create_subprocess_exec(
                *args,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await process.communicate()
            err = stderr.decode("utf-8", errors="replace").strip()
            log_wg_result(process.returncode, err)
            if process.returncode != 0:
                logger.error(f"Sync error: {err}")
                return False
            return True
        except OSError as exc:
            logger.error(f"Sync error: {exc}")
            return False

    @classmethod
    def generate_config_content(cls, private_key: str, ipv4: str) -> str:
        return f"""[Interface]
PrivateKey = {private_key}
Address = {ipv4}/32
DNS = {settings.dns_servers}
Jc = {settings.jc}
Jmin = {settings.jmin}
Jmax = {settings.jmax}
S1 = {settings.s1}
S2 = {settings.s2}
H1 = {settings.h1}
H2 = {settings.h2}
H3 = {settings.h3}
H4 = {settings.h4}

[Peer]
PublicKey = {settings.server_pub_key}
Endpoint = {settings.server_endpoint}
AllowedIPs = 0.0.0.0/0
"""

    @staticmethod
    def generate_qr_code(config: str) -> bytes:
        qr_code = segno.make(config)
        buffer = BytesIO()
        qr_code.save(buffer, kind="png", scale=5)
        return buffer.getvalue()

    @staticmethod
    def format_bytes(value: int) -> str:
        units = ["B", "KB", "MB", "GB", "TB"]
        size = float(max(value, 0))
        for unit in units:
            if size < 1024.0 or unit == units[-1]:
                if unit == "B":
                    return f"{int(size)} {unit}"
                return f"{size:.2f} {unit}"
            size /= 1024.0
        return "0 B"

    @classmethod
    async def get_server_status(cls) -> dict[str, Any]:
        interface = settings.wg_interface
        try:
            binary = cls._resolve_wg_binary()
        except RuntimeError as exc:
            return {
                "status": "error",
                "interface": interface,
                "active_peers_count": 0,
                "message": str(exc),
            }

        args = cls._build_command(binary, "show", interface, "dump")
        process = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            message = stderr.decode("utf-8", errors="replace").strip() or "interface is unavailable"
            return {
                "status": "offline",
                "interface": interface,
                "active_peers_count": 0,
                "message": message,
            }

        lines = [line for line in stdout.decode("utf-8", errors="replace").splitlines() if line]
        active_peers_count = max(len(lines) - 1, 0)
        return {
            "status": "online",
            "interface": interface,
            "active_peers_count": active_peers_count,
        }

    @classmethod
    async def get_monthly_usage(cls, db: aiosqlite.Connection, user_id: int) -> list[dict]:
        all_stats = await cls.get_all_peers_stats()
        rows = await repository.get_monthly_usage_rows(db, user_id)
        results: list[dict] = []
        for row in rows:
            pub_key = row["public_key"]
            offset = row["monthly_offset_bytes"] or 0
            stats = all_stats.get(pub_key, {"total": 0, "rx": 0, "tx": 0})
            monthly_total = (
                stats["total"] - offset if stats["total"] >= offset else stats["total"]
            )
            results.append({
                "id": row["id"],
                "name": row["name"],
                "ip": row["ipv4_address"],
                "monthly_total": monthly_total,
            })
        return results

    @classmethod
    async def remove_peer_from_server(cls, public_key: str) -> bool:
        try:
            binary = cls._resolve_wg_binary()
        except RuntimeError as exc:
            logger.error(str(exc))
            return False

        args = cls._build_command(binary, "set", settings.wg_interface, "peer", public_key, "remove")
        log_wg_command(args)
        try:
            process = await asyncio.create_subprocess_exec(
                *args,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await process.communicate()
            err = stderr.decode("utf-8", errors="replace").strip()
            log_wg_result(process.returncode, err)
            if process.returncode != 0:
                logger.error(f"Failed to remove peer: {err}")
                return False
            return True
        except OSError as exc:
            logger.error(f"Failed to remove peer: {exc}")
            return False

    @classmethod
    async def delete_profile(cls, db: aiosqlite.Connection, profile_id: int) -> bool:
        """Удаляет профиль из WireGuard и базы данных. Принимает db — не открывает своё соединение."""
        public_key = await repository.get_profile_public_key(db, profile_id)
        if not public_key:
            return False

        await cls.remove_peer_from_server(public_key)
        await repository.delete_vpn_profile(db, profile_id)
        return True

    @classmethod
    async def get_profile_config(cls, db: aiosqlite.Connection, profile_id: int) -> dict | None:
        """Восстанавливает конфиг профиля. Принимает db — не открывает своё соединение."""
        row = await repository.get_profile_for_config(db, profile_id)
        if not row:
            return None

        name, encrypted_key, ipv4 = row["name"], row["private_key"], row["ipv4_address"]
        private_key = cls.decrypt_data(encrypted_key)
        config = cls.generate_config_content(private_key, ipv4)
        return {"name": name, "config": config, "ipv4": ipv4}

    @classmethod
    async def get_all_peers_stats(cls) -> dict[str, dict[str, int]]:
        try:
            binary = cls._resolve_wg_binary()
        except RuntimeError:
            return {}

        args = cls._build_command(binary, "show", settings.wg_interface, "dump")
        try:
            process = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await process.communicate()
            if process.returncode != 0:
                return {}

            stats: dict[str, dict[str, int]] = {}
            lines = stdout.decode("utf-8", errors="replace").strip().split("\n")
            for line in lines[1:]:
                parts = line.split("\t")
                if len(parts) >= 8:
                    rx = int(parts[6])
                    tx = int(parts[7])
                    stats[parts[0]] = {"rx": rx, "tx": tx, "total": rx + tx}
            return stats
        except (OSError, ValueError):
            return {}
