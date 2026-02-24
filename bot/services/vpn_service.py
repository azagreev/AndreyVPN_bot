import asyncio
import shutil
import aiosqlite
import ipaddress
from cryptography.fernet import Fernet
from loguru import logger
from bot.core.config import settings


class VPNService:
    """
    v6: Сервис для управления VPN-профилями с поддержкой AmneziaWG и Fernet-шифрования.
    """
    _fernet: Fernet | None = None

    @classmethod
    def _get_fernet(cls) -> Fernet | None:
        """
        Инициализирует и возвращает экземпляр Fernet для шифрования.
        """
        if cls._fernet:
            return cls._fernet
        
        if not settings.encryption_key:
            logger.warning("ENCRYPTION_KEY is not set! Sensitive data will be stored as-is (UNSAFE).")
            return None
        
        try:
            key_val = settings.encryption_key
            if hasattr(key_val, "get_secret_value"):
                key_val = key_val.get_secret_value()
            
            cls._fernet = Fernet(key_val.encode())
            return cls._fernet
        except Exception as e:
            logger.error(f"Failed to initialize Fernet: {e}")
            return None

    @classmethod
    def encrypt_data(cls, data: str) -> str:
        fernet = cls._get_fernet()
        if not fernet:
            return data
        return fernet.encrypt(data.encode()).decode()

    @classmethod
    def decrypt_data(cls, encrypted_data: str) -> str:
        fernet = cls._get_fernet()
        if not fernet:
            return encrypted_data
        try:
            return fernet.decrypt(encrypted_data.encode()).decode()
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            return encrypted_data

    @staticmethod
    def _check_wg_installed() -> bool:
        if shutil.which("awg") is not None:
            return True
        if shutil.which("wg") is None:
            logger.error("Utilities 'wg' or 'awg' not found.")
            return False
        return True

    @classmethod
    async def generate_keys(cls) -> tuple[str, str]:
        if not cls._check_wg_installed():
            raise RuntimeError("WireGuard/AmneziaWG utilities not found")

        binary = "awg" if shutil.which("awg") else "wg"
        try:
            process_genkey = await asyncio.create_subprocess_exec(
                binary, "genkey",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process_genkey.communicate()
            if process_genkey.returncode != 0:
                raise RuntimeError(f"Failed to generate private key: {stderr.decode()}")
            
            private_key = stdout.decode().strip()

            process_pubkey = await asyncio.create_subprocess_exec(
                binary, "pubkey",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process_pubkey.communicate(input=private_key.encode())
            if process_pubkey.returncode != 0:
                raise RuntimeError(f"Failed to generate public key: {stderr.decode()}")
            
            return private_key, stdout.decode().strip()
        except Exception as e:
            logger.exception(f"Error generating keys: {e}")
            raise e

    @classmethod
    async def get_next_ipv4(cls, db: aiosqlite.Connection) -> str:
        """
        Вычисляет ПЕРВЫЙ свободный IPv4-адрес в CIDR пуле.
        """
        network = ipaddress.IPv4Network(settings.vpn_ip_range, strict=False)
        available_hosts = list(network.hosts())
        if len(available_hosts) < 2:
            raise ValueError("IP range is too small")
        
        async with db.execute("SELECT ipv4_address FROM vpn_profiles") as cursor:
            rows = await cursor.fetchall()
            used_ips = {row[0] for row in rows}
        
        for ip in available_hosts[1:]:
            ip_str = str(ip)
            if ip_str not in used_ips:
                return ip_str
        
        raise ValueError("No available IP addresses in the configured range")

    @classmethod
    async def create_profile(cls, user_id: int, name: str) -> dict:
        """
        Атомарное создание профиля (v6).
        """
        async with aiosqlite.connect(settings.db_path) as db:
            await db.execute("BEGIN IMMEDIATE")
            try:
                private_key, public_key = await cls.generate_keys()
                ipv4 = await cls.get_next_ipv4(db)
                encrypted_key = cls.encrypt_data(private_key)
                
                # Синхронизация с сервером
                synced = await cls.sync_peer_with_server(public_key, ipv4)
                
                await db.execute(
                    "INSERT INTO vpn_profiles (user_id, name, private_key, public_key, ipv4_address) VALUES (?, ?, ?, ?, ?)",
                    (user_id, name, encrypted_key, public_key, ipv4)
                )
                await db.commit()
                
                return {
                    "name": name,
                    "ipv4": ipv4,
                    "config": cls.generate_config_content(private_key, ipv4),
                    "synced": synced
                }
            except Exception as e:
                await db.rollback()
                logger.error(f"Failed to create profile: {e}")
                raise e

    @classmethod
    async def update_profile(cls, profile_id: int, new_name: str | None = None) -> bool:
        """
        v6: Обновление существующего профиля.
        """
        async with aiosqlite.connect(settings.db_path) as db:
            if not new_name:
                return False
            try:
                await db.execute("UPDATE vpn_profiles SET name = ? WHERE id = ?", (new_name, profile_id))
                await db.commit()
                return True
            except Exception as e:
                logger.error(f"Failed to update profile: {e}")
                return False

    @classmethod
    async def sync_peer_with_server(cls, public_key: str, ipv4: str) -> bool:
        if not cls._check_wg_installed():
            return False
        binary = "awg" if shutil.which("awg") else "wg"
        try:
            command = [binary, "set", settings.wg_interface, "peer", public_key, "allowed-ips", f"{ipv4}/32"]
            process = await asyncio.create_subprocess_exec(*command, stderr=asyncio.subprocess.PIPE)
            _, stderr = await process.communicate()
            return process.returncode == 0
        except Exception as e:
            logger.error(f"Sync error: {e}")
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

    @classmethod
    async def get_monthly_usage(cls, db: aiosqlite.Connection, user_id: int) -> list[dict]:
        all_stats = await cls.get_all_peers_stats()
        query = "SELECT id, name, public_key, ipv4_address, monthly_offset_bytes FROM vpn_profiles WHERE user_id = ?"
        results = []
        async with db.execute(query, (user_id,)) as cursor:
            async for row in cursor:
                pub_key = row[2]
                offset = row[4] or 0
                stats = all_stats.get(pub_key, {'total': 0, 'rx': 0, 'tx': 0})
                monthly_total = stats['total'] - offset if stats['total'] >= offset else stats['total']
                results.append({
                    "id": row[0],
                    "name": row[1],
                    "ip": row[3],
                    "monthly_total": monthly_total
                })
        return results

    @classmethod
    async def get_all_peers_stats(cls) -> dict[str, dict[str, int]]:
        if not cls._check_wg_installed():
            return {}
        binary = "awg" if shutil.which("awg") else "wg"
        try:
            process = await asyncio.create_subprocess_exec(binary, "show", settings.wg_interface, "dump", stdout=asyncio.subprocess.PIPE)
            stdout, _ = await process.communicate()
            stats = {}
            for line in stdout.decode().strip().split('\n')[1:]:
                parts = line.split('\t')
                if len(parts) >= 8:
                    stats[parts[0]] = {'rx': int(parts[6]), 'tx': int(parts[7]), 'total': int(parts[6]) + int(parts[7])}
            return stats
        except Exception:
            return {}
