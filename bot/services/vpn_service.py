import asyncio
import shutil
from loguru import logger


class VPNService:
    """
    Сервис для управления VPN-профилями и ключами WireGuard.
    """

    @staticmethod
    def _check_wg_installed():
        """
        Проверяет наличие утилиты 'wg' в системе.
        """
        if shutil.which("wg") is None:
            logger.error("Утилита 'wg' не найдена в системе. Убедитесь, что wireguard-tools установлен.")
            return False
        return True

    @classmethod
    async def generate_keys(cls) -> tuple[str, str]:
        """
        Генерирует пару ключей (private key, public key) с помощью утилиты wg.
        
        :return: Кортеж (private_key, public_key)
        """
        if not cls._check_wg_installed():
            # Если wg не установлен, мы не можем генерировать ключи штатным способом.
            # Для тестовых сред или при отсутствии wg можно было бы добавить альтернативу,
            # но по ТЗ требуется использование CLI.
            raise RuntimeError("wg utility not found")

        try:
            # Генерируем приватный ключ
            process_genkey = await asyncio.create_subprocess_exec(
                "wg", "genkey",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process_genkey.communicate()
            if process_genkey.returncode != 0:
                logger.error(f"Ошибка при генерации приватного ключа: {stderr.decode()}")
                raise RuntimeError("Failed Mikrotik to generate private key")
            
            private_key = stdout.decode().strip()

            # Генерируем публичный ключ на основе приватного
            process_pubkey = await asyncio.create_subprocess_exec(
                "wg", "pubkey",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process_pubkey.communicate(input=private_key.encode())
            if process_pubkey.returncode != 0:
                logger.error(f"Ошибка при генерации публичного ключа: {stderr.decode()}")
                raise RuntimeError("Failed to generate public key")
            
            public_key = stdout.decode().strip()

            logger.info("Успешно сгенерирована пара ключей WireGuard")
            return private_key, public_key

        except Exception as e:
            logger.exception(f"Непредвиденная ошибка при генерации ключей: {e}")
            raise e

    @classmethod
    async def get_next_ipv4(cls) -> str:
        """
        Вычисляет следующий свободный IPv4-адрес для нового профиля.
        По умолчанию использует 10.8.0.2, если база пуста.
        
        :return: Строка с IPv4 адресом.
        """
        from bot.core.config import settings
        import aiosqlite
        
        # Разбираем базовую сеть из vpn_ip_range (например, 10.8.0.0/24)
        base_net = settings.vpn_ip_range.split('/')[0]
        net_parts = base_net.split('.')
        base_prefix = ".".join(net_parts[:3])
        
        try:
            async with aiosqlite.connect(settings.db_path) as db:
                query = "SELECT ipv4_address FROM vpn_profiles ORDER BY id DESC LIMIT 1;"
                async with db.execute(query) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        last_ip = row[0]
                        last_octet = int(last_ip.split('.')[-1])
                        next_octet = last_octet + 1
                        if next_octet > 254:
                            raise ValueError("IP range exhausted for /24 network")
                        return f"{base_prefix}.{next_octet}"
                    else:
                        # Если база пуста, начинаем с .2 (.1 обычно у сервера)
                        return f"{base_prefix}.2"
        except Exception as e:
            logger.warning(f"Ошибка или отсутствие данных в БД при получении IP: {e}. Используем начальный IP.")
            return f"{base_prefix}.2"

    @classmethod
    def generate_config_content(cls, private_key: str, ipv4: str) -> str:
        """
        Формирует строку конфигурационного файла .conf для клиента AmneziaWG.
        """
        from bot.core.config import settings
        
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
    async def sync_peer_with_server(cls, public_key: str, ipv4: str) -> bool:
        """
        Добавляет публичный ключ пира в конфигурацию сервера WireGuard в реальном времени.
        Вызывает команду: wg set <interface> peer <pubkey> allowed-ips <ipv4>/32
        """
        from bot.core.config import settings
        
        if not cls._check_wg_installed():
            return False

        try:
            command = ["wg", "set", settings.wg_interface, "peer", public_key, "allowed-ips", f"{ipv4}/32"]
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
                logger.error(f"Ошибка при синхронизации пира с сервером: {stderr.decode()}")
                return False
        except Exception as e:
            logger.exception(f"Непредвиденная ошибка при синхронизации пира: {e}")
            return False

    @classmethod
    async def create_profile(cls, user_id: int, name: str) -> dict:
        """
        Полный цикл создания VPN профиля: генерация ключей, выбор IP, 
        синхронизация с сервером и сохранение в БД.
        """
        from bot.core.config import settings
        import aiosqlite
        
        # 1. Генерация ключей
        private_key, public_key = await cls.generate_keys()
        
        # 2. Выбор следующего IP
        ipv4 = await cls.get_next_ipv4()
        
        # 3. Синхронизация с сервером
        # ВНИМАНИЕ: Если мы в среде без реального WG интерфейса (тесты/локалка),
        # этот шаг может вернуть False, но мы можем разрешить продолжение для тестов.
        synced = await cls.sync_peer_with_server(public_key, ipv4)
        if not synced:
            logger.warning("Синхронизация с WG сервером не удалась. Возможно, интерфейс не активен.")

        # 4. Сохранение в БД
        try:
            async with aiosqlite.connect(settings.db_path) as db:
                query = """
                INSERT INTO vpn_profiles (user_id, name, private_key, public_key, ipv4_address)
                VALUES (?, ?, ?, ?, ?);
                """
                await db.execute(query, (user_id, name, private_key, public_key, ipv4))
                await db.commit()
            
            logger.success(f"Профиль '{name}' для пользователя {user_id} успешно создан и сохранен.")
            
            # 5. Генерация конфиг-файла (строки)
            config_content = cls.generate_config_content(private_key, ipv4)
            
            return {
                "name": name,
                "ipv4": ipv4,
                "config": config_content,
                "synced": synced
            }
        except Exception as e:
            logger.error(f"Ошибка при сохранении профиля в БД: {e}")
            raise e
