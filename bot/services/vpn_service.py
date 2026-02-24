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


class VPNService:
    """
    Сервис для управления VPN-профилями с поддержкой AmneziaWG и Fernet-шифрования.
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
        awg_binary = shutil.which("awg")
        if awg_binary:
            return awg_binary

        wg_binary = shutil.which("wg")
        if wg_binary:
            return wg_binary

        raise RuntimeError("Utilities 'awg' or 'wg' are not installed or not in PATH.")

    @classmethod
    async def generate_keys(cls) -> tuple[str, str]:
        binary = cls._resolve_wg_binary()

        process_genkey = await asyncio.create_subprocess_exec(
            binary,
            "genkey",
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

        process_pubkey = await asyncio.create_subprocess_exec(
            binary,
            "pubkey",
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
        """
        Вычисляет ПЕРВЫЙ свободный IPv4-адрес в CIDR пуле.
        """
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

        # Первый host традиционно резервируется под сервер/шлюз.
        host_iterator = iter(network.hosts())
        next(host_iterator, None)

        for ip in host_iterator:
            if ip not in used_ips:
                return str(ip)

        raise ValueError("No available IP addresses in the configured range")

    @classmethod
    async def create_profile(cls, user_id: int, name: str) -> dict:
        """
        Атомарное создание профиля.
        """
        async with aiosqlite.connect(settings.db_path, timeout=30) as db:
            await db.execute("PRAGMA foreign_keys = ON")
            await db.execute("BEGIN IMMEDIATE")
            try:
                private_key, public_key = await cls.generate_keys()
                ipv4 = await cls.get_next_ipv4(db)
                encrypted_key = cls.encrypt_data(private_key)

                synced = await cls.sync_peer_with_server(public_key, ipv4)

                await db.execute(
                    (
                        "INSERT INTO vpn_profiles "
                        "(user_id, name, private_key, public_key, ipv4_address) "
                        "VALUES (?, ?, ?, ?, ?)"
                    ),
                    (user_id, name, encrypted_key, public_key, ipv4),
                )
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
    async def update_profile(cls, profile_id: int, new_name: str | None = None) -> bool:
        """
        Обновление существующего профиля.
        """
        async with aiosqlite.connect(settings.db_path) as db:
            if not new_name:
                return False
            try:
                await db.execute("UPDATE vpn_profiles SET name = ? WHERE id = ?", (new_name, profile_id))
                await db.commit()
                return True
            except aiosqlite.Error as exc:
                logger.error(f"Failed to update profile: {exc}")
                return False

    @classmethod
    async def sync_peer_with_server(cls, public_key: str, ipv4: str) -> bool:
        try:
            binary = cls._resolve_wg_binary()
        except RuntimeError as exc:
            logger.error(str(exc))
            return False

        try:
            process = await asyncio.create_subprocess_exec(
                binary,
                "set",
                settings.wg_interface,
                "peer",
                public_key,
                "allowed-ips",
                f"{ipv4}/32",
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await process.communicate()
            if process.returncode != 0:
                err = stderr.decode("utf-8", errors="replace").strip()
                logger.error(f"Sync error: {err}")
                return False
            return process.returncode == 0
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

        process = await asyncio.create_subprocess_exec(
            binary,
            "show",
            interface,
            "dump",
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
        query = "SELECT id, name, public_key, ipv4_address, monthly_offset_bytes FROM vpn_profiles WHERE user_id = ?"
        results: list[dict[str, int | str]] = []
        async with db.execute(query, (user_id,)) as cursor:
            async for row in cursor:
                pub_key = row[2]
                offset = row[4] or 0
                stats = all_stats.get(pub_key, {"total": 0, "rx": 0, "tx": 0})
                monthly_total = (
                    stats["total"] - offset if stats["total"] >= offset else stats["total"]
                )
                results.append({
                    "id": row[0],
                    "name": row[1],
                    "ip": row[3],
                    "monthly_total": monthly_total,
                })
        return results

    @classmethod
    async def get_all_peers_stats(cls) -> dict[str, dict[str, int]]:
        try:
            binary = cls._resolve_wg_binary()
        except RuntimeError:
            return {}

        try:
            process = await asyncio.create_subprocess_exec(
                binary,
                "show",
                settings.wg_interface,
                "dump",
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
