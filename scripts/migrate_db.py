import asyncio
import aiosqlite
import os

async def migrate():
    db_path = "bot_data.db"
    if not os.path.exists(db_path):
        print("Database not found.")
        return

    async with aiosqlite.connect(db_path) as db:
        try:
            await db.execute("ALTER TABLE vpn_profiles ADD COLUMN monthly_offset_bytes INTEGER DEFAULT 0;")
            await db.commit()
            print("Successfully added monthly_offset_bytes column.")
        except Exception as e:
            if "duplicate column name" in str(e).lower():
                print("Column already exists.")
            else:
                print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(migrate())
