import asyncio
import aiosqlite
from bot.core.config import settings
from bot.services.vpn_service import VPNService
from loguru import logger

async def migrate_to_fernet():
    """
    Миграция существующих приватных ключей на Fernet-шифрование.
    Скрипт проверяет каждый ключ, и если он не зашифрован (или зашифрован старым ключом),
    перезаписывает его новым зашифрованным значением.
    """
    if not settings.encryption_key:
        logger.error("ENCRYPTION_KEY не установлен. Миграция невозможна.")
        return

    async with aiosqlite.connect(settings.db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT id, private_key FROM vpn_profiles") as cursor:
            rows = await cursor.fetchall()

        updated_count = 0
        for row in rows:
            profile_id = row['id']
            raw_key = row['private_key']
            
            # Пытаемся расшифровать. Если не получается - значит ключ в открытом виде или зашифрован иначе.
            VPNService.decrypt_data(raw_key)
            
            # Если расшифрованный ключ совпадает с исходным, значит он не был зашифрован 
            # (так как decrypt_data возвращает оригинал при ошибке или отсутствии фернета)
            # Либо если длина ключа WireGuard (44 символа base64) и он не зашифрован.
            
            is_encrypted = False
            try:
                # Fernet токены обычно начинаются с 'gAAAAA'
                if raw_key.startswith('gAAAAA'):
                    # Проверяем, можем ли мы его реально расшифровать текущим ключом
                    VPNService.decrypt_data(raw_key)
                    is_encrypted = True
            except:
                is_encrypted = False

            if not is_encrypted:
                logger.info(f"Шифрование ключа для профиля ID {profile_id}...")
                encrypted_key = VPNService.encrypt_data(raw_key)
                await db.execute(
                    "UPDATE vpn_profiles SET private_key = ? WHERE id = ?",
                    (encrypted_key, profile_id)
                )
                updated_count += 1

        await db.commit()
        logger.success(f"Миграция завершена. Обновлено профилей: {updated_count}")

if __name__ == "__main__":
    asyncio.run(migrate_to_fernet())
