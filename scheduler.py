import asyncio
import logging
from datetime import datetime
from scrapers.bidcars_scraper import scrape_bidcars
from scrapers.copart_scraper import scrape_copart
from scrapers.iaai_scraper import scrape_iaai
from analyzer.market_analyzer import analyze_cars
from publisher.telegram_publisher import publish_to_telegram
from admin_bot import run_admin_bot, load_settings

logger = logging.getLogger(__name__)


async def _notify(session, chat_id: int, text: str):
    """Отправляет сообщение администратору."""
    if session is None or chat_id is None:
        return
    try:
        import json, os
        from config import TELEGRAM_TOKEN
        token = os.getenv("TELEGRAM_TOKEN") or TELEGRAM_TOKEN
        api = f"https://api.telegram.org/bot{token}"
        payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
        async with session.post(f"{api}/sendMessage", json=payload):
            pass
    except Exception as e:
        logger.debug(f"notify: {e}")


async def run_once_with_feedback(session=None, chat_id: int = None):
    """Запуск с обратной связью в Telegram."""
    s = load_settings()
    sources = s.get("sources", ["bid.cars", "Copart"])
    now = datetime.now().strftime("%d.%m.%Y %H:%M")

    logger.info(f"⏰ Запуск цикла: {now}")
    await _notify(session, chat_id,
                  f"⏰ *Запуск поиска* — {now}\n🌐 Источники: {', '.join(sources)}")

    all_cars = []

    if "bid.cars" in sources:
        await _notify(session, chat_id, "🔍 Ищу на *bid.cars*...")
        try:
            cars = await scrape_bidcars(s)
            count = len(cars)
            if count:
                await _notify(session, chat_id, f"✅ *bid.cars:* найдено *{count}* новых лотов")
            else:
                await _notify(session, chat_id, "ℹ️ *bid.cars:* новых лотов не найдено")
            all_cars.extend(cars)
        except Exception as e:
            logger.error(f"bid.cars: {e}")
            await _notify(session, chat_id, f"❌ *bid.cars* ошибка: {e}")

    if "Copart" in sources:
        await _notify(session, chat_id, "🔍 Ищу на *Copart*...")
        try:
            cars = await scrape_copart(s)
            count = len(cars)
            if count:
                await _notify(session, chat_id, f"✅ *Copart:* найдено *{count}* новых лотов")
            else:
                await _notify(session, chat_id, "ℹ️ *Copart:* новых лотов не найдено")
            all_cars.extend(cars)
        except Exception as e:
            logger.error(f"Copart: {e}")
            await _notify(session, chat_id, f"❌ *Copart* ошибка: {e}")

    if "IAAI" in sources:
        await _notify(session, chat_id, "🔍 Ищу на *IAAI*...")
        try:
            cars = await scrape_iaai(s)
            count = len(cars)
            if count:
                await _notify(session, chat_id, f"✅ *IAAI:* найдено *{count}* новых лотов")
            else:
                await _notify(session, chat_id, "ℹ️ *IAAI:* новых лотов не найдено")
            all_cars.extend(cars)
        except Exception as e:
            logger.error(f"IAAI: {e}")
            await _notify(session, chat_id, f"❌ *IAAI* ошибка: {e}")

    total = len(all_cars)
    logger.info(f"📋 Всего найдено лотов: {total}")

    if not all_cars:
        await _notify(session, chat_id, "📭 Новых лотов не найдено. Попробуй позже или измени фильтры.")
        return

    await _notify(session, chat_id, f"🧠 Анализирую {total} лотов...")
    try:
        top_cars = await analyze_cars(all_cars)
    except Exception as e:
        logger.error(f"Анализ: {e}")
        top_cars = all_cars

    pub_count = len(top_cars)
    if not top_cars:
        await _notify(session, chat_id, "📭 После фильтров ничего не осталось.")
        return

    await _notify(session, chat_id, f"📢 Публикую *{pub_count}* лотов в канал...")
    try:
        await publish_to_telegram(top_cars)
        await _notify(session, chat_id, f"🎉 *Готово!* Опубликовано *{pub_count}* лотов в канал.")
    except Exception as e:
        logger.error(f"Публикация: {e}")
        await _notify(session, chat_id, f"❌ Ошибка публикации: {e}")


async def run_once():
    """Запуск без обратной связи (для планировщика)."""
    await run_once_with_feedback(session=None, chat_id=None)


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
