import asyncio
import os
import sys

# Добавляем путь к проекту в sys.path
sys.path.append(os.getcwd())

from bot.services.vpn_service import VPNService

async def test_qr_generation():
    print("Testing QR generation...")
    test_config = """[Interface]
PrivateKey = TestKey
Address = 10.8.0.2/32"""
    
    try:
        qr_bytes = VPNService.generate_qr_code(test_config)
        print(f"Success! QR bytes length: {len(qr_bytes)}")
        
        # Сохраним локально для визуальной проверки
        with open("test_qr.png", "wb") as f:
            f.write(qr_bytes)
        print("Test QR saved to test_qr.png")
        
    except ImportError:
        print("Error: segno is not installed!")
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    asyncio.run(test_qr_generation())
