import asyncio
import aiosqlite
import os
import sys

# Добавляем путь к проекту
sys.path.append(os.getcwd())

from bot.services.vpn_service import VPNService

async def test_monitoring():
    print("Testing Monitoring Logic...")
    
    # 1. Тест парсинга (заглушка для wg show dump)
    # Формат: interface public_key preshared_key endpoint allowed_ips latest_handshake transfer_rx transfer_tx persistent_keepalive
    mock_output = """wg0
PubKey1	(none)	1.2.3.4:5678	10.8.0.2/32	12345678	5000000	10000000	(none)
PubKey2	(none)	5.6.7.8:1234	10.8.0.3/32	12345679	1000000	2000000	(none)"""
    
    print("Mocking 'wg show dump' output...")
    # Мы не можем легко подменить subprocess, но можем проверить метод format_bytes
    print(f"Format 1024 bytes: {VPNService.format_bytes(1024)}")
    print(f"Format 1048576 bytes: {VPNService.format_bytes(1048576)}")
    
    # 2. Тест логики ежемесячного сброса в БД
    db_path = "bot_data.db"
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        print("Checking monthly reset logic...")
        await VPNService.check_and_perform_monthly_reset(db)
        
        async with db.execute("SELECT value FROM configs WHERE key = 'last_traffic_reset'") as cursor:
            row = await cursor.fetchone()
            print(f"Last reset month in DB: {row['value'] if row else 'None'}")

if __name__ == "__main__":
    asyncio.run(test_monitoring())
