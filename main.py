import asyncio
import logging
from scheduler import run_scheduler

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

if __name__ == "__main__":
    print("🚀 MFR AUTO Auction Bot запущен...")
    asyncio.run(run_scheduler())
