import asyncio
import shutil
import aiosqlite
import ipaddress
from cryptography.fernet import Fernet
from loguru import logger
from bot.core.config import settings


class VPNService:
    """
    Сервис для управления VPN-профилями и ключами WireGuard/AmneziaWG.
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
            logger.warning("Encryption key is not set! Sensitive data will be stored as-is (UNSAFE).")
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
        """
        Шифрует строку данных.
        """
        fernet = cls._get_fernet()
        if not fernet:
            return data
        return fernet.encrypt(data.encode()).decode()

    @classmethod
    def decrypt_data(cls, encrypted_data: str) -> str:
        """
        Расшифровывает данные.
        """
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
        """
        Проверяет наличие утилиты 'wg' или 'awg' в системе.
        Для AmneziaWG рекомендуется проверять наличие awg.
        """
        if shutil.which("awg") is not None:
            return True
        if shutil.which("wg") is None:
            logger.error("Утилиты 'wg' или 'awg' не найдены. Убедитесь, что AmneziaWG или WireGuard установлены.")
            return False
        return True

    @classmethod
    async def generate_keys(cls) -> tuple[str, str]:
        """
        Генерирует пару ключей (private key, public key).
        Приоритет отдается утилите 'awg', если её нет — 'wg'.
        """
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
                logger.error(f"Ошибка при генерации приватного ключа: {stderr.decode()}")
                raise RuntimeError(f"Failed to generate private key with {binary}")
            
            private_key = stdout.decode().strip()

            process_pubkey = await asyncio.create_subprocess_exec(
                binary, "pubkey",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process_pubkey.communicate(input=private_key.encode())
            if process_pubkey.returncode != 0:
                logger.error(f"Ошибка при генерации публичного ключа: {stderr.decode()}")
                raise RuntimeError(f"Failed to generate public key with {binary}")
            
            public_key = stdout.decode().strip()
            return private_key, public_key

        except Exception as e:
            logger.exception(f"Непредвиденная ошибка при генерации ключей: {e}")
            raise e

    @classmethod
    async def get_next_ipv4(cls, db: aiosqlite.Connection) -> str:
        """
        Вычисляет ПЕРВЫЙ свободный IPv4-адрес в CIDR-пуле.
        Принимает существующее соединение для атомарности внутри транзакции.
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
    async def sync_peer_with_server(cls, public_key: str, ipv4: str) -> bool:
        """
        Добавляет пира в конфигурацию сервера.
        """
        if not cls._check_wg_installed():
            return False

        binary = "awg" if shutil.which("awg") else "wg"
        try:
            command = [binary, "set", settings.wg_interface, "peer", public_key, "allowed-ips", f"{ipv4}/32"]
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            _, stderr = await process.communicate()
            
            if process.returncode == 0:
                logger.info(f"Пир {public_key} успешно добавлен на сервер ({ipv4})")
                return True
            else:
                logger.error(f"Ошибка при синхронизации пира: {stderr.decode()}")
                return False
        except Exception as e:
            logger.exception(f"Непредвиденная ошибка при синхронизации: {e}")
            return False

    @classmethod
    async def create_profile(cls, user_id: int, name: str) -> dict:
        """
        Полный цикл создания профиля в одной атомарной транзакции БД.
        """
        async with aiosqlite.connect(settings.db_path) as db:
            await db.execute("BEGIN IMMEDIATE")
            try:
                private_key, public_key = await cls.generate_keys()
                ipv4 = await cls.get_next_ipv4(db)
                encrypted_private_key = cls.encrypt_data(private_key)
                
                synced = await cls.sync_peer_with_server(public_key, ipv4)
                if not synced:
                    logger.warning(f"Синхронизация с сервером не удалась для {public_key}.")

                query = """
                INSERT INTO vpn_profiles (user_id, name, private_key, public_key, ipv4_address)
                VALUES (?, ?, ?, ?, ?);
                """
                await db.execute(query, (user_id, name, encrypted_private_key, public_key, ipv4))
                await db.commit()
            
                logger.success(f"Профиль '{name}' для пользователя {user_id} успешно создан (IP: {ipv4}).")
                
                return {
                    "name": name,
                    "ipv4": ipv4,
                    "config": cls.generate_config_content(private_key, ipv4),
                    "synced": synced
                }
            except Exception as e:
                await db.rollback()
                logger.error(f"Ошибка при создании профиля: {e}")
                raise e

    @classmethod
    def generate_config_content(cls, private_key: str, ipv4: str) -> str:
        """
        Формирует строку конфигурации .conf для клиента AmneziaWG.
        """
        config = f"""[Interface]
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
        return config

    @classmethod
    def generate_qr_code(cls, content: str) -> bytes:
        import segno
        import io
        qr = segno.make(content, error='M')
        out = io.BytesIO()
        qr.save(out, kind='png', scale=10)
        return out.getvalue()

    @staticmethod
    def format_bytes(size_bytes: int) -> str:
        import math
        if size_bytes == 0:
            return "0 Б"
        size_name = ("Б", "КБ", "МБ", "ГБ", "ТБ")
        i = int(math.floor(math.log(size_bytes, 1024)))
        p = math.pow(1024, i)
        s = round(size_bytes / p, 2)
        return f"{s} {size_name[i]}"

    @classmethod
    async def get_monthly_usage(cls, db: aiosqlite.Connection, user_id: int) -> list[dict]:
        await cls.check_and_perform_monthly_reset(db)
        all_stats = await cls.get_all_peers_stats()
        query = "SELECT name, public_key, ipv4_address, monthly_offset_bytes FROM vpn_profiles WHERE user_id = ?"
        results = []
        async with db.execute(query, (user_id,)) as cursor:
            async for row in cursor:
                pub_key = row[1]
                offset = row[3] or 0
                stats = all_stats.get(pub_key, {'rx': 0, 'tx': 0, 'total': 0})
                current_total = stats['total']
                monthly_bytes = current_total if current_total < offset else current_total - offset
                results.append({
                    "name": row[0],
                    "ip": row[2],
                    "rx": stats['rx'],
                    "tx": stats['tx'],
                    "monthly_total": monthly_bytes
                })
        return results

    @classmethod
    async def check_and_perform_monthly_reset(cls, db: aiosqlite.Connection):
        from datetime import datetime
        now = datetime.now()
        current_month_key = now.strftime("%Y-%m")
        async with db.execute("SELECT value FROM configs WHERE key = 'last_traffic_reset'", ()) as cursor:
            row = await cursor.fetchone()
            if not row or row[0] != current_month_key:
                all_stats = await cls.get_all_peers_stats()
                for pub_key, stat in all_stats.items():
                    await db.execute("UPDATE vpn_profiles SET monthly_offset_bytes = ? WHERE public_key = ?", (stat['total'], pub_key))
                await db.execute("INSERT OR REPLACE INTO configs (key, value) VALUES ('last_traffic_reset', ?)", (current_month_key,))
                await db.commit()
                logger.success(f"Ежемесячный сброс завершен ({current_month_key}).")
