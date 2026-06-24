import aiohttp
import asyncio
import logging
from config import TELEGRAM_TOKEN, TELEGRAM_CHANNEL

logger = logging.getLogger(__name__)

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"


async def publish_to_telegram(cars: list[dict]):
    """Публикует топ машин в Telegram канал"""
    
    if not cars:
        logger.info("Нет машин для публикации")
        return
    
    async with aiohttp.ClientSession() as session:
        # Заголовочный пост
        header = (
            "🚗 *MFR AUTO | ВЫГОДНЫЕ АВТО С АУКЦИОНОВ США*\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 Найдено {len(cars)} выгодных лотов\n"
            "🔍 Источники: IAAI + Copart + bid.cars\n"
            "🏙 Анализ рынка: Бишкек\n"
            "━━━━━━━━━━━━━━━━━━━━━"
        )
        await send_message(session, header)
        await asyncio.sleep(1)
        
        # Публикуем каждую машину
        for i, car in enumerate(cars, 1):
            message = format_car_message(car, i)
            
            if car.get("image"):
                await send_photo(session, car["image"], message)
            else:
                await send_message(session, message)
            
            await asyncio.sleep(2)  # Пауза между постами
        
        # Футер
        footer = (
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "📞 *Хотите заказать авто из США?*\n"
            "👉 Пишите нам: @MFRB2C\\_BOT\n"
            "🌐 MFR AUTO — доставка авто США → Бишкек\n"
            "━━━━━━━━━━━━━━━━━━━━━"
        )
        await send_message(session, footer)
    
    logger.info(f"✅ Опубликовано {len(cars)} машин в Telegram")


def format_car_message(car: dict, num: int) -> str:
    """Форматирует сообщение для одной машины"""
    
    title = car.get("title", "Неизвестно")
    source = car.get("source", "")
    price = car.get("price", 0)
    bids = car.get("bids", 0)
    damage = car.get("damage", "—")
    year = car.get("year", "—")
    total_cost = car.get("total_cost_usd", 0)
    bishkek_price = car.get("bishkek_price_usd", 0)
    profit = car.get("profit_usd", 0)
    roi = car.get("roi_percent", 0)
    demand = car.get("demand", "—")
    ai_comment = car.get("ai_comment", "")
    url = car.get("url", "")
    
    msg = (
        f"🏆 *#{num} | {title}*\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"🏷 Источник: {source}\n"
        f"💰 Цена на аукционе: *${price:,.0f}*\n"
        f"🔨 Ставок: {bids} {demand}\n"
        f"🔧 Повреждения: {damage}\n"
        f"\n"
        f"📦 Итоговая стоимость (с доставкой): *${total_cost:,}*\n"
        f"💵 Цена продажи в Бишкеке: *${bishkek_price:,}*\n"
        f"📈 Прибыль: *+${profit:,}* ({roi}% ROI)\n"
    )
    
    if ai_comment:
        msg += f"\n🤖 *AI-анализ:*\n_{ai_comment}_\n"
    
    if url:
        msg += f"\n🔗 [Смотреть лот]({url})"
    
    return msg


async def send_message(session: aiohttp.ClientSession, text: str):
    """Отправляет текстовое сообщение"""
    try:
        async with session.post(
            f"{TELEGRAM_API}/sendMessage",
            json={
                "chat_id": TELEGRAM_CHANNEL,
                "text": text,
                "parse_mode": "Markdown",
                "disable_web_page_preview": False,
            }
        ) as resp:
            data = await resp.json()
            if not data.get("ok"):
                logger.error(f"Telegram ошибка: {data.get('description')}")
    except Exception as e:
        logger.error(f"send_message ошибка: {e}")


async def send_photo(session: aiohttp.ClientSession, photo_url: str, caption: str):
    """Отправляет фото с подписью"""
    try:
        async with session.post(
            f"{TELEGRAM_API}/sendPhoto",
            json={
                "chat_id": TELEGRAM_CHANNEL,
                "photo": photo_url,
                "caption": caption[:1024],  # Telegram лимит на подпись
                "parse_mode": "Markdown",
            }
        ) as resp:
            data = await resp.json()
            if not data.get("ok"):
                # Если фото не загрузилось — шлём текст
                await send_message(session, caption)
    except Exception as e:
        logger.error(f"send_photo ошибка: {e}")
        await send_message(session, caption)
