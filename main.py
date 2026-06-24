import asyncio
import logging
from scheduler import run_all

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

if __name__ == "__main__":
    print("🚀 MFR AUTO Auction Bot запущен...")
    print("🎛 Админ-панель: напиши /start боту в личку")
    asyncio.run(run_all())
