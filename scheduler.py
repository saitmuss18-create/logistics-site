import asyncio
import logging
from datetime import datetime
from scrapers.iaai_scraper import scrape_iaai
from scrapers.copart_scraper import scrape_copart
from scrapers.bidcars_scraper import scrape_bidcars
from analyzer.market_analyzer import analyze_cars
from publisher.telegram_publisher import publish_to_telegram
from config import CHECK_INTERVAL_HOURS

logger = logging.getLogger(__name__)


async def run_once():
    """Один цикл: парсинг → анализ → публикация"""
    logger.info(f"⏰ Запуск цикла: {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    
    # 1. Парсим все аукционы параллельно
    logger.info("📡 Парсим аукционы...")
    iaai_cars, copart_cars, bidcars_cars = await asyncio.gather(
        scrape_iaai(),
        scrape_copart(),
        scrape_bidcars(),
        return_exceptions=True
    )
    
    all_cars = []
    for result in [iaai_cars, copart_cars, bidcars_cars]:
        if isinstance(result, list):
            all_cars.extend(result)
        else:
            logger.error(f"Ошибка парсинга: {result}")
    
    logger.info(f"📋 Всего найдено лотов: {len(all_cars)}")
    
    if not all_cars:
        logger.warning("Нет данных для анализа")
        return
    
    # 2. Анализируем
    logger.info("🧠 Анализируем рынок Бишкека...")
    top_cars = await analyze_cars(all_cars)
    logger.info(f"✅ Топ выгодных машин: {len(top_cars)}")
    
    if not top_cars:
        logger.warning("Нет подходящих машин для публикации")
        return
    
    # 3. Публикуем в Telegram
    logger.info("📢 Публикуем в Telegram...")
    await publish_to_telegram(top_cars)
    
    logger.info("🎉 Цикл завершён!")


async def run_scheduler():
    """Запускает бот по расписанию"""
    logger.info(f"🤖 Бот запущен. Интервал: каждые {CHECK_INTERVAL_HOURS} часов")
    
    while True:
        try:
            await run_once()
        except Exception as e:
            logger.error(f"Критическая ошибка в цикле: {e}")
        
        next_run = CHECK_INTERVAL_HOURS * 3600
        logger.info(f"💤 Следующий запуск через {CHECK_INTERVAL_HOURS} часов")
        await asyncio.sleep(next_run)
