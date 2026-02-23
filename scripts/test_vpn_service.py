import asyncio
import os
import sys

# Добавляем путь к корню проекта для импортов
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

# Загружаем тестовые переменные окружения ДО импорта настроек
from dotenv import load_dotenv
load_dotenv(os.path.join(project_root, ".env.test"))

from bot.services.vpn_service import VPNService
from bot.db.engine import init_db
from bot.core.config import settings
from loguru import logger


async def run_test():
    logger.info("Starting VPNService Integration Test...")
    
    # 1. Инициализируем тестовую БД
    test_db = "test_vpn.db"
    settings.db_path = test_db
    if os.path.exists(test_db):
        os.remove(test_db)
        
    await init_db(settings.db_path)
    logger.info(f"Test database '{test_db}' initialized.")
    
    try:
        # 2. Создаем первый профиль
        logger.info("Creating first profile (test_user_1)...")
        profile1 = await VPNService.create_profile(12345, "test_user_1")
        
        print("\n--- PROFILE 1 ---")
        print(f"Name: {profile1['name']}")
        print(f"IP: {profile1['ipv4']}")
        print(f"Server Synced: {profile1['synced']}")
        print("Config Preview:")
        # Избегаем проблем с \n в f-строках или join в этом окружении
        lines = profile1['config'].split('\n')
        for i in range(min(5, len(lines))):
            print(lines[i])
        
        assert profile1['ipv4'] == "10.8.0.2", f"Expected 10.8.0.2, got {profile1['ipv4']}"
        
        # 3. Создаем второй профиль для проверки инкремента IP
        logger.info("Creating second profile (test_user_2)...")
        profile2 = await VPNService.create_profile(67890, "test_user_2")
        
        print("\n--- PROFILE 2 ---")
        print(f"Name: {profile2['name']}")
        print(f"IP: {profile2['ipv4']}")
        assert profile2['ipv4'] == "10.8.0.3", f"Expected 10.8.0.3, got {profile2['ipv4']}"
        
        logger.success("Integration test PASSED!")
        
    except Exception as e:
        logger.error(f"Integration test FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        if os.path.exists(test_db):
            os.remove(test_db)


if __name__ == "__main__":
    asyncio.run(run_test())
