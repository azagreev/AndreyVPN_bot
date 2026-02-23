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
