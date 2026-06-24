import asyncio
import logging
from datetime import datetime
from scrapers.iaai_scraper import scrape_iaai
from scrapers.copart_scraper import scrape_copart
from scrapers.bidcars_scraper import scrape_bidcars
from analyzer.market_analyzer import analyze_cars
from publisher.telegram_publisher import publish_to_telegram
from admin_bot import run_admin_bot, load_settings

logger = logging.getLogger(__name__)


async def run_once():
    s = load_settings()
    logger.info(f"⏰ Запуск цикла: {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    logger.info("📡 Парсим аукционы...")

    bidcars_task = asyncio.create_task(scrape_bidcars(s))
    copart_task = asyncio.create_task(scrape_copart(s))

    bidcars_cars, copart_cars = await asyncio.gather(bidcars_task, copart_task, return_exceptions=True)

    all_cars = []
    for result in [bidcars_cars, copart_cars]:
        if isinstance(result, list):
            all_cars.extend(result)
        else:
            logger.error(f"Ошибка парсинга: {result}")

    logger.info(f"📋 Всего найдено лотов: {len(all_cars)}")
    if not all_cars:
        return

    logger.info("🧠 Анализируем рынок Бишкека...")
    top_cars = await analyze_cars(all_cars)
    logger.info(f"✅ Топ выгодных машин: {len(top_cars)}")
    if not top_cars:
        return

    logger.info("📢 Публикуем в Telegram...")
    await publish_to_telegram(top_cars)
    logger.info("🎉 Цикл завершён!")


async def run_scheduler():
    s = load_settings()
    interval = s.get("check_interval_hours", 6)
    logger.info(f"🤖 Бот запущен. Интервал: каждые {interval} часов")

    while True:
        try:
            s = load_settings()
            await run_once()
        except Exception as e:
            logger.error(f"Критическая ошибка: {e}")
        s = load_settings()
        interval = s.get("check_interval_hours", 6)
        logger.info(f"💤 Следующий запуск через {interval} часов")
        await asyncio.sleep(interval * 3600)


async def run_all():
    await asyncio.gather(run_scheduler(), run_admin_bot())
