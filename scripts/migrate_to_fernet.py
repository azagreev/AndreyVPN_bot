import asyncio
import aiosqlite
from bot.core.config import settings
from bot.services.vpn_service import VPNService
from loguru import logger

_DUPLICATE_IPV4_QUERY = """
SELECT ipv4_address, COUNT(*) as cnt
FROM vpn_profiles
WHERE ipv4_address IS NOT NULL AND ipv4_address <> ''
GROUP BY ipv4_address
HAVING cnt > 1
LIMIT 1
"""

_DUPLICATE_PUBLIC_KEY_QUERY = """
SELECT public_key, COUNT(*) as cnt
FROM vpn_profiles
WHERE public_key IS NOT NULL AND public_key <> ''
GROUP BY public_key
HAVING cnt > 1
LIMIT 1
"""


async def _assert_no_duplicates(db: aiosqlite.Connection) -> None:
    async with db.execute(_DUPLICATE_IPV4_QUERY) as cursor:
        duplicate_ipv4 = await cursor.fetchone()
    if duplicate_ipv4:
        raise RuntimeError(
            f"Duplicate ipv4_address found: {duplicate_ipv4[0]} (count={duplicate_ipv4[1]}).",
        )

    async with db.execute(_DUPLICATE_PUBLIC_KEY_QUERY) as cursor:
        duplicate_public_key = await cursor.fetchone()
    if duplicate_public_key:
        raise RuntimeError(
            "Duplicate public_key found in vpn_profiles "
            f"(count={duplicate_public_key[1]}).",
        )


async def _ensure_unique_indexes(db: aiosqlite.Connection) -> None:
    await db.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_vpn_profiles_ipv4_unique
        ON vpn_profiles(ipv4_address)
        WHERE ipv4_address IS NOT NULL AND ipv4_address <> ''
        """,
    )
    await db.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_vpn_profiles_public_key_unique
        ON vpn_profiles(public_key)
        WHERE public_key IS NOT NULL AND public_key <> ''
        """,
    )


async def migrate_to_fernet() -> int:
    """
    Миграция существующих приватных ключей на Fernet-шифрование.
    Правила:
    1) Plaintext ключи WireGuard шифруются текущим ENCRYPTION_KEY.
    2) Валидные Fernet-токены остаются без изменений.
    3) Невалидные Fernet-подобные токены считаются ошибкой и останавливают миграцию.
    """
    # Fail-fast на кривом/пустом ключе шифрования.
    VPNService.reset_cache()
    VPNService._get_fernet()

    async with aiosqlite.connect(settings.db_path) as db:
        await db.execute("BEGIN IMMEDIATE")
        db.row_factory = aiosqlite.Row
        try:
            await _assert_no_duplicates(db)
            await _ensure_unique_indexes(db)

            async with db.execute("SELECT id, private_key FROM vpn_profiles") as cursor:
                rows = await cursor.fetchall()

            updated_count = 0
            for row in rows:
                profile_id = row["id"]
                raw_key = row["private_key"]

                if not raw_key:
                    raise RuntimeError(f"Profile {profile_id} has empty private_key.")

                if VPNService.looks_like_fernet_token(raw_key):
                    try:
                        VPNService.decrypt_data(raw_key)
                    except ValueError as exc:
                        raise RuntimeError(
                            "Found Fernet-like token that cannot be decrypted with current "
                            f"ENCRYPTION_KEY. profile_id={profile_id}",
                        ) from exc
                    continue

                encrypted_key = VPNService.encrypt_data(raw_key)
                await db.execute(
                    "UPDATE vpn_profiles SET private_key = ? WHERE id = ?",
                    (encrypted_key, profile_id),
                )
                updated_count += 1

            await db.commit()
            logger.success(f"Миграция завершена. Обновлено профилей: {updated_count}")
            return updated_count
        except Exception:
            await db.rollback()
            raise


async def _run() -> None:
    try:
        updated = await migrate_to_fernet()
        logger.info(f"Migration complete, updated rows: {updated}")
    except Exception as exc:
        logger.error(f"Migration failed: {exc}")
        raise


if __name__ == "__main__":
    asyncio.run(_run())
