import aiohttp
import asyncio
import json
import logging
import os
from config import TELEGRAM_CHANNEL, ADMIN_CHAT_ID

logger = logging.getLogger(__name__)


def get_api():
    return f"https://api.telegram.org/bot{os.getenv('TELEGRAM_TOKEN', '')}"


async def publish_to_telegram(cars: list[dict]):
    if not cars:
        return

    async with aiohttp.ClientSession() as session:
        header = (
            "🚗 *MFR AUTO | ВЫГОДНЫЕ АВТО С АУКЦИОНОВ США*\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 Найдено {len(cars)} выгодных лотов\n"
            "🔍 Источники: IAAI + Copart + bid.cars\n"
            "🏙 Анализ рынка: Бишкек\n"
            "━━━━━━━━━━━━━━━━━━━━━"
        )
        await send_message(session, TELEGRAM_CHANNEL, header)
        await asyncio.sleep(1)

        for i, car in enumerate(cars, 1):
            pub_msg = format_car_message(car, i, for_admin=False)
            admin_msg = format_car_message(car, i, for_admin=True)

            # Список фото лота (берём до 10 штук)
            all_images = car.get("images") or ([car["image"]] if car.get("image") else [])
            # Фильтруем только фото с images.bid.cars или cs.copart.com
            car_images = [u for u in all_images if "images.bid.cars" in u or "cs.copart.com" in u or "mercury.bid.cars" in u]
            if not car_images and all_images:
                car_images = all_images[:1]

            if car_images:
                # Отправляем альбом (до 10 фото) в канал
                await send_photo_album(session, TELEGRAM_CHANNEL, car_images[:10], pub_msg)
                # Админу — первое фото + описание с прямой ссылкой
                photo_bytes = await download_photo(session, car_images[0])
                if photo_bytes:
                    await send_photo_bytes(session, ADMIN_CHAT_ID, photo_bytes, admin_msg)
                else:
                    await send_message(session, ADMIN_CHAT_ID, admin_msg)
            else:
                await send_message(session, TELEGRAM_CHANNEL, pub_msg)
                await send_message(session, ADMIN_CHAT_ID, admin_msg)

            await asyncio.sleep(3)

        footer = (
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "📞 *Хотите заказать авто из США?*\n"
            "👉 Пишите нам: @MFRB2C\\_BOT\n"
            "🌐 MFR AUTO — доставка авто США → Бишкек\n"
            "━━━━━━━━━━━━━━━━━━━━━"
        )
        await send_message(session, TELEGRAM_CHANNEL, footer)

    logger.info(f"✅ Опубликовано {len(cars)} машин в Telegram")


async def send_photo_album(session: aiohttp.ClientSession, chat_id, photo_urls: list[str], caption: str):
    """Отправляет несколько фото как альбом (media group). Подпись только к первому фото."""
    if not photo_urls:
        return

    # Если одно фото — просто sendPhoto
    if len(photo_urls) == 1:
        photo_bytes = await download_photo(session, photo_urls[0])
        if photo_bytes:
            await send_photo_bytes(session, chat_id, photo_bytes, caption)
        else:
            await send_message(session, chat_id, caption)
        return

    # Скачиваем все фото
    photos_data = []
    for url in photo_urls[:10]:
        data = await download_photo(session, url)
        if data:
            photos_data.append(data)

    if not photos_data:
        await send_message(session, chat_id, caption)
        return

    # Если не удалось скачать несколько — отправляем одно
    if len(photos_data) == 1:
        await send_photo_bytes(session, chat_id, photos_data[0], caption)
        return

    try:
        # Формируем media group
        media = []
        for i, _ in enumerate(photos_data):
            item = {"type": "photo", "media": f"attach://photo{i}"}
            if i == 0:
                item["caption"] = caption[:1024]
                item["parse_mode"] = "Markdown"
            media.append(item)

        form = aiohttp.FormData()
        form.add_field("chat_id", str(chat_id))
        form.add_field("media", json.dumps(media))
        for i, data in enumerate(photos_data):
            form.add_field(f"photo{i}", data, filename=f"photo{i}.jpg", content_type="image/jpeg")

        async with session.post(f"{get_api()}/sendMediaGroup", data=form) as resp:
            result = await resp.json()
            if not result.get("ok"):
                logger.warning(f"sendMediaGroup ошибка: {result.get('description')}")
                # Fallback — отправляем первое фото
                await send_photo_bytes(session, chat_id, photos_data[0], caption)
    except Exception as e:
        logger.error(f"send_photo_album ошибка: {e}")
        await send_photo_bytes(session, chat_id, photos_data[0], caption)


async def download_photo(session: aiohttp.ClientSession, url: str):
    if not url:
        return None
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status == 200 and "image" in resp.content_type:
                return await resp.read()
    except Exception as e:
        logger.debug(f"Фото не загружено {url}: {e}")
    return None


def format_car_message(car: dict, num: int, for_admin: bool = False) -> str:
    price = car.get("price", 0)
    total_cost = car.get("total_cost_usd", 0)
    bishkek_price = car.get("bishkek_price_usd", 0)
    profit = car.get("profit_usd", 0)
    roi = car.get("roi_percent", 0)
    ai_comment = car.get("ai_comment", "")
    url = car.get("url", "")

    msg = (
        f"🏆 *#{num} | {car.get('title', '?')}*\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"🏷 Источник: {car.get('source', '')}\n"
        f"💰 Цена на аукционе: *${price:,.0f}*\n"
        f"🔨 Ставок: {car.get('bids', 0)} {car.get('demand', '')}\n"
        f"🔧 Повреждения: {car.get('damage', '?')}\n\n"
        f"📦 Итого с доставкой: *${total_cost:,}*\n"
        f"💵 Цена в Бишкеке: *${bishkek_price:,}*\n"
        f"📈 Прибыль: *+${profit:,}* ({roi}% ROI)\n"
    )

    if ai_comment:
        msg += f"\n🤖 *AI:* _{ai_comment}_\n"

    if url:
        link_text = "🔗 [Открыть лот на аукционе]" if for_admin else "🔗 [Смотреть лот]"
        msg += f"\n{link_text}({url})"

    return msg


async def send_message(session: aiohttp.ClientSession, chat_id, text: str):
    try:
        async with session.post(
            f"{get_api()}/sendMessage",
            json={"chat_id": chat_id, "text": text,
                  "parse_mode": "Markdown", "disable_web_page_preview": False}
        ) as resp:
            data = await resp.json()
            if not data.get("ok"):
                logger.error(f"Telegram ошибка: {data.get('description')}")
    except Exception as e:
        logger.error(f"send_message ошибка: {e}")


async def send_photo_bytes(session: aiohttp.ClientSession, chat_id, photo: bytes, caption: str):
    try:
        form = aiohttp.FormData()
        form.add_field("chat_id", str(chat_id))
        form.add_field("caption", caption[:1024])
        form.add_field("parse_mode", "Markdown")
        form.add_field("photo", photo, filename="photo.jpg", content_type="image/jpeg")

        async with session.post(f"{get_api()}/sendPhoto", data=form) as resp:
            data = await resp.json()
            if not data.get("ok"):
                await send_message(session, chat_id, caption)
    except Exception as e:
        logger.error(f"send_photo ошибка: {e}")
        await send_message(session, chat_id, caption)
