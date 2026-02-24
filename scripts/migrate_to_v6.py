import asyncio
import aiosqlite
from bot.core.config import settings
from bot.services.vpn_service import VPNService
from loguru import logger

async def migrate_v6():
    if not settings.encryption_key:
        logger.error("ENCRYPTION_KEY not set.")
        return

    async with aiosqlite.connect(settings.db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT id, private_key FROM vpn_profiles") as cursor:
            rows = await cursor.fetchall()

        count = 0
        for row in rows:
            pk = row['private_key']
            if not pk.startswith('gAAAAA'): # Simple check for Fernet token
                enc = VPNService.encrypt_data(pk)
                await db.execute("UPDATE vpn_profiles SET private_key = ? WHERE id = ?", (enc, row['id']))
                count += 1
        
        await db.commit()
        logger.info(f"Migrated {count} profiles to v6 encryption.")

if __name__ == "__main__":
    asyncio.run(migrate_v6())
